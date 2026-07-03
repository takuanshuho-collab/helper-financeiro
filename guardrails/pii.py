"""
Guardrail de privacidade (REQ-GRD-002, REQ-SEC-003).

Substitui dados pessoais por tokens estáveis antes de qualquer chamada ao LLM.
O mapa token→valor real vive SOMENTE em memória, durante a execução.

Analogia: é como cobrir os nomes num documento com etiquetas numeradas antes de
mostrá-lo a um terceiro; só você tem a legenda para descolar as etiquetas depois.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MapaAnonimizacao:
    """Legenda reversível token ↔ valor real (fica apenas em memória)."""
    para_token: dict[str, str] = field(default_factory=dict)   # real -> token
    para_real: dict[str, str] = field(default_factory=dict)    # token -> real

    def registrar(self, real: str, token: str) -> None:
        self.para_token[real] = token
        self.para_real[token] = real


def anonimizar_credores(nomes: list[str]) -> tuple[dict[str, str], MapaAnonimizacao]:
    """Gera tokens CREDOR_1..n para uma lista de credores, preservando a ordem.

    Retorna (real->token, mapa).
    """
    mapa = MapaAnonimizacao()
    for i, nome in enumerate(nomes, start=1):
        token = f"CREDOR_{i}"
        mapa.registrar(nome, token)
    return dict(mapa.para_token), mapa


# CPF em formatos comuns: 000.000.000-00 ou 00000000000
_RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def contem_pii(texto: str, mapa: MapaAnonimizacao) -> list[str]:
    """Detecta vazamento de PII num texto que está prestes a sair da máquina.

    Retorna a lista de PII encontrada (nomes reais de credores ou CPF). Lista
    vazia = seguro para enviar. Usado como checagem final antes de chamadas cloud.
    """
    achados: list[str] = []
    for real in mapa.para_token:
        if real and real in texto:
            achados.append(real)
    if _RE_CPF.search(texto):
        achados.append("CPF")
    return achados


def desanonimizar(texto: str, mapa: MapaAnonimizacao) -> str:
    """Recoloca os nomes reais no texto retornado pelo LLM (para exibição local)."""
    for token, real in mapa.para_real.items():
        texto = texto.replace(token, real)
    return texto
