"""
Testes de `texto_numerico_valido` (M6 / REQ-F-009).

O validador alimenta a sinalização visual da GUI: texto não interpretável
nunca deve virar zero silenciosamente sem o campo ser marcado.
"""
import pytest

from core.utils import parse_valor, texto_numerico_valido


@pytest.mark.parametrize("texto", [
    None, "", "   ",                      # vazio vale zero por design
    "0", "1234", "1.234,56", "1234,56",
    "R$ 1.234,56", "2,3%", "1234.56", "-150,00",
])
def test_textos_validos(texto):
    assert texto_numerico_valido(texto) is True


@pytest.mark.parametrize("texto", [
    "abc", "12a34", "1,2,3", "1.2.3,4x", "R$ dez", "--5",
])
def test_textos_invalidos(texto):
    assert texto_numerico_valido(texto) is False


def test_invalido_e_exatamente_onde_parse_valor_cai_no_zero_fallback():
    """Coerência com parse_valor: inválido ⇔ o parse devolveu o 0.0 de
    fallback para um texto não vazio (o caso que a GUI precisa sinalizar)."""
    for texto in ("abc", "1,2,3", "12a34"):
        assert parse_valor(texto) == 0.0
        assert not texto_numerico_valido(texto)
    for texto in ("0", "0,00", "R$ 0"):
        assert parse_valor(texto) == 0.0
        assert texto_numerico_valido(texto)  # zero legítimo não é sinalizado
