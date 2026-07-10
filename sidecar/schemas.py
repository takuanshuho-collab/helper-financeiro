"""
Contrato de dados do sidecar (REQ-NF-005).

Modelos Pydantic da fronteira HTTP. O front envia o orçamento por categoria e a
lista de dívidas; o roll-up dos agregados acontece no `core` (ADR-0008), nunca
aqui. Nenhum cálculo financeiro vive neste módulo.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DividaIn(BaseModel):
    credor: str
    tipo: str
    saldo_devedor: float = 0.0
    taxa_mensal: float = 0.0
    parcela: float = 0.0
    parcelas_restantes: int = 0
    garantia: str = ""
    em_atraso: bool = False
    dias_atraso: int = 0
    cet_anual: float | None = None


class RendaIn(BaseModel):
    salario_liquido: float = 0.0
    renda_extra: float = 0.0
    outras_rendas: float = 0.0


class FixasIn(BaseModel):
    moradia: float = 0.0
    contas_casa: float = 0.0
    transporte: float = 0.0
    saude: float = 0.0
    educacao: float = 0.0
    assinaturas: float = 0.0
    outras_fixas: float = 0.0


class VariaveisIn(BaseModel):
    mercado: float = 0.0
    lazer: float = 0.0
    vestuario: float = 0.0
    imprevistos: float = 0.0
    outras_variaveis: float = 0.0


class PerfilIn(BaseModel):
    """Orçamento por categoria + dívidas — a entrada do diagnóstico."""

    renda: RendaIn = Field(default_factory=RendaIn)
    fixas: FixasIn = Field(default_factory=FixasIn)
    variaveis: VariaveisIn = Field(default_factory=VariaveisIn)
    reserva_emergencia: float = 0.0
    saldo_fgts: float = 0.0
    dividas: list[DividaIn] = Field(default_factory=list)


class RubricaIn(BaseModel):
    """Novo lançamento do orçamento (T-1103, REQ-F-017).

    A ancoragem (`categoria` + `campo_pai`) é validada contra o modelo do
    core (`CAMPOS_POR_CATEGORIA`) no endpoint — 422 se não existir.
    """

    categoria: str   # 'renda' | 'fixas' | 'variaveis'
    campo_pai: str   # ex.: 'contas_casa'
    nome: str
    valor: float = 0.0
    ordem: int = 0


class RubricaEditIn(BaseModel):
    """Edição de rubrica: nome/valor (e ordem, opcional). Ancoragem não muda."""

    nome: str
    valor: float = 0.0
    ordem: int | None = None


class ArquivarMesIn(BaseModel):
    """Arquiva a competência 'AAAA-MM' (snapshot do orçamento vivo, T-1202)."""

    mes: str


class CompararMesesIn(BaseModel):
    """Comparação entre competências; `mes_b` None = contra o orçamento vivo."""

    mes_a: str
    mes_b: str | None = None


class ImportarCsvIn(BaseModel):
    """Extrato/fatura CSV (base64) para importação classificada (REQ-F-021).

    Base64 do ARQUIVO cru (não texto): a decodificação de encoding
    (UTF-8/cp1252) é do core. Viaja só na loopback; nada é persistido até o
    usuário revisar e aplicar (ADR-0014).
    """

    csv_base64: str
    nome: str = ""


class ImportarOcrIn(BaseModel):
    """Comprovante/extrato ESCANEADO (imagem ou PDF, base64) para importação
    classificada via OCR local (REQ-F-026 / ADR-0015).

    Base64 do arquivo cru; o OCR roda no sidecar (H2/H7) e o texto vira
    lançamentos pelo mesmo `core/extrato`. Nada é persistido até revisar.
    """

    arquivo_base64: str
    nome: str = ""


class ItemImportacaoIn(BaseModel):
    """Um grupo revisado pelo usuário, pronto para virar rubrica."""

    categoria: str   # 'renda' | 'fixas' | 'variaveis'
    campo_pai: str   # ex.: 'mercado'
    nome: str
    valor: float = 0.0


class AplicarImportacaoIn(BaseModel):
    """Aplica a importação revisada; `mes` None = orçamento vivo."""

    mes: str | None = None
    itens: list[ItemImportacaoIn] = Field(default_factory=list)


class EstrategiasIn(BaseModel):
    """Perfil + pagamento extra mensal para simular a quitação."""

    perfil: PerfilIn
    extra: float = 0.0


class AnaliseIn(BaseModel):
    """Perfil + parâmetros da tela Análise (REQ-F-015).

    `extra` alimenta a simulação de quitação; `taxa_alvo` (fração mensal,
    0.018 = 1,8% a.m.) filtra as oportunidades de portabilidade.
    """

    perfil: PerfilIn
    extra: float = 0.0
    taxa_alvo: float = 0.018


class AnaliseIaIn(BaseModel):
    """Disparo do job assíncrono da análise sênior (IA, sob guardrails)."""

    perfil: PerfilIn
    extra: float = 0.0


class ExportarPlanilhaIn(BaseModel):
    """Exportação .xlsx: o caminho vem do diálogo de salvar do Electron."""

    perfil: PerfilIn
    caminho: str
    extra: float = 0.0
    taxa_alvo: float = 0.018


class ExportarRelatorioIn(ExportarPlanilhaIn):
    """Exportação .docx; `secao_ia` é a última análise sênior (opcional)."""

    nome_usuario: str = ""
    secao_ia: dict[str, Any] | None = None


class CartaIn(BaseModel):
    """Carta ao credor (REQ-F-016): dívida + tipo + campos contextuais.

    `valor_proposto` só vale para quitação; `banco_concorrente`/`taxa_
    concorrente_mensal` (fração, 0.018 = 1,8% a.m.) só para portabilidade.
    Nome/CPF ficam na loopback e no arquivo local — nunca vão à nuvem (H2).
    """

    divida: DividaIn
    tipo: str = "quitacao"  # "quitacao" | "portabilidade" | "reducao"
    valor_proposto: float | None = None
    banco_concorrente: str = ""
    taxa_concorrente_mensal: float | None = None
    nome_usuario: str = ""
    cpf: str = ""
    contrato: str = ""


class ExportarCartaIn(CartaIn):
    """Exportação da carta .docx no caminho escolhido no diálogo do Electron."""

    caminho: str


class ContratoIn(BaseModel):
    """PDF de contrato (base64) para extração LOCAL dos campos (REQ-F-014).

    O binário viaja só na loopback; o sidecar o decodifica em memória, extrai o
    texto e roda a extração local — nada é persistido em disco nem vai à nuvem.
    """

    pdf_base64: str
    nome: str = ""


class ConfirmarContratoIn(BaseModel):
    """Retomada do grafo de extração pausado (interrupt→resume, ADR-0006)."""

    thread_id: str
    confirmacao: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------- cofre local (T-1603, ADR-0016)
class CadastrarCofreIn(BaseModel):
    """Cadastro do cofre: só a senha mestra — o TOTP nasce no servidor e o
    URI/QR volta na resposta de `POST /auth/cadastrar`."""

    senha: str


class LoginCofreIn(BaseModel):
    """Login do cofre: senha mestra (1º fator) + código TOTP (2º fator)."""

    senha: str
    codigo_totp: str


class RecuperarCofreIn(BaseModel):
    """Redefine a senha por um código de recuperação de uso único (o código É
    o fator de posse; TOTP não é exigido aqui — ADR-0016 §A)."""

    codigo: str
    nova_senha: str


class TrocarSenhaCofreIn(BaseModel):
    """Troca de senha com o cofre já desbloqueado; exige os 2 fatores atuais
    (o `Cofre` os confere de novo antes de re-envelopar a DEK)."""

    senha_atual: str
    codigo_totp: str
    nova_senha: str
