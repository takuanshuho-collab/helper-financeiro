"""
Guardrail de conteúdo (REQ-GRD-003 / REQ-GRD-004 / H3 / H6).

Duas funções:
  - detectar conteúdo indevido (recomendação de investimento, promessa de retorno);
  - garantir que o aviso legal acompanha toda saída.
"""
from __future__ import annotations

import re

from contracts import AnaliseAgente

AVISO_LEGAL = (
    "Aviso: esta análise é apoio à decisão com base nos dados informados. Não "
    "constitui aconselhamento financeiro ou de investimento personalizado. "
    "Regras de programas de renegociação e taxas de mercado mudam; confirme a "
    "vigência na fonte oficial antes de decidir."
)

# Padrões que NÃO devem aparecer numa ferramenta de gestão de dívida.
_PADROES_PROIBIDOS = [
    r"invist[ae]\s+em\b",
    r"compr[ae]\s+(?:a[çc][õo]es|ativos|criptomoedas?|bitcoin)",
    r"recomend[oa]\s+(?:o\s+)?investiment",
    r"retorno\s+garantid",
    r"lucro\s+garantid",
    r"rentabilidade\s+garantid",
    r"aplique\s+em\b",
]
_RE_PROIBIDO = re.compile("|".join(_PADROES_PROIBIDOS), re.IGNORECASE)


def detectar_conteudo_indevido(analise: AnaliseAgente) -> list[str]:
    """Retorna trechos que violam o escopo (investimento/garantia). Vazio = ok."""
    from guardrails.validador_numerico import coletar_textos  # reuso local

    violacoes: list[str] = []
    for texto in coletar_textos(analise):
        for m in _RE_PROIBIDO.finditer(texto):
            violacoes.append(m.group(0))
    return violacoes


def garantir_aviso(texto: str) -> str:
    """Anexa o aviso legal se ainda não estiver presente (H3)."""
    if "apoio à decisão" in texto:
        return texto
    return texto.rstrip() + "\n\n" + AVISO_LEGAL
