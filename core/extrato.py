"""
Leitura determinística de extratos CSV (ADR-0014, REQ-F-021).

Fonte única do parse: o sidecar recebe o texto do CSV e delega tudo aqui —
detecção de separador, localização das colunas (data/descrição/valor),
valores em formato brasileiro e internacional, e o agrupamento por
estabelecimento que vira candidato a rubrica. A LLM entra DEPOIS, e só para
rotular grupos com um campo do orçamento: nenhum número deste módulo passa
pelo modelo (H1 por construção).

Heurísticas assumidas (limites documentados na ADR-0014):
- sinais mistos ⇒ extrato de conta (negativo = débito, positivo = crédito);
  todos os valores com o mesmo sinal ⇒ fatura de cartão (tudo débito);
- linha ilegível vira AVISO, nunca exceção — o usuário revisa antes de
  aplicar de qualquer forma.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass

from .utils import parse_valor, texto_numerico_valido

# Palavras-chave (minúsculas, por substring) que identificam as colunas no
# cabeçalho — pt e en, cobrindo os exports comuns de bancos/cartões.
_CHAVES_DATA = ("data", "date")
_CHAVES_DESCRICAO = (
    "descri", "title", "hist", "lançamento", "lancamento",
    "estabelecimento", "memo",
)
_CHAVES_VALOR = ("valor", "amount", "value", "montante")

_RE_DATA_BR = re.compile(r"^(\d{2})[/.-](\d{2})[/.-](\d{4})$")
_RE_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

# Texto livre (OCR de comprovante/extrato): valor monetário BR (número + sinal
# opcional à frente) e data em qualquer posição da linha.
_RE_VALOR_LIVRE = re.compile(r"(-)?\s*R?\$?\s*(\d[\d.]*,\d{2})(?![\d,])")
_RE_DATA_EM_TEXTO = re.compile(r"\b(\d{2}[/.-]\d{2}[/.-]\d{4}|\d{4}-\d{2}-\d{2})\b")


@dataclass(frozen=True)
class Lancamento:
    """Uma linha do extrato, já interpretada."""

    data: str | None   # ISO 'AAAA-MM-DD'; None quando a data não é legível
    descricao: str
    valor: float       # com o sinal original do arquivo
    natureza: str      # 'credito' | 'debito' (heurística de sinais)


@dataclass(frozen=True)
class GrupoExtrato:
    """Lançamentos do mesmo estabelecimento somados — candidato a rubrica."""

    nome: str          # estabelecimento normalizado, ex.: 'Uber Trip'
    total: float       # soma ABSOLUTA, arredondada a 2 casas
    quantidade: int
    natureza: str      # 'credito' | 'debito'


@dataclass(frozen=True)
class Extrato:
    """Resultado completo do parse de um CSV."""

    lancamentos: tuple[Lancamento, ...]
    grupos: tuple[GrupoExtrato, ...]
    competencia_sugerida: str | None   # 'AAAA-MM' (moda das datas) ou None
    avisos: tuple[str, ...]


def decodificar_csv(dados: bytes) -> str:
    """Bytes do arquivo → texto: UTF-8 (com/sem BOM) e legado Windows."""
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return dados.decode("latin-1", errors="replace")


def _parse_data(texto: str) -> str | None:
    """'07/06/2026', '07.06.2026' ou '2026-06-07' → '2026-06-07'; senão None."""
    limpo = texto.strip()
    m = _RE_DATA_BR.match(limpo)
    if m:
        dia, mes, ano = m.group(1), m.group(2), m.group(3)
    else:
        m = _RE_DATA_ISO.match(limpo)
        if not m:
            return None
        ano, mes, dia = m.group(1), m.group(2), m.group(3)
    if not (1 <= int(mes) <= 12 and 1 <= int(dia) <= 31):
        return None
    return f"{ano}-{mes}-{dia}"


def _detectar_separador(linha: str) -> str:
    """';' (padrão dos bancos BR), tab ou ',' — o que aparecer na 1ª linha."""
    if ";" in linha:
        return ";"
    if "\t" in linha:
        return "\t"
    return ","


def _mapear_cabecalho(celulas: list[str]) -> dict[str, int] | None:
    """Índices das colunas pelo cabeçalho; None se a linha não é cabeçalho."""
    mapa: dict[str, int] = {}
    for i, celula in enumerate(celulas):
        rotulo = celula.strip().casefold()
        if "data" not in mapa and any(ch in rotulo for ch in _CHAVES_DATA):
            mapa["data"] = i
        elif "valor" not in mapa and any(ch in rotulo for ch in _CHAVES_VALOR):
            mapa["valor"] = i
        elif "descricao" not in mapa and any(
            ch in rotulo for ch in _CHAVES_DESCRICAO
        ):
            mapa["descricao"] = i
    # Sem valor ou descrição não há lançamento; "data" é opcional (alguns
    # exports de fatura não trazem coluna de data reconhecível).
    return mapa if "valor" in mapa and "descricao" in mapa else None


def _inferir_colunas(celulas: list[str]) -> dict[str, int] | None:
    """Arquivo sem cabeçalho: deduz as colunas pelo CONTEÚDO da 1ª linha.

    Data = primeira célula que parseia como data; valor = a ÚLTIMA célula
    numérica (bancos costumam pôr o valor no fim); descrição = a mais longa
    das restantes.
    """
    mapa: dict[str, int] = {}
    for i, celula in enumerate(celulas):
        if "data" not in mapa and _parse_data(celula):
            mapa["data"] = i
    for i in range(len(celulas) - 1, -1, -1):
        if i == mapa.get("data"):
            continue
        texto = celulas[i].strip()
        if texto and texto_numerico_valido(texto):
            mapa["valor"] = i
            break
    restantes = [
        i for i in range(len(celulas))
        if i not in (mapa.get("data"), mapa.get("valor"))
    ]
    if restantes:
        mapa["descricao"] = max(restantes, key=lambda i: len(celulas[i].strip()))
    return mapa if "valor" in mapa and "descricao" in mapa else None


def normalizar_estabelecimento(descricao: str) -> str:
    """Nome estável para agrupar: sem códigos, '*', datas e dígitos soltos.

    'UBER *TRIP 8291' e 'UBER *TRIP 4415' → 'Uber Trip'. Se a limpeza
    consumir tudo (descrição só de códigos), devolve a descrição original.
    """
    tokens = []
    for token in descricao.replace("*", " ").split():
        if _parse_data(token):
            continue
        digitos = sum(c.isdigit() for c in token)
        if digitos and digitos * 2 >= len(token):
            continue   # '8291', '01/03', '2x' — código, não nome
        tokens.append(token)
    nome = " ".join(tokens)
    if nome.isupper():
        nome = nome.title()
    return nome or descricao.strip()


def _naturezas(valores: list[float]) -> list[str]:
    """Sinais mistos ⇒ conta (sinal decide); sinal único ⇒ fatura (débito)."""
    tem_credito = any(v > 0 for v in valores)
    tem_debito = any(v < 0 for v in valores)
    if tem_credito and tem_debito:
        return ["credito" if v > 0 else "debito" for v in valores]
    return ["debito"] * len(valores)


def _agrupar(lancamentos: list[Lancamento]) -> tuple[GrupoExtrato, ...]:
    """Agrupa por (estabelecimento normalizado, natureza), maior total antes."""
    grupos: dict[tuple[str, str], list[Lancamento]] = {}
    nomes: dict[tuple[str, str], str] = {}
    for lanc in lancamentos:
        nome = normalizar_estabelecimento(lanc.descricao)
        chave = (nome.casefold(), lanc.natureza)
        grupos.setdefault(chave, []).append(lanc)
        nomes.setdefault(chave, nome)
    resultado = [
        GrupoExtrato(
            nome=nomes[chave],
            total=round(sum(abs(item.valor) for item in itens), 2),
            quantidade=len(itens),
            natureza=chave[1],
        )
        for chave, itens in grupos.items()
    ]
    return tuple(sorted(resultado, key=lambda g: -g.total))


def _competencia_sugerida(lancamentos: list[Lancamento]) -> str | None:
    """Moda dos 'AAAA-MM' entre as datas legíveis; None sem nenhuma data."""
    meses = Counter(
        lanc.data[:7] for lanc in lancamentos if lanc.data is not None
    )
    if not meses:
        return None
    return meses.most_common(1)[0][0]


def ler_extrato_csv(texto: str) -> Extrato:
    """Texto do CSV → lançamentos + grupos + competência sugerida + avisos."""
    linhas_uteis = [linha for linha in texto.splitlines() if linha.strip()]
    if not linhas_uteis:
        return Extrato((), (), None, ("Arquivo vazio.",))

    separador = _detectar_separador(linhas_uteis[0])
    leitor = csv.reader(io.StringIO("\n".join(linhas_uteis)), delimiter=separador)
    linhas = [celulas for celulas in leitor if any(c.strip() for c in celulas)]

    mapa = _mapear_cabecalho(linhas[0])
    dados = linhas[1:] if mapa else linhas
    if mapa is None:
        mapa = _inferir_colunas(linhas[0])
    if mapa is None:
        return Extrato(
            (), (), None,
            ("Não reconheci as colunas de descrição e valor do arquivo.",),
        )

    avisos: list[str] = []
    brutos: list[tuple[str | None, str, float]] = []
    for numero, celulas in enumerate(dados, start=2 if dados is not linhas else 1):
        try:
            texto_valor = celulas[mapa["valor"]].strip()
            descricao = celulas[mapa["descricao"]].strip()
        except IndexError:
            avisos.append(f"Linha {numero} ignorada: colunas faltando.")
            continue
        if not texto_valor or not texto_numerico_valido(texto_valor):
            avisos.append(f"Linha {numero} ignorada: valor ilegível.")
            continue
        valor = parse_valor(texto_valor)
        if valor == 0.0:
            avisos.append(f"Linha {numero} ignorada: valor zerado.")
            continue
        if not descricao:
            avisos.append(f"Linha {numero} ignorada: sem descrição.")
            continue
        data = None
        if "data" in mapa and mapa["data"] < len(celulas):
            data = _parse_data(celulas[mapa["data"]])
        brutos.append((data, descricao, valor))

    naturezas = _naturezas([valor for _, _, valor in brutos])
    lancamentos = [
        Lancamento(data=data, descricao=descricao, valor=valor, natureza=nat)
        for (data, descricao, valor), nat in zip(brutos, naturezas, strict=True)
    ]
    return Extrato(
        lancamentos=tuple(lancamentos),
        grupos=_agrupar(lancamentos),
        competencia_sugerida=_competencia_sugerida(lancamentos),
        avisos=tuple(avisos),
    )


def _parse_linha_livre(linha: str) -> tuple[str | None, str, float] | None:
    """Uma linha de texto (OCR de comprovante/extrato) → (data, descrição, valor).

    Heurística por linha, no espírito de `_inferir_colunas` mas sobre texto sem
    colunas: o ÚLTIMO número monetário é o valor (bancos põem o valor no fim da
    linha); um sinal '-' à frente, ou '-'/'D' logo após, marca débito, 'C' marca
    crédito; a data (se houver) é o 1º token de data; a descrição é o que sobra.
    Linha sem valor monetário não é lançamento (título, rodapé) → None; linha de
    SALDO também não (é o balanço da conta, não uma transação — e o valor pouparia
    o usuário de desmarcá-lo na revisão).
    """
    if re.search(r"\bsaldo\b", linha, re.IGNORECASE):
        return None
    achados = list(_RE_VALOR_LIVRE.finditer(linha))
    if not achados:
        return None
    m = achados[-1]
    valor = parse_valor(m.group(2))
    if valor == 0.0:
        return None
    # Sinal: '-' à frente, ou '-'/'D' logo após (extratos BR); 'C' = crédito.
    sufixo = linha[m.end():m.end() + 2].strip().upper()[:1]
    negativo = m.group(1) == "-" or sufixo in ("-", "D")
    valor = -abs(valor) if negativo else abs(valor)

    data_match = _RE_DATA_EM_TEXTO.search(linha)
    data = _parse_data(data_match.group(1)) if data_match else None

    # Descrição = linha sem os trechos de data e valor (splice do fim p/ início,
    # p/ os índices não invalidarem), sem R$/moeda e sem o marcador de sinal.
    spans = sorted(
        ([data_match.span()] if data_match else []) + [m.span()], reverse=True
    )
    desc = linha
    for ini, fim in spans:
        desc = desc[:ini] + " " + desc[fim:]
    tokens = desc.replace("R$", " ").replace("$", " ").split()
    if tokens and tokens[-1].upper() in ("D", "C", "-"):
        tokens.pop()
    descricao = " ".join(tokens).strip(" -–—:|")
    return data, (descricao if len(descricao) >= 2 else "Lançamento"), valor


def ler_extrato_ocr(texto: str) -> Extrato:
    """Texto OCRizado de um comprovante/extrato → mesmo `Extrato` do CSV.

    O OCR (`agent/ocr.py`) já reconstruiu as linhas pela leitura do layout; aqui
    cada linha com valor monetário vira um `Lancamento` e o resto do pipeline é
    IDÊNTICO ao do CSV (agrupamento por estabelecimento, natureza por sinais,
    competência pela moda das datas) — a classificação e o `/importar/aplicar`
    do v2.6 são reusados sem mudança (ADR-0015 §E). Todo número vem daqui, nunca
    do modelo (H1); linhas sem valor são silenciosamente ignoradas (num
    documento livre a maioria não é lançamento).
    """
    brutos: list[tuple[str | None, str, float]] = []
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        parsed = _parse_linha_livre(linha)
        if parsed is not None:
            brutos.append(parsed)

    if not brutos:
        return Extrato(
            (), (), None,
            ("Não reconheci lançamentos com valor no documento escaneado.",),
        )

    naturezas = _naturezas([valor for _, _, valor in brutos])
    lancamentos = [
        Lancamento(data=data, descricao=descricao, valor=valor, natureza=nat)
        for (data, descricao, valor), nat in zip(brutos, naturezas, strict=True)
    ]
    return Extrato(
        lancamentos=tuple(lancamentos),
        grupos=_agrupar(lancamentos),
        competencia_sugerida=_competencia_sugerida(lancamentos),
        avisos=(),
    )
