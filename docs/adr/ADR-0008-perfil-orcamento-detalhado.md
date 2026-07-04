# ADR-0008 — Perfil como orçamento doméstico detalhado (roll-up no core)

- **Status:** Aceita (2026-07-04)
- **Contexto de processo:** primeira mudança pós-freeze v2.1.0. Esta ADR é a
  autorização formal exigida pela ata: abre o ciclo **v2.2.0** (M5); nova ata
  de freeze será lavrada no fechamento do ciclo.

## Contexto

A aba Perfil pedia agregados prontos ("Despesas fixas (R$)") em campos únicos.
Na prática, a persona de nível técnico baixo não sabe esses totais de cabeça —
ela sabe o aluguel, a conta de luz, o mercado. O número agregado chegava
impreciso, e toda a cadeia (diagnóstico → estratégias → CONSELHEIRO) herda a
imprecisão da entrada. Na revisão dos `NEEDS_CLARIFICATION` (PRD §8, DEC-1..4),
o mantenedor decidiu que o perfil vira um **orçamento doméstico completo com
itemização obrigatória** na GUI.

## Decisão

1. **Categorias tipadas no `core`** (`core/models.py`): `ComposicaoRenda`
   (salário líquido, renda extra, outras rendas), `DespesasFixas` (moradia,
   contas da casa, transporte, saúde, educação, assinaturas, outras) e
   `DespesasVariaveis` (mercado, lazer, vestuário, imprevistos, outras),
   cada uma com `property total`.
2. **Roll-up determinístico**: `PerfilFinanceiro.com_orcamento(...)` deriva os
   agregados por soma; os campos agregados continuam sendo a única fonte dos
   cálculos (nada muda em `diagnostico`, `estrategias`, agente ou outputs).
   O detalhamento fica preservado em campos opcionais (`renda_detalhada`,
   `fixas_detalhadas`, `variaveis_detalhadas`) para uso futuro em relatórios.
3. **Indicador de reserva** (`meses_reserva`): reserva ÷ despesas totais, em
   meses; `None` quando não há despesas informadas (sem significado).
4. **GUI como casca fina**: a aba Perfil exibe as seções sempre visíveis com
   um campo por categoria, totais ao vivo (trace de `StringVar`), cobertura da
   reserva colorida (≥3 meses ok, ≥1 atenção, <1 crítico) e resumo ao vivo
   (fluxo de caixa livre e comprometimento com dívidas, limiares do
   REQ-F-002). Toda a aritmética vem do `core` — a GUI só formata.

## Alternativas rejeitadas

- **Itemização só na GUI** (somar nos handlers): lógica de negócio fora dos
  portões de qualidade (gui/ não conta cobertura); violaria REQ-NF-004.
- **Campos únicos com texto de ajuda**: escopo menor, mas não resolve a causa
  da imprecisão — o usuário continua estimando o agregado de cabeça.
- **`dict` livre de categorias**: sem tipo, sem autocompletar, sem validação;
  contraria o padrão de contratos tipados do projeto (ADR-0004).

## Consequências

- Retrocompatível: `PerfilFinanceiro(...)` direto pelos agregados segue
  válido (testes e `demo_agente.py` não mudam); `to_dict()` passa a incluir o
  detalhamento (ou `None`).
- Mais fricção de digitação no primeiro uso — aceita conscientemente pelo
  mantenedor em troca de precisão (decisão registrada no PRD §8).
- `FatosFinanceiros` NÃO ganhou o detalhamento nesta ADR: o agente continua
  recebendo agregados. Se o detalhamento se mostrar útil ao CONSELHEIRO,
  será uma extensão futura com nova avaliação de guardrails.

## Requisitos derivados

`REQ-F-006` (itemização + roll-up), `REQ-F-007` (cobertura da reserva) e
`REQ-F-008` (resumo ao vivo) no `SPEC.md` §1; harness em
`tests/test_orcamento.py`.
