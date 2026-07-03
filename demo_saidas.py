"""
Demonstração sem interface: monta um perfil de exemplo e gera as três saídas.

Rode com:  python demo_saidas.py
Serve para testar o motor e ver o que o programa produz.
"""
import os

from core.models import Divida, PerfilFinanceiro
from outputs.planilha import gerar_planilha
from outputs.proposta import gerar_proposta
from outputs.relatorio import gerar_relatorio

SAIDA = os.path.join(os.path.dirname(__file__), "exemplos")
os.makedirs(SAIDA, exist_ok=True)

perfil = PerfilFinanceiro(
    renda_liquida=5000,
    despesas_fixas=2200,
    despesas_variaveis=800,
    reserva_emergencia=0,
    saldo_fgts=3000,
    dividas=[
        Divida("Cartão Banco A", "Cartão de crédito", 8000, 0.12, 900, 12),
        Divida("CDC Veículo", "CDC (Crédito Direto ao Consumidor)", 20000, 0.025, 700, 36,
               garantia="alienação fiduciária do veículo"),
        Divida("Consignado Servidor", "Consignado", 6000, 0.018, 350, 20,
               garantia="folha de pagamento"),
    ],
)

gerar_planilha(perfil, os.path.join(SAIDA, "exemplo_diagnostico.xlsx"),
               extra_mensal=500, taxa_alvo_mensal=0.018)
gerar_relatorio(perfil, os.path.join(SAIDA, "exemplo_relatorio.docx"),
                extra_mensal=500, taxa_alvo_mensal=0.018,
                nome_usuario="Usuário de Exemplo")
gerar_proposta(perfil.dividas[0], os.path.join(SAIDA, "exemplo_carta_quitacao.docx"),
               tipo="quitacao", dados={"valor_proposto": 5500},
               nome_usuario="Usuário de Exemplo", contrato="2024-00123")

print("Saídas geradas na pasta 'exemplos/':")
for f in sorted(os.listdir(SAIDA)):
    print("  -", f)
