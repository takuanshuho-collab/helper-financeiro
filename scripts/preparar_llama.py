"""Prepara o binário `llama-server` (llama.cpp) para o empacotamento (T-1703, ADR-0016 §E).

O runtime embarcado (`sidecar/runtime_llm.py`) espera UM binário em
`resources/llama/llama-server(.exe)` — relativo ao executável congelado no
pacote, ou à raiz do repositório em desenvolvimento. Este script materializa
esse diretório a partir de um release **oficial** do llama.cpp
(`ggml-org/llama.cpp` no GitHub), baixando, verificando e extraindo as DLLs que
acompanham o servidor. É o análogo do `scripts/preparar_ocr.py` para a LLM.

## Decisões (para o revisor)

- **Variante padrão: Vulkan.** O zip `bin-win-vulkan-x64` traz, além do
  `ggml-vulkan.dll`, TODOS os backends de CPU (`ggml-cpu-*.dll`): num PC com
  GPU Vulkan (a GPU-alvo é uma NVIDIA de 4 GB) ele acelera; sem GPU/driver
  Vulkan, o llama.cpp cai no backend de CPU sozinho. Um único binário cobre os
  dois mundos (ADR-0016 §E: "build CPU + Vulkan… sem exigir CUDA"), o que
  respeita a convenção de um binário só do `runtime_llm.py`. A variante `cpu`
  (menor, sem `ggml-vulkan.dll`) fica disponível via `--variante cpu` para a
  rara máquina onde o loader Vulkan atrapalhe — nunca é o padrão.

- **Só o necessário para servir.** Extraímos os `*.dll` (o `llama-server.exe`
  é um lançador fino que carrega `llama-server-impl.dll` + os `ggml*.dll`) e o
  próprio `llama-server.exe`; os outros executáveis do zip (`llama-cli`,
  `llama-bench`, …) não entram — o runtime só sobe o servidor.

- **Fora do git (REQ-NF-006 análogo do OCR):** os binários são grandes
  (~130 MB descompactados) e vivem em `resources/llama/`, que está no
  `.gitignore`. Rede é usada **só aqui, no build**; a máquina do usuário nunca
  baixa o binário. Idempotente: se o `llama-server.exe` já está lá com a mesma
  origem (marcador `.origem.json`), não rebaixa.

- **Verificação:** SHA-256 **e** tamanho do zip travados no código (conferidos
  em 2026-07 contra o release `b9966`); hash divergente aborta sem extrair
  (nunca empacota binário adulterado). É a mesma disciplina do catálogo de
  modelos (`sidecar/gestor_modelos.py`).

Uso (antes do PyInstaller / electron-builder):

    uv run python scripts/preparar_llama.py            # variante vulkan (padrão)
    uv run python scripts/preparar_llama.py --variante cpu
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Release oficial fixado (ggml-org/llama.cpp). Subir de versão é uma decisão
# consciente: bump da TAG + recomputar os SHA-256/tamanhos abaixo.
TAG_LLAMA = "b9966"
_URL_BASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG_LLAMA}"

NOME_BINARIO = "llama-server.exe"  # Windows-only (o app é Windows; ADR-0009)
_TAMANHO_BLOCO = 1024 * 1024


@dataclass(frozen=True)
class AssetLlama:
    """Um zip de release do llama.cpp, com origem e integridade travadas."""

    variante: str
    nome_zip: str
    url: str
    sha256: str
    tamanho_bytes: int


def _asset(variante: str, nome_zip: str, sha256: str, tamanho: int) -> AssetLlama:
    return AssetLlama(variante, nome_zip, f"{_URL_BASE}/{nome_zip}", sha256, tamanho)


# SHA-256 e tamanhos conferidos em 2026-07 contra o release b9966 (baixados uma
# vez, hasheados com `sha256sum`).
ASSETS: dict[str, AssetLlama] = {
    "vulkan": _asset(
        "vulkan",
        "llama-b9966-bin-win-vulkan-x64.zip",
        "db5a32a02222e3d77272745ad18b378cb33023ef001cd37d491183870e34291a",
        32898388,
    ),
    "cpu": _asset(
        "cpu",
        "llama-b9966-bin-win-cpu-x64.zip",
        "a2e791df47c8abd09e23f85a00699d6d6552445f6bba21e810263eaeefbf672a",
        18211851,
    ),
}

VARIANTE_PADRAO = "vulkan"
_MARCADOR = ".origem.json"  # registra variante+tag+sha do que está extraído


class ErroPrepararLlama(RuntimeError):
    """Falha ao baixar/verificar/extrair o binário — aborta o build cedo."""


def raiz_repo() -> Path:
    """Raiz do repositório (um nível acima de `scripts/`)."""
    return Path(__file__).resolve().parent.parent


def diretorio_llama(raiz: Path | None = None) -> Path:
    """Destino do binário: `<raiz>/resources/llama` (a convenção do
    `runtime_llm.resolver_binario_llama`, também usada como *extraResource*)."""
    base = raiz if raiz is not None else raiz_repo()
    return base / "resources" / "llama"


def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(_TAMANHO_BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def _deve_manter(nome: str) -> bool:
    """Arquivos do zip que vão para `resources/llama`: as DLLs (runtime do
    servidor) e só o `llama-server.exe` (não os demais executáveis)."""
    minusculo = nome.lower()
    return minusculo.endswith(".dll") or minusculo == NOME_BINARIO


def _ja_preparado(destino: Path, asset: AssetLlama) -> bool:
    """`True` se o binário já está extraído com a MESMA origem (idempotência)."""
    binario = destino / NOME_BINARIO
    marcador = destino / _MARCADOR
    if not binario.is_file() or not marcador.is_file():
        return False
    try:
        dados = json.loads(marcador.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return dados.get("sha256") == asset.sha256 and dados.get("variante") == asset.variante


def baixar_zip(
    asset: AssetLlama,
    destino_zip: Path,
    *,
    abrir_url: Callable[..., Any] = urllib.request.urlopen,
    verificar: bool = True,
) -> Path:
    """Baixa o zip do release para `destino_zip` e confere tamanho + SHA-256.

    Escreve em `.parcial` e só promove (`os.replace`) após o hash bater — nunca
    deixa um zip corrompido no lugar do bom. `verificar=False` é uma válvula de
    escape para dev (pular a checagem NÃO é permitido no build oficial).
    """
    destino_zip.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino_zip.with_name(destino_zip.name + ".parcial")
    req = urllib.request.Request(asset.url)
    try:
        with abrir_url(req, timeout=300) as resp, open(parcial, "wb") as f:
            f.writelines(iter(lambda: resp.read(_TAMANHO_BLOCO), b""))
    except OSError as e:
        raise ErroPrepararLlama(f"Falha ao baixar {asset.nome_zip}: {e}") from e

    if verificar:
        tamanho = parcial.stat().st_size
        if tamanho != asset.tamanho_bytes:
            parcial.unlink(missing_ok=True)
            raise ErroPrepararLlama(
                f"Tamanho de {asset.nome_zip} não confere "
                f"(esperado {asset.tamanho_bytes}, obtido {tamanho}) — descartado.")
        obtido = _sha256_arquivo(parcial)
        if not hmac.compare_digest(obtido, asset.sha256):
            parcial.unlink(missing_ok=True)
            raise ErroPrepararLlama(
                f"SHA-256 de {asset.nome_zip} não confere "
                f"(esperado {asset.sha256[:12]}…, obtido {obtido[:12]}…) — descartado.")
    os.replace(parcial, destino_zip)
    return destino_zip


def extrair_binario(zip_path: Path, destino: Path) -> list[str]:
    """Extrai as DLLs + `llama-server.exe` do zip, achatados em `destino`.

    Achata a estrutura (o release traz os arquivos na raiz do zip, mas
    normalizamos por `Path(nome).name` por segurança contra caminhos com pasta).
    Devolve a lista de arquivos extraídos.
    """
    destino.mkdir(parents=True, exist_ok=True)
    extraidos: list[str] = []
    with zipfile.ZipFile(zip_path) as z:
        for nome in z.namelist():
            base = Path(nome).name
            if not base or not _deve_manter(base):
                continue
            with z.open(nome) as origem, open(destino / base, "wb") as saida:
                saida.write(origem.read())
            extraidos.append(base)
    return extraidos


def preparar(
    variante: str = VARIANTE_PADRAO,
    *,
    destino: Path | None = None,
    asset: AssetLlama | None = None,
    abrir_url: Callable[..., Any] = urllib.request.urlopen,
    verificar: bool = True,
    forcar: bool = False,
) -> Path:
    """Deixa `resources/llama` pronto com o `llama-server` e devolve seu caminho.

    Idempotente (a menos de `forcar`): se o binário da mesma origem já está lá,
    não rebaixa. Aborta com `ErroPrepararLlama` se, ao final, o binário não
    existir (build não deve seguir sem ele).
    """
    escolhido = asset if asset is not None else ASSETS.get(variante)
    if escolhido is None:
        raise ErroPrepararLlama(
            f"Variante desconhecida: {variante!r} (use {', '.join(ASSETS)}).")
    alvo = destino if destino is not None else diretorio_llama()
    binario = alvo / NOME_BINARIO

    if not forcar and _ja_preparado(alvo, escolhido):
        return binario

    zip_path = alvo / escolhido.nome_zip
    baixar_zip(escolhido, zip_path, abrir_url=abrir_url, verificar=verificar)
    extraidos = extrair_binario(zip_path, alvo)
    zip_path.unlink(missing_ok=True)

    if not binario.is_file():
        raise ErroPrepararLlama(
            f"{NOME_BINARIO} não foi encontrado no zip {escolhido.nome_zip} "
            f"(extraídos: {len(extraidos)} arquivos).")
    (alvo / _MARCADOR).write_text(
        json.dumps(
            {"variante": escolhido.variante, "tag": TAG_LLAMA,
             "sha256": escolhido.sha256, "arquivos": sorted(extraidos)},
            ensure_ascii=False, indent=2),
        encoding="utf-8")
    return binario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepara o llama-server para o empacotamento.")
    parser.add_argument(
        "--variante", choices=sorted(ASSETS), default=VARIANTE_PADRAO,
        help="Variante do binário (padrão: vulkan, com fallback de CPU embutido).")
    parser.add_argument(
        "--forcar", action="store_true", help="Rebaixa mesmo se já preparado.")
    args = parser.parse_args(argv)

    destino = diretorio_llama()
    print(f"Preparando llama-server (variante {args.variante}) em: {destino}")
    try:
        binario = preparar(args.variante, forcar=args.forcar)
    except ErroPrepararLlama as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    tamanho = binario.stat().st_size
    dlls = len(list(destino.glob("*.dll")))
    print(f"  [ok] {binario.name} ({tamanho} bytes) + {dlls} DLLs")
    print("llama-server pronto para o empacotamento.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
