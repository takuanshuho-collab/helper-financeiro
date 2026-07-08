"""
Parser determinístico de extratos CSV (ADR-0014, REQ-F-021) — T-1301.

O invariante em teste: todo número que chega ao usuário nasceu AQUI, do
texto do CSV — a LLM (T-1302) só rotula grupos, nunca produz valor. Os
cenários espelham os exports comuns de bancos BR: separador ','/';'/tab,
valor '1.234,56' e '1234.56', data 'DD/MM/AAAA' e 'AAAA-MM-DD', com e sem
cabeçalho. Linha ilegível vira aviso, nunca exceção.
"""
from core.extrato import (
    _parse_linha_livre,
    decodificar_csv,
    ler_extrato_csv,
    ler_extrato_ocr,
    normalizar_estabelecimento,
)

# Estilo "extrato de conta" (Nubank): vírgula, data BR, valor com ponto
# decimal, sinais mistos (negativo = débito).
CSV_CONTA = """\
Data,Valor,Identificador,Descrição
05/06/2026,-180.50,abc-1,Conta de luz Enel
07/06/2026,-92.30,abc-2,UBER *TRIP 8291
15/06/2026,-45.10,abc-3,UBER *TRIP 4415
30/06/2026,3500.00,abc-4,Salário ACME LTDA
"""

# Estilo "banco tradicional": ponto-e-vírgula, valor brasileiro.
CSV_PONTO_E_VIRGULA = """\
data lançamento;histórico;valor (R$)
02/06/2026;PIX ENVIADO PADARIA SAO JOAO;-1.234,56
10/06/2026;TED RECEBIDA;2.000,00
"""

# Estilo "fatura de cartão" (export en): ISO, tudo positivo = tudo débito.
CSV_FATURA = """\
date,title,amount
2026-06-03,Mercado Bom Preço,412.77
2026-06-18,Mercado Bom Preço,388.10
2026-06-20,Netflix.com,55.90
"""


def test_extrato_de_conta_com_sinais_mistos():
    extrato = ler_extrato_csv(CSV_CONTA)
    assert extrato.avisos == ()
    assert len(extrato.lancamentos) == 4
    luz = extrato.lancamentos[0]
    assert (luz.data, luz.valor, luz.natureza) == (
        "2026-06-05", -180.50, "debito")
    salario = extrato.lancamentos[3]
    assert (salario.valor, salario.natureza) == (3500.00, "credito")
    assert extrato.competencia_sugerida == "2026-06"


def test_agrupamento_por_estabelecimento_normalizado():
    extrato = ler_extrato_csv(CSV_CONTA)
    uber = next(g for g in extrato.grupos if g.nome == "Uber Trip")
    # 92,30 + 45,10 — os códigos '8291'/'4415' não separam o grupo.
    assert uber.total == 137.40
    assert uber.quantidade == 2
    assert uber.natureza == "debito"
    # Grupos saem por total decrescente: o salário lidera.
    assert extrato.grupos[0].total == 3500.00


def test_separador_ponto_e_virgula_e_valor_brasileiro():
    extrato = ler_extrato_csv(CSV_PONTO_E_VIRGULA)
    assert extrato.avisos == ()
    pix = extrato.lancamentos[0]
    assert pix.valor == -1234.56
    assert pix.natureza == "debito"
    assert extrato.lancamentos[1].natureza == "credito"


def test_fatura_toda_positiva_vira_debito():
    extrato = ler_extrato_csv(CSV_FATURA)
    assert {lanc.natureza for lanc in extrato.lancamentos} == {"debito"}
    mercado = next(g for g in extrato.grupos if g.nome == "Mercado Bom Preço")
    assert mercado.total == 800.87
    assert mercado.quantidade == 2
    assert extrato.competencia_sugerida == "2026-06"


def test_sem_cabecalho_infere_as_colunas_pelo_conteudo():
    extrato = ler_extrato_csv("05/06/2026,Conta de luz Enel,-180.50\n"
                              "30/06/2026,Salário ACME,3500.00\n")
    assert extrato.avisos == ()
    assert extrato.lancamentos[0].data == "2026-06-05"
    assert extrato.lancamentos[0].descricao == "Conta de luz Enel"
    assert extrato.lancamentos[0].valor == -180.50


def test_linhas_ilegiveis_viram_aviso_nunca_excecao():
    extrato = ler_extrato_csv("Data,Descrição,Valor\n"
                              "05/06/2026,Conta de luz,-180.50\n"
                              "06/06/2026,Sem valor,abc\n"
                              "07/06/2026,Valor zerado,0\n"
                              "08/06/2026\n")
    assert len(extrato.lancamentos) == 1
    assert len(extrato.avisos) == 3
    assert any("valor ilegível" in aviso for aviso in extrato.avisos)
    assert any("valor zerado" in aviso for aviso in extrato.avisos)
    assert any("colunas faltando" in aviso for aviso in extrato.avisos)


def test_arquivo_vazio_e_irreconhecivel():
    assert ler_extrato_csv("").avisos == ("Arquivo vazio.",)
    assert ler_extrato_csv("   \n\n").lancamentos == ()
    sem_colunas = ler_extrato_csv("a\nb\nc\n")
    assert sem_colunas.lancamentos == ()
    assert "Não reconheci" in sem_colunas.avisos[0]


