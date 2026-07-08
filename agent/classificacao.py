"""
Classificação de lançamentos de extrato por LLM local (ADR-0014, REQ-F-021).

O modelo SÓ ROTULA: recebe os grupos numerados (nome do estabelecimento
normalizado + natureza — sem valores, sem datas) e devolve
`índice → categoria/campo_pai`. Todo número que o usuário verá vem do parser
determinístico (`core/extrato.py`) — H1 por construção.

Travas determinísticas sobre a resposta do modelo:
1. índice precisa existir na lista enviada (e sem repetição);
2. categoria/campo precisam existir em `CAMPOS_POR_CATEGORIA` (core);
3. natureza coerente — crédito só classifica em `renda`; débito só em
   `fixas`/`variaveis`.
Item que viole qualquer trava é DESCARTADO (o grupo volta "não classificado"
para o usuário decidir no painel de revisão).

H2 por construção: classificação roda SOMENTE em provider local (loopback) —
extrato bancário é a PII mais sensível do app. Sem LLM disponível, o fluxo
degrada para classificação manual (P8): mapa vazio + motivos.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import ValidationError

from contracts import ClassificacaoExtrato
from core.rubricas import CAMPOS_POR_CATEGORIA, ROTULO_CAMPO

from .config import ConfigAgente, carregar_config
from .prompts import SYSTEM_PROMPT_CLASSIFICACAO, montar_prompt_classificacao
from .provider import NUM_CTX, _post_json

# Classificação quer determinismo, não criatividade.
TEMPERATURA_CLASSIFICACAO = 0.0
# REQ-LLM-002 (mesma régua da extração): no máximo 1 recuperação.
MAX_TENTATIVAS = 2

# Natureza do lançamento → categorias permitidas (regra 2 do prompt,
# reimposta aqui em código — a LLM não decide invariante).
_CATEGORIAS_POR_NATUREZA = {
    "credito": ("renda",),
    "debito": ("fixas", "variaveis"),
}


class Classificador(Protocol):
    def classificar(
        self, grupos: Sequence[tuple[str, str]]
    ) -> ClassificacaoExtrato: ...


def _opcoes_de_campos() -> str:
    """Tabela `categoria/campo — rótulo` que o prompt oferece ao modelo."""
    linhas = []
    for categoria, campos in CAMPOS_POR_CATEGORIA.items():
        for campo in campos:
            linhas.append(
                f"- {categoria}/{campo} — {ROTULO_CAMPO[categoria][campo]}")
    return "\n".join(linhas)


def _mensagens(grupos: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT_CLASSIFICACAO},
        {"role": "user",
         "content": montar_prompt_classificacao(list(grupos),
                                                _opcoes_de_campos())},
    ]


class OllamaClassificador:
    """Classificação via API nativa do Ollama com gramática restrita."""

    def __init__(self, cfg: ConfigAgente):
        self.cfg = cfg
        raiz = cfg.base_url.rstrip("/").removesuffix("/v1")
        self.url = f"{raiz}/api/chat"

    def classificar(
        self, grupos: Sequence[tuple[str, str]]
    ) -> ClassificacaoExtrato:
        resposta = _post_json(self.url, {
            "model": self.cfg.model,
            "messages": _mensagens(grupos),
            "stream": False,
            "format": ClassificacaoExtrato.model_json_schema(),
            "options": {"temperature": TEMPERATURA_CLASSIFICACAO,
                        "num_ctx": NUM_CTX},
        }, headers={}, timeout_s=self.cfg.timeout_s)
        return ClassificacaoExtrato.model_validate_json(
            resposta["message"]["content"])


class OpenAICompatClassificador:
    """Classificação via endpoint OpenAI-compatible LOCAL (LM Studio etc.).

    Mesmas escolhas do `OpenAICompatExtrator`: `response_format` json_schema
    sem `strict` (compatibilidade entre servidores locais); saída fora do
    schema vira recuperação (1 retry) e depois degradação (P8).
    """

    def __init__(self, cfg: ConfigAgente):
        self.cfg = cfg
        self.url = cfg.base_url.rstrip("/") + "/chat/completions"

    def classificar(
        self, grupos: Sequence[tuple[str, str]]
    ) -> ClassificacaoExtrato:
        headers = ({"Authorization": f"Bearer {self.cfg.api_key}"}
                   if self.cfg.api_key else {})
        resposta = _post_json(self.url, {
            "model": self.cfg.model,
            "messages": _mensagens(grupos),
            "temperature": TEMPERATURA_CLASSIFICACAO,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "ClassificacaoExtrato",
                    "schema": ClassificacaoExtrato.model_json_schema()},
            },
        }, headers=headers, timeout_s=self.cfg.timeout_s)
        conteudo = resposta["choices"][0]["message"]["content"]
        return ClassificacaoExtrato.model_validate_json(conteudo)


# Mesmo racional da extração (ADR-0010): Ollama fala a API nativa; qualquer
# outro servidor local fala o dialeto OpenAI-compatible.
_PROVIDERS_OLLAMA = {"local", "ollama"}


def obter_classificador(cfg: ConfigAgente) -> Classificador:
    """Fábrica. Classificação exige endpoint LOCAL (loopback): os nomes dos
    lançamentos vêm do extrato bancário e nunca saem da máquina (H2)."""
    if not cfg.endpoint_local:
        raise RuntimeError(
            f"CLASSIFICACAO_LOCAL_ONLY: classificação exige endpoint local "
            f"(loopback); base_url='{cfg.base_url}' é remoto (H2 — o extrato "
            f"contém PII).")
    if cfg.provider.strip().lower() in _PROVIDERS_OLLAMA:
        return OllamaClassificador(cfg)
    return OpenAICompatClassificador(cfg)


@dataclass(frozen=True)
class ResultadoClassificacao:
    """`por_indice` mapeia grupo → (categoria, campo_pai); o resto é auditoria.

    `motivos` não-vazio = degradação (P8): a GUI mostra o porquê e o usuário
    classifica manualmente; `descartes` lista itens da LLM que violaram as
    travas (o grupo correspondente volta sem rótulo).
    """

    por_indice: dict[int, tuple[str, str]] = field(default_factory=dict)
    descartes: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)


def _validar_itens(classificacao: ClassificacaoExtrato,
                   grupos: Sequence[tuple[str, str]]) -> ResultadoClassificacao:
    """Reimpõe as travas em código — nada da LLM passa sem verificação."""
    por_indice: dict[int, tuple[str, str]] = {}
    descartes: list[str] = []
    for item in classificacao.itens:
        if not 0 <= item.indice < len(grupos):
            descartes.append(f"{item.indice}:INDICE_INVALIDO")
            continue
        if item.indice in por_indice:
            descartes.append(f"{item.indice}:INDICE_REPETIDO")
            continue
        campos = CAMPOS_POR_CATEGORIA.get(item.categoria)
        if campos is None or item.campo_pai not in campos:
            descartes.append(
                f"{item.indice}:CAMPO_INVALIDO:{item.categoria}/{item.campo_pai}")
            continue
        natureza = grupos[item.indice][1]
        if item.categoria not in _CATEGORIAS_POR_NATUREZA.get(natureza, ()):
            descartes.append(f"{item.indice}:NATUREZA:{natureza}")
            continue
        por_indice[item.indice] = (item.categoria, item.campo_pai)
    return ResultadoClassificacao(por_indice=por_indice, descartes=descartes)


def classificar_grupos(grupos: Sequence[tuple[str, str]],
                       cfg: ConfigAgente | None = None,
                       classificador: Classificador | None = None,
                       ) -> ResultadoClassificacao:
    """Classifica os grupos do extrato; degrada com motivo, nunca levanta.

    `grupos` são pares (nome normalizado, natureza) na ordem do parse —
    os índices da resposta apontam para essa lista.
    """
    if not grupos:
        return ResultadoClassificacao()
    if classificador is None:
        try:
            classificador = obter_classificador(cfg or carregar_config())
        except Exception as e:  # noqa: BLE001 — P8: sem LLM ⇒ classificação manual
            return ResultadoClassificacao(
                motivos=[f"ERRO_CONFIG:{type(e).__name__}"])

    motivos: list[str] = []
    for _ in range(MAX_TENTATIVAS):
        try:
            classificacao = classificador.classificar(grupos)
        except ValidationError:
            motivos = ["REQ-LLM-002:SCHEMA"]
            continue
        except Exception as e:  # noqa: BLE001 — P8: falhou ⇒ manual, com o motivo
            motivos = [f"ERRO_PROVIDER:{type(e).__name__}"]
            continue
        return _validar_itens(classificacao, grupos)
    return ResultadoClassificacao(motivos=motivos)
