"""
Adaptação para exibição local (M3, T-301/T-302/T-305).

Este módulo é a FRONTEIRA da desanonimização: os tokens (`CREDOR_n`) viajam
pelo LLM e pelos guardrails; os nomes reais só voltam aqui, na hora de mostrar
ao usuário — via `MapaAnonimizacao`, que vive apenas em memória (REQ-SEC-003).

Ele não conhece tkinter nem python-docx: produz estruturas prontas (`SecaoIA`)
e texto plano que as cascas (gui/, outputs/) apenas renderizam. Assim a lógica
fica testável offline enquanto a GUI permanece uma casca fina.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from contracts import PassoRoteiroIA, ResultadoAnalise, SecaoIA
from guardrails.pii import MapaAnonimizacao, desanonimizar

# Rótulo exigido pelo T-302 (P2: transparência de que houve IA no meio).
ROTULO_IA = "assistido por IA"

_ABORDAGENS = {
    "quitacao": "Quitação à vista",
    "portabilidade": "Portabilidade",
    "reducao": "Redução de taxa / renegociação",
}


def preparar_exibicao(resultado: ResultadoAnalise, mapa: MapaAnonimizacao) -> SecaoIA:
    """Materializa a seção de IA com os nomes reais restaurados."""
    if resultado.analise is None:
        return SecaoIA(modo=resultado.modo,
                       motivos=list(resultado.guardrails_violados),
                       aviso_legal=resultado.aviso_legal)

    def real(texto: str) -> str:
        return desanonimizar(texto, mapa)

    a = resultado.analise
    prioridades = [f"{p.ordem}. {real(p.credor_token)} — {real(p.justificativa)}"
                   for p in sorted(a.prioridades, key=lambda p: p.ordem)]
    roteiro = [
        PassoRoteiroIA(
            credor=real(p.credor_token),
            abordagem=_ABORDAGENS.get(p.abordagem, p.abordagem),
            argumentos=[real(x) for x in p.argumentos],
            concessoes=[real(x) for x in p.concessoes_possiveis],
        )
        for p in a.roteiro_negociacao
    ]
    return SecaoIA(
        modo=resultado.modo,
        motivos=list(resultado.guardrails_violados),
        sumario=real(a.sumario_executivo),
        diagnostico=real(a.diagnostico_interpretado),
        prioridades=prioridades,
        roteiro=roteiro,
        alertas=[real(x) for x in a.alertas_risco],
        confianca=a.confianca,
        aviso_legal=resultado.aviso_legal,
    )


def formatar_secao_ia(secao: SecaoIA) -> str:
    """Texto plano da seção de IA para o painel da GUI (T-302/T-304)."""
    if secao.modo != "completo":
        linhas = [
            "⚠ MODO DEGRADADO — a análise de IA não está disponível agora.",
            "Vale o diagnóstico determinístico acima (que é sempre a fonte oficial dos números).",
        ]
        if secao.motivos:
            linhas.append("Motivos registrados: " + ", ".join(secao.motivos))
        return "\n".join(linhas)

    linhas = [
        f"ANÁLISE DO AGENTE — conteúdo {ROTULO_IA}",
        "=" * 60,
        "",
        "SUMÁRIO EXECUTIVO",
        secao.sumario,
        "",
        "DIAGNÓSTICO INTERPRETADO",
        secao.diagnostico,
    ]
    if secao.prioridades:
        linhas += ["", "PRIORIDADES SUGERIDAS"] + [f"  {p}" for p in secao.prioridades]
    if secao.roteiro:
        linhas += ["", "ROTEIRO DE NEGOCIAÇÃO"]
        for passo in secao.roteiro:
            linhas.append(f"  • {passo.credor} — {passo.abordagem}")
            linhas += [f"      - {arg}" for arg in passo.argumentos]
            if passo.concessoes:
                linhas.append("      Concessões possíveis: " + "; ".join(passo.concessoes))
    if secao.alertas:
        linhas += ["", "ALERTAS DE RISCO"] + [f"  ⚠ {a}" for a in secao.alertas]
    linhas += ["", f"Confiança auto-avaliada do modelo: {secao.confianca:.0%}"]
    if secao.aviso_legal:
        linhas += ["", secao.aviso_legal]
    return "\n".join(linhas)


# ---------------------------------------------------- extração → formulário
# Rótulos que a tela de confirmação (T-305) mostra, na ordem do formulário
# da aba Dívidas.
ROTULOS_EXTRACAO = {
    "credor": "Credor",
    "tipo": "Tipo",
    "saldo": "Saldo devedor (R$)",
    "taxa": "Taxa mensal (%)",
    "parcela": "Parcela (R$)",
    "restantes": "Parcelas restantes",
}


def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def _num_form(valor: float) -> str:
    """Número no formato que o formulário espera (vírgula decimal)."""
    return f"{valor:.2f}".replace(".", ",")


# Do texto livre do documento para a lista fechada TIPOS_DIVIDA da aba Dívidas.
# Ordem importa: "empréstimo consignado" deve casar "consignad" antes de
# "emprestimo". Sem casamento ⇒ "Outro" (o usuário sempre confere).
_REGRAS_TIPO = [
    ("consignad", "Consignado"),
    ("cartao", "Cartão de crédito"),
    ("cheque", "Cheque especial"),
    ("cdc", "CDC (Crédito Direto ao Consumidor)"),
    ("credito direto", "CDC (Crédito Direto ao Consumidor)"),
    ("financiamento", "Financiamento"),
    ("pessoal", "Empréstimo pessoal"),
    ("emprestimo", "Empréstimo pessoal"),
]


def mapear_tipo_divida(texto: str | None) -> str:
    if not texto:
        return "Outro"
    normalizado = re.sub(r"\s+", " ", _sem_acentos(texto)).casefold()
    for chave, rotulo in _REGRAS_TIPO:
        if chave in normalizado:
            return rotulo
    return "Outro"


def campos_para_formulario(campos: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Converte o payload do `interrupt` (ExtracaoContrato.model_dump()) em
    campos prontos para a tela de confirmação: valor no formato do formulário
    (vírgula decimal, taxa em %), citação de origem e confiança.

    Campos ausentes (None) são omitidos — a tela só mostra o que tem fonte.
    """
    def item(campo: dict[str, Any], valor: str) -> dict[str, str]:
        return {
            "valor": valor,
            "fonte": str(campo.get("trecho_fonte", "")),
            "confianca": f"{float(campo.get('confianca', 0.0)):.0%}",
        }

    form: dict[str, dict[str, str]] = {}
    if c := campos.get("credor"):
        form["credor"] = item(c, str(c["valor"]).strip())
    if c := campos.get("tipo"):
        form["tipo"] = item(c, mapear_tipo_divida(str(c["valor"])))
    if c := campos.get("saldo_devedor"):
        form["saldo"] = item(c, _num_form(float(c["valor"])))
    if c := campos.get("taxa_mensal"):
        # O contrato guarda FRAÇÃO (0.02); o formulário fala em % (2,00).
        form["taxa"] = item(c, _num_form(float(c["valor"]) * 100))
    if c := campos.get("parcela"):
        form["parcela"] = item(c, _num_form(float(c["valor"])))
    if c := campos.get("parcelas_restantes"):
        form["restantes"] = item(c, str(int(float(c["valor"]))))
    return form