def test_competencia_e_a_moda_das_datas():
    extrato = ler_extrato_csv("Data,Descrição,Valor\n"
                              "30/05/2026,Compra,-10.00\n"
                              "02/06/2026,Compra,-10.00\n"
                              "03/06/2026,Compra,-10.00\n")
    assert extrato.competencia_sugerida == "2026-06"
    sem_data = ler_extrato_csv("Descrição,Valor\nCompra,-10.00\n")
    assert sem_data.competencia_sugerida is None
    assert sem_data.lancamentos[0].data is None


def test_normalizacao_de_estabelecimento():
    assert normalizar_estabelecimento("UBER *TRIP 8291") == "Uber Trip"
    assert normalizar_estabelecimento("PARC 01/03 LOJAS XYZ") == "Parc Lojas Xyz"
    # Descrição só de códigos: devolve o original (melhor que vazio).
    assert normalizar_estabelecimento("990011") == "990011"
    # Caixa mista é preservada (já é um nome, não um grito de mainframe).
    assert normalizar_estabelecimento("Netflix.com") == "Netflix.com"


def test_decodificar_utf8_bom_e_cp1252():
    assert decodificar_csv("Padaria São João".encode("utf-8-sig")) == \
        "Padaria São João"
    assert decodificar_csv("Padaria São João".encode("cp1252")) == \
        "Padaria São João"


# ------------------------------------------------- texto livre de OCR (T-1405)
def test_parse_linha_livre_valor_no_fim_com_data():
    data, descricao, valor = _parse_linha_livre("07/06/2026 UBER *TRIP 8291 R$ 29,90")
    assert data == "2026-06-07"
    assert descricao == "UBER *TRIP 8291"
    assert valor == 29.90


def test_parse_linha_livre_marcador_de_debito_e_credito():
    # '-' à frente, ou 'D'/'C' logo após o valor (extratos BR).
    assert _parse_linha_livre("MERCADO BOM PRECO -45,10")[2] == -45.10
    assert _parse_linha_livre("PIX ENVIADO PADARIA 1.234,56 D")[2] == -1234.56
    _, desc, valor = _parse_linha_livre("TED RECEBIDA 2.000,00 C")
    assert valor == 2000.00 and desc == "TED RECEBIDA"


def test_parse_linha_livre_ultimo_numero_e_o_valor():
    # Parcelamento: o valor da linha é o ÚLTIMO monetário, não o "12,00".
    _, _, valor = _parse_linha_livre("LOJA XYZ 3x de 12,00 total 36,00")
    assert valor == 36.00


def test_parse_linha_livre_sem_valor_nao_e_lancamento():
    assert _parse_linha_livre("COMPROVANTE DE PAGAMENTO") is None
    assert _parse_linha_livre("Agencia 0001 Conta 12345-6") is None


def test_parse_linha_livre_ignora_linha_de_saldo():
    # Saldo é balanço da conta, não transação — mesmo tendo valor.
    assert _parse_linha_livre("Saldo final: 3.244,50") is None
    assert _parse_linha_livre("SALDO ANTERIOR 1.000,00") is None


# Comprovante escaneado, texto já reconstruído por layout pelo motor de OCR:
# cabeçalho/rodapé sem valor + linhas de lançamento (sinais mistos = conta).
OCR_EXTRATO = """\
BANCO EXEMPLO S.A.
Extrato de conta corrente
05/06/2026 Conta de luz Enel -180,50
07/06/2026 UBER *TRIP 8291 -29,90
15/06/2026 UBER *TRIP 4415 -45,10
30/06/2026 Salario ACME LTDA 3.500,00
Saldo final: 3.244,50
"""


def test_ler_extrato_ocr_reconhece_lancamentos_e_agrupa():
    extrato = ler_extrato_ocr(OCR_EXTRATO)
    # 4 lançamentos (as 2 linhas Uber agrupam), crédito e débito por sinal.
    assert len(extrato.lancamentos) == 4
    nomes = {g.nome: g for g in extrato.grupos}
    assert nomes["Uber Trip"].quantidade == 2
    assert nomes["Uber Trip"].total == 75.00
    assert nomes["Uber Trip"].natureza == "debito"
    salario = next(g for g in extrato.grupos if g.natureza == "credito")
    assert salario.total == 3500.00
    assert extrato.competencia_sugerida == "2026-06"


def test_ler_extrato_ocr_sem_valores_avisa_sem_excecao():
    extrato = ler_extrato_ocr("COMPROVANTE\nAgencia 0001\nObrigado pela preferencia")
    assert extrato.lancamentos == ()
    assert extrato.grupos == ()
    assert len(extrato.avisos) == 1


def test_ler_extrato_ocr_comprovante_de_um_pagamento():
    # Comprovante simples: sem sinais ⇒ tudo débito (é uma despesa).
    extrato = ler_extrato_ocr(
        "COMPROVANTE DE PAGAMENTO\n"
        "Beneficiario ENEL DISTRIBUICAO\n"
        "Valor R$ 180,50\n"
        "Data 05/06/2026\n"
    )
    assert len(extrato.lancamentos) == 1
    (lanc,) = extrato.lancamentos
    assert lanc.valor == 180.50
    assert lanc.natureza == "debito"
