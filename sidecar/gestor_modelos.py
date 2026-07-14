"""
Gestor de modelos GGUF do runtime embarcado (T-1702, ADR-0016 §F, REQ-F-028).

Três peças:

1. **Catálogo curado**, travado no código: 3 modelos 3-4B quantizados Q4,
   dimensionados para a GPU-alvo (4 GB de VRAM) ou CPU, todos com licença que
   permite uso comercial (a ADR-0006 já registrou que o Qwen2.5-3B usa a Qwen
   Research License, não comercial; o Ministral 3B, que o usuário roda no LM
   Studio dele, tem a mesma restrição — Mistral Research License — e por isso
   nenhum dos dois entra aqui). Os hashes SHA-256 vêm da API do Hugging Face
   (`lfs.oid`), NUNCA baixando o arquivo — ver a nota de proveniência de cada
   item.
2. **Download gerenciado**: única exceção de rede do app (REQ-NF-007), só por
   clique explícito do usuário. Escreve em `.parcial`, retoma via `Range` se o
   servidor aceitar, e só promove para o nome final (`os.replace`) depois do
   SHA-256 bater — hash errado apaga o parcial e levanta erro claro.
3. **Persistência da escolha** em `llm.json`, FORA do cofre: o caminho de um
   `.gguf` não é segredo (aponta um arquivo público no disco), então não há
   por que cifrá-lo. Escrita atômica temp+`os.replace`, mesmo padrão do
   `auth.json` (`sidecar/auth.py`).

Este módulo não sobe nenhum processo — quem faz o `llama-server` falar com o
modelo escolhido é `sidecar/runtime_llm.py` (T-1701), que lê `llm.json` via
`modelo_ativo()` na resolução `env > llm.json > ausente`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .arquivos import gravar_json_atomico

log = logging.getLogger("helper_financeiro.gestor_modelos")

# Variáveis de ambiente (prefixo HF_, como o resto do projeto).
VAR_MODELOS_DIR = "HF_MODELOS_DIR"        # override do destino dos downloads
VAR_LLM_CONFIG_PATH = "HF_LLM_CONFIG_PATH"  # override do llm.json

_TAMANHO_BLOCO = 1024 * 1024  # 1 MiB por leitura/escrita — streaming, sem carregar o .gguf inteiro na RAM
_TIMEOUT_CONEXAO_S = 30

EstadoArquivo = Literal["baixado", "ausente"]


# --------------------------------------------------------------- exceções
class ErroGestorModelos(Exception):
    """Base de todas as falhas tipadas deste módulo."""


class ModeloDownloadFalhou(ErroGestorModelos):
    """Erro de rede/HTTP durante o download — o `.parcial` fica no disco
    (retomável na próxima tentativa)."""


class ModeloHashInvalido(ErroGestorModelos):
    """O SHA-256 do arquivo baixado não bate com o catálogo — o `.parcial`
    já foi apagado quando esta exceção é levantada (nunca promove lixo)."""


class ModeloDownloadCancelado(ErroGestorModelos):
    """Cancelamento cooperativo pedido pelo usuário — o `.parcial` fica no
    disco para retomar depois (cancelar não é o mesmo que descartar)."""


class ModeloLocalInvalido(ErroGestorModelos):
    """O `.gguf` apontado pelo usuário não existe ou não tem a extensão certa."""


class CatalogoIdDesconhecido(ErroGestorModelos):
    """O `id` informado não está no catálogo curado."""


# ---------------------------------------------------------------- catálogo
@dataclass(frozen=True)
class ModeloCatalogo:
    """Um item do catálogo curado — tudo travado no código (REQ-F-028)."""

    id: str
    nome: str
    descricao: str
    licenca: str
    url: str
    sha256: str
    tamanho_bytes: int
    arquivo: str  # nome do arquivo final dentro de HF_MODELOS_DIR


# Catálogo curado (2026-07): 3 modelos 3-4B GGUF Q4_K_M, todos com licença de
# uso comercial permitido. Os SHA-256 foram obtidos SEM baixar o arquivo, via
#   GET https://huggingface.co/api/models/<repo>/tree/main?recursive=true
# (o campo `lfs.oid` de cada blob é o sha256 oficial do Hugging Face) —
# conferido em 2026-07, um item por vez, comando `curl` na mesma API.
CATALOGO: tuple[ModeloCatalogo, ...] = (
    ModeloCatalogo(
        id="phi-3.5-mini-instruct-q4",
        nome="Phi-3.5 Mini Instruct (Q4_K_M)",
        descricao=(
            "Microsoft, 3.8B parâmetros. Bom equilíbrio custo/qualidade em "
            "CPU ou GPU de 4 GB."
        ),
        licenca="MIT",
        # repo: bartowski/Phi-3.5-mini-instruct-GGUF (quantização comunitária
        # do Phi-3.5 oficial da Microsoft — o peso em si segue a licença MIT
        # do modelo original).
        url=(
            "https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/"
            "resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf"
        ),
        sha256="e4165e3a71af97f1b4820da61079826d8752a2088e313af0c7d346796c38eff5",
        tamanho_bytes=2393232672,
        arquivo="phi-3.5-mini-instruct-q4_k_m.gguf",
    ),
    ModeloCatalogo(
        id="qwen2.5-1.5b-instruct-q4",
        nome="Qwen2.5 1.5B Instruct (Q4_K_M)",
        descricao=(
            "Alibaba, 1.5B parâmetros. O mais leve dos três — roda bem em "
            "CPU/notebook modesto, com qualidade menor que os de 3-4B."
        ),
        licenca="Apache-2.0",
        # repo oficial: Qwen/Qwen2.5-1.5B-Instruct-GGUF. ATENÇÃO: Qwen2.5-3B
        # é Qwen Research License (NÃO comercial, ver agent/config.py) — só
        # o 1.5B (e o 7B+) da família 2.5 são Apache-2.0.
        url=(
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
            "resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
        ),
        sha256="6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        tamanho_bytes=1117320736,
        arquivo="qwen2.5-1.5b-instruct-q4_k_m.gguf",
    ),
    ModeloCatalogo(
        id="granite-3.1-2b-instruct-q4",
        nome="Granite 3.1 2B Instruct (Q4_K_M)",
        descricao=(
            "IBM, 2B parâmetros. Alternativa enxuta com procedência "
            "corporativa (IBM), pensada para uso empresarial."
        ),
        licenca="Apache-2.0",
        # repo: bartowski/granite-3.1-2b-instruct-GGUF (quantização
        # comunitária do granite-3.1-2b-instruct oficial da IBM, Apache-2.0).
        url=(
            "https://huggingface.co/bartowski/granite-3.1-2b-instruct-GGUF/"
            "resolve/main/granite-3.1-2b-instruct-Q4_K_M.gguf"
        ),
        sha256="774269c82fde2720ea18dcf457fb5bd028fe096139a0735f4ad59c0a270cfc9c",
        tamanho_bytes=1545295424,
        arquivo="granite-3.1-2b-instruct-q4_k_m.gguf",
    ),
)

# Override do catálogo inteiro (E2E/dev, NUNCA produção): caminho de um JSON
# com a mesma forma de `ModeloCatalogo` — permite o E2E baixar de um servidor
# HTTP LOCAL fake em vez do Hugging Face de verdade (nada de rede externa nos
# testes). Só existe quando alguém aponta a env explicitamente.
VAR_CATALOGO_TESTE = "HF_CATALOGO_TESTE"


def catalogo_efetivo(ambiente: Mapping[str, str] | None = None) -> tuple[ModeloCatalogo, ...]:
    """`CATALOGO` real, ou o catálogo de teste apontado por `HF_CATALOGO_TESTE`."""
    env = os.environ if ambiente is None else ambiente
    caminho = env.get(VAR_CATALOGO_TESTE, "").strip()
    if not caminho:
        return CATALOGO
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return tuple(ModeloCatalogo(**item) for item in dados)


def item_do_catalogo(catalogo_id: str,
                     ambiente: Mapping[str, str] | None = None) -> ModeloCatalogo:
    """Busca um item pelo `id` no catálogo efetivo; levanta
    `CatalogoIdDesconhecido` se não existir."""
    for item in catalogo_efetivo(ambiente):
        if item.id == catalogo_id:
            return item
    raise CatalogoIdDesconhecido(f"Modelo desconhecido no catálogo: {catalogo_id!r}")


# ------------------------------------------------------------------ caminhos
def caminho_modelos_dir(ambiente: Mapping[str, str] | None = None) -> Path:
    """Destino dos downloads: `HF_MODELOS_DIR` (testes) > perfil do usuário."""
    env = os.environ if ambiente is None else ambiente
    forcado = env.get(VAR_MODELOS_DIR, "").strip()
    if forcado:
        return Path(forcado)
    appdata = env.get("APPDATA", "").strip()
    base = Path(appdata) / "HelperFinanceiro" if appdata else Path.home() / ".helper_financeiro"
    return base / "modelos"


def caminho_llm_config(ambiente: Mapping[str, str] | None = None) -> Path:
    """`llm.json`: `HF_LLM_CONFIG_PATH` (testes) > perfil do usuário.

    Mesma pasta do `auth.json`/`dados.db`, mas FORA do cofre — o caminho de um
    `.gguf` aponta um arquivo público no disco, não é segredo.
    """
    env = os.environ if ambiente is None else ambiente
    forcado = env.get(VAR_LLM_CONFIG_PATH, "").strip()
    if forcado:
        return Path(forcado)
    appdata = env.get("APPDATA", "").strip()
    base = Path(appdata) / "HelperFinanceiro" if appdata else Path.home() / ".helper_financeiro"
    return base / "llm.json"


def caminho_final(item: ModeloCatalogo, ambiente: Mapping[str, str] | None = None,
                  destino_dir: Path | None = None) -> Path:
    """Caminho onde o `.gguf` de `item` fica depois de baixado com sucesso."""
    base = destino_dir if destino_dir is not None else caminho_modelos_dir(ambiente)
    return base / item.arquivo


def caminho_parcial(item: ModeloCatalogo, ambiente: Mapping[str, str] | None = None,
                    destino_dir: Path | None = None) -> Path:
    return caminho_final(item, ambiente, destino_dir).with_name(
        f"{item.arquivo}.parcial")


# --------------------------------------------------------------- llm.json
def _salvar_atomico(caminho: Path, dados: dict) -> None:
    """Escrita atômica temp+`os.replace` (C-27) — mesmo padrão do `auth.json`."""
    gravar_json_atomico(caminho, dados)


def ler_llm_config(ambiente: Mapping[str, str] | None = None) -> dict:
    """Lê o `llm.json`; devolve `{}` se ausente ou corrompido (nunca levanta —
    a ausência de config é um estado normal, não um erro)."""
    caminho = caminho_llm_config(ambiente)
    if not caminho.is_file():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("llm.json corrompido/ilegível (%s) — tratando como ausente.", e)
        return {}


def modelo_ativo(ambiente: Mapping[str, str] | None = None) -> str | None:
    """Caminho (string) do `.gguf` ativo segundo o `llm.json`, ou `None`."""
    bruto = ler_llm_config(ambiente).get("modelo_ativo")
    if not bruto:
        return None
    texto = str(bruto).strip()
    return texto or None


def definir_modelo_ativo(caminho: str | os.PathLike[str],
                         ambiente: Mapping[str, str] | None = None) -> Path:
    """Valida o `.gguf` e persiste como modelo ativo em `llm.json`.

    Encerra o runtime embarcado corrente (se algum estiver de pé): a próxima
    chamada a `base_url()` sobe de novo já com o modelo novo (T-1701 deixou
    essa pendência explícita para esta task). Import tardio de
    `sidecar.runtime_llm` só para evitar um ciclo de import a nível de módulo
    (`runtime_llm.resolver_modelo` também importa este módulo tardiamente).
    """
    validado = _validar_gguf(caminho)
    dados = ler_llm_config(ambiente)
    dados["modelo_ativo"] = str(validado)
    _salvar_atomico(caminho_llm_config(ambiente), dados)

    from .runtime_llm import encerrar_runtime
    encerrar_runtime()
    return validado


def _validar_gguf(caminho: str | os.PathLike[str]) -> Path:
    p = Path(caminho)
    if not p.is_file():
        raise ModeloLocalInvalido(f"Arquivo não encontrado: {p}")
    if p.suffix.lower() != ".gguf":
        raise ModeloLocalInvalido(f"Não é um arquivo .gguf: {p}")
    return p


# --------------------------------------------------------------- estado
def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(_TAMANHO_BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


# Cache do veredito de hash por (caminho, mtime_ns, tamanho): `estado_arquivo`
# roda a cada poll de `GET /llm/catalogo`, e sem cache re-hashearia cada `.gguf`
# (até ~2,4 GB) por item, por request — saturando disco/CPU e podendo colidir
# com um download em curso (C-14). A chave inclui `st_mtime_ns` e `st_size`:
# promover o download (`os.replace`) muda o mtime, então uma entrada velha nunca
# é servida para um arquivo novo; um arquivo trocado no lugar (mesmo tamanho,
# mtime diferente) também invalida a chave e força o re-hash. `baixar_modelo` e
# `definir_modelo_ativo` seguem verificando o hash de verdade (não passam por
# aqui): o cache é só para a leitura de estado do catálogo.
_CACHE_HASH: dict[tuple[str, int, int], str] = {}
_CACHE_HASH_LOCK = threading.Lock()


def _sha256_cacheado(caminho: Path) -> str:
    """SHA-256 de `caminho`, cacheado por (caminho, mtime_ns, tamanho).

    Só re-hasheia quando a tupla muda. Chama `_sha256_arquivo` pelo nome do
    módulo (não uma referência capturada) de propósito: mantém o ponto de
    monkeypatch dos testes."""
    st = caminho.stat()
    chave = (str(caminho), st.st_mtime_ns, st.st_size)
    with _CACHE_HASH_LOCK:
        em_cache = _CACHE_HASH.get(chave)
    if em_cache is not None:
        return em_cache
    digest = _sha256_arquivo(caminho)
    with _CACHE_HASH_LOCK:
        # Só o estado atual de cada caminho interessa: descarta chaves velhas do
        # mesmo arquivo (mtime/tamanho anteriores) para o cache não crescer.
        for velha in [k for k in _CACHE_HASH if k[0] == chave[0] and k != chave]:
            del _CACHE_HASH[velha]
        _CACHE_HASH[chave] = digest
    return digest


def estado_arquivo(item: ModeloCatalogo, ambiente: Mapping[str, str] | None = None,
                   destino_dir: Path | None = None) -> EstadoArquivo:
    """`"baixado"` só se o arquivo final existe E o hash bate (um arquivo
    corrompido/truncado não conta como baixado — evita falso positivo)."""
    final = caminho_final(item, ambiente, destino_dir)
    if final.is_file() and _sha256_cacheado(final) == item.sha256:
        return "baixado"
    return "ausente"


def listar_catalogo_com_estado(ambiente: Mapping[str, str] | None = None) -> list[dict]:
    """Catálogo + `estado_arquivo` de cada item — o `/llm/catalogo` do sidecar
    completa com o estado "baixando" (que só o job em memória do app.py sabe)."""
    return [
        {
            "id": item.id, "nome": item.nome, "descricao": item.descricao,
            "licenca": item.licenca, "tamanho_bytes": item.tamanho_bytes,
            # `arquivo` (nome final no disco, não sensível) deixa a GUI casar
            # o `modelo_ativo` (caminho completo) com o item do catálogo.
            "arquivo": item.arquivo,
            "estado": estado_arquivo(item, ambiente),
        }
        for item in catalogo_efetivo(ambiente)
    ]


# --------------------------------------------------------------- download
def _preparar_download_parcial(
    item: ModeloCatalogo,
    ambiente: Mapping[str, str] | None,
    destino_dir: Path | None,
) -> tuple[Path, int]:
    """Garante o diretório do `.parcial` e calcula o offset de retomada.

    Se já existir um `.parcial` de uma tentativa anterior, o offset é o
    tamanho já baixado (retomada via `Range`); senão começa do zero.
    """
    parcial = caminho_parcial(item, ambiente, destino_dir)
    parcial.parent.mkdir(parents=True, exist_ok=True)
    offset = parcial.stat().st_size if parcial.exists() else 0
    return parcial, offset


def _executar_download(
    item: ModeloCatalogo,
    parcial: Path,
    offset: int,
    cancelado: Callable[[], bool],
    progresso: Callable[[int, int], None] | None,
    abrir_url: Callable[..., Any],
) -> None:
    """Baixa o conteúdo para `parcial`, tentando retomar via `Range` a partir
    de `offset` — se o servidor não honrar (não devolve 206), recomeça do
    zero. `cancelado()` é checado a cada bloco (cancelamento cooperativo, sem
    `.parcial` incompleto virar lixo silencioso: ele fica no disco para
    retomar depois).
    """
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    req = urllib.request.Request(item.url, headers=headers)
    try:
        with abrir_url(req, timeout=_TIMEOUT_CONEXAO_S) as resp:
            retomando = offset > 0 and getattr(resp, "status", 200) == 206
            if offset and not retomando:
                offset = 0  # servidor ignorou o Range: recomeça do zero
            modo = "ab" if retomando else "wb"
            baixados = offset
            if progresso:
                progresso(baixados, item.tamanho_bytes)
            with open(parcial, modo) as f:
                while True:
                    if cancelado():
                        raise ModeloDownloadCancelado(
                            f"Download de {item.id!r} cancelado pelo usuário.")
                    bloco = resp.read(_TAMANHO_BLOCO)
                    if not bloco:
                        break
                    f.write(bloco)
                    baixados += len(bloco)
                    if progresso:
                        progresso(baixados, item.tamanho_bytes)
    except ModeloDownloadCancelado:
        raise
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise ModeloDownloadFalhou(
            f"Falha ao baixar {item.id!r}: {type(e).__name__}: {e}") from e


def _promover_download(parcial: Path, final: Path, item: ModeloCatalogo) -> None:
    """Verifica o SHA-256 do `.parcial` e só então promove para `final`.

    Hash divergente apaga o `.parcial` e levanta `ModeloHashInvalido` — nunca
    promove um arquivo corrompido.
    """
    hash_obtido = _sha256_arquivo(parcial)
    if not hmac.compare_digest(hash_obtido, item.sha256):
        parcial.unlink(missing_ok=True)
        raise ModeloHashInvalido(
            f"SHA-256 do download de {item.id!r} não confere "
            f"(esperado {item.sha256[:12]}…, obtido {hash_obtido[:12]}…) — "
            "arquivo descartado.")
    os.replace(parcial, final)


def baixar_modelo(
    item: ModeloCatalogo,
    *,
    ambiente: Mapping[str, str] | None = None,
    destino_dir: Path | None = None,
    cancelado: Callable[[], bool] = lambda: False,
    progresso: Callable[[int, int], None] | None = None,
    abrir_url: Callable[..., Any] = urllib.request.urlopen,
) -> Path:
    """Baixa `item.url` para `HF_MODELOS_DIR`, com retomada via `Range` e
    verificação de SHA-256 obrigatória antes de promover o arquivo (REQ-F-028).

    Única exceção de rede do app (REQ-NF-007): só roda por chamada explícita
    (o endpoint `/llm/baixar` só dispara com um clique do usuário). Escreve em
    `<arquivo>.parcial`; se já existir um `.parcial` de uma tentativa anterior,
    tenta retomar com o cabeçalho `Range` — se o servidor não honrar (não
    devolve 206), recomeça do zero. `cancelado()` é checado a cada bloco
    (cancelamento cooperativo, sem `.parcial` incompleto virar lixo silencioso:
    ele fica no disco para retomar depois). Hash divergente apaga o `.parcial`
    e levanta `ModeloHashInvalido` — nunca promove um arquivo corrompido.
    """
    final = caminho_final(item, ambiente, destino_dir)
    if final.is_file() and _sha256_arquivo(final) == item.sha256:
        return final  # idempotente: já baixado e íntegro

    parcial, offset = _preparar_download_parcial(item, ambiente, destino_dir)
    _executar_download(item, parcial, offset, cancelado, progresso, abrir_url)
    _promover_download(parcial, final, item)
    return final
