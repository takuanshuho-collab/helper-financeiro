"""
Rubricas do orçamento (ADR-0012, REQ-F-017) — T-1103, camada core.

O invariante em teste: campo com rubricas vale a SOMA das rubricas; campo sem
rubricas não é tocado. A validação de ancoragem (categoria/campo existem no
modelo do ADR-0008) também vive aqui — o sidecar só traduz ValueError em 422.
"""
import pytest

from core.rubricas import (
    CAMPOS_POR_CATEGORIA,
    Rubrica,
    aplicar_somas,
    comparar_orcamentos,
    somas_por_campo,
    validar_mes,
    validar_rubrica,
)


def _r(categoria="fixas", campo="contas_casa", nome="Conta de luz",
       valor=0.0, **kw):
    return Rubrica(categoria=categoria, campo_pai=campo, nome=nome,
                   valor=valor, **kw)


# ------------------------------------------------------------ campos válidos
def test_campos_derivam_do_modelo_do_adr_0008():
    # A tabela nasce dos dataclasses — nunca diverge do core.
    assert "salario_liquido" in CAMPOS_POR_CATEGORIA["renda"]
    assert "contas_casa" in CAMPOS_POR_CATEGORIA["fixas"]
    assert "mercado" in CAMPOS_POR_CATEGORIA["variaveis"]
    # Reserva/FGTS são saldos, não fluxos: fora do roll-up (ADR-0012).
    assert "reserva" not in CAMPOS_POR_CATEGORIA


def test_validar_categoria_desconhecida():
    with pytest.raises(ValueError, match="Categoria desconhecida"):
        validar_rubrica("investimentos", "acoes", "PETR4")


def test_validar_campo_desconhecido_na_categoria():
    # 'mercado' existe, mas em 'variaveis' — a ancoragem tem que bater.
    with pytest.raises(ValueError, match="Campo desconhecido"):
        validar_rubrica("fixas", "mercado", "Feira")


def test_validar_nome_vazio():
    with pytest.raises(ValueError, match="nome"):
        validar_rubrica("fixas", "contas_casa", "   ")


# ------------------------------------------------------------------- somas
def test_soma_agrupa_por_campo():
    somas = somas_por_campo([
        _r(nome="Conta de luz", valor=180.0),
        _r(nome="Internet", valor=120.0),
        _r(campo="moradia", nome="Aluguel", valor=1400.0),
        _r(categoria="renda", campo="renda_extra", nome="Freela", valor=800.0),
    ])
    assert somas == {
        "fixas": {"contas_casa": 300.0, "moradia": 1400.0},
        "renda": {"renda_extra": 800.0},
    }


def test_campo_sem_rubricas_nao_aparece():
    assert somas_por_campo([]) == {}
    somas = somas_por_campo([_r(valor=50.0)])
    assert "variaveis" not in somas
    assert "moradia" not in somas["fixas"]


def test_soma_arredonda_a_2_casas():
    somas = somas_por_campo([
        _r(nome="A", valor=0.1), _r(nome="B", valor=0.2),
    ])
    assert somas["fixas"]["contas_casa"] == 0.3  # sem 0.30000000000000004


def test_soma_valida_cada_rubrica():
    with pytest.raises(ValueError):
        somas_por_campo([_r(categoria="saldo")])


# ---------------------------------------------------------- aplicar ao perfil
PERFIL = {
    "renda": {"salario_liquido": 5000.0, "renda_extra": 0.0},
    "fixas": {"moradia": 1400.0, "contas_casa": 500.0},
    "variaveis": {"mercado": 800.0},
    "reserva_emergencia": 3000.0,
    "dividas": [{"credor": "Banco X"}],
}


def test_aplicar_substitui_so_os_campos_detalhados():
    novo = aplicar_somas(PERFIL, {"fixas": {"contas_casa": 300.0}})
    assert novo["fixas"]["contas_casa"] == 300.0   # detalhado: vira a soma
    assert novo["fixas"]["moradia"] == 1400.0      # sem rubricas: intacto
    assert novo["renda"]["salario_liquido"] == 5000.0
    assert novo["reserva_emergencia"] == 3000.0
    assert novo["dividas"] == [{"credor": "Banco X"}]


def test_aplicar_nao_muta_a_entrada():
    aplicar_somas(PERFIL, {"fixas": {"contas_casa": 1.0}})
    assert PERFIL["fixas"]["contas_casa"] == 500.0


def test_aplicar_com_secao_ausente_no_perfil():
    # Perfil mínimo (sem a seção): a soma cria a seção — nada explode.
    novo = aplicar_somas({}, {"renda": {"renda_extra": 200.0}})
    assert novo["renda"]["renda_extra"] == 200.0


# ------------------------------------- histórico mensal (ADR-0013, T-1201)
def test_validar_mes():
    validar_mes("2026-07")  # ok
    for ruim in ("2026-13", "2026-0", "26-07", "julho", "2026-07-01"):
        with pytest.raises(ValueError, match="Competência inválida"):
            validar_mes(ruim)


def test_comparar_orcamentos_variacao_por_campo():
    antes = {"variaveis": {"mercado": 800.0}}
    depois = {"variaveis": {"mercado": 900.0}}
    comp = comparar_orcamentos(antes, depois)

    variaveis = next(s for s in comp["secoes"] if s["categoria"] == "variaveis")
    mercado = next(c for c in variaveis["campos"] if c["campo"] == "mercado")
    # "Seu mercado subiu 12,5%": 800 → 900.
    assert mercado["antes"] == 800.0
    assert mercado["depois"] == 900.0
    assert mercado["delta"] == 100.0
    assert mercado["variacao_pct"] == 0.125
    assert mercado["rotulo"] == "Mercado"
    # A seção agrega os campos (aqui só há um).
    assert variaveis["antes"] == 800.0
    assert variaveis["delta"] == 100.0


def test_comparar_orcamentos_sem_base_pct_none():
    # Campo que nasceu neste mês: delta existe, % não (sem divisão por zero).
    comp = comparar_orcamentos({}, {"fixas": {"saude": 250.0}})
    fixas = next(s for s in comp["secoes"] if s["categoria"] == "fixas")
    saude = next(c for c in fixas["campos"] if c["campo"] == "saude")
    assert saude["delta"] == 250.0
    assert saude["variacao_pct"] is None


def test_comparar_orcamentos_omite_campos_zerados():
    comp = comparar_orcamentos({"fixas": {"moradia": 1400.0}},
                               {"fixas": {"moradia": 1400.0}})
    fixas = next(s for s in comp["secoes"] if s["categoria"] == "fixas")
    assert [c["campo"] for c in fixas["campos"]] == ["moradia"]
    assert fixas["campos"][0]["delta"] == 0.0
    # As 3 seções sempre existem (mesmo vazias), para a GUI ser estável.
    assert [s["categoria"] for s in comp["secoes"]] == [
        "renda", "fixas", "variaveis"]
