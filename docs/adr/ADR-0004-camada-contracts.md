# ADR-0004 — Camada `contracts/` para os schemas Pydantic

- **Status:** Aceita · **Data:** 2026-07-03
- **Relacionada a:** PLAN §1 (regra de dependência), SPEC §6, auditoria F-05

## Contexto

Os schemas Pydantic (`FatosFinanceiros`, `AnaliseAgente`, `ResultadoAnalise`)
viviam em `agent/schemas.py`. Como `guardrails/` precisa desses tipos para
validar a saída do LLM, surgiu uma dependência circular de pacotes:
`agent → guardrails` (orquestração chama validadores) e
`guardrails → agent` (validadores importam os schemas). Funcionava apenas
porque `agent/__init__.py` era vazio — mas violava a regra do PLAN §1
("setas só apontam para baixo") e quebraria com qualquer import no
`__init__` do pacote.

## Decisão

Criar a camada `contracts/` (Pydantic puro, **sem dependências internas**)
e mover `agent/schemas.py` → `contracts/schemas.py`. `agent/` e
`guardrails/` passam a depender apenas de `contracts/`; nenhum dos dois
importa o outro para obter tipos.

```
agent ──▶ guardrails ──▶ contracts ◀── agent
core  (não importa nenhum dos acima)
```

## Consequências

- O grafo de dependências volta a ser acíclico e verificável.
- Contratos ganham endereço estável para a GUI (M3) e futuros consumidores
  (CLI) sem arrastar o pacote `agent/` inteiro.
- Custo: um pacote a mais e atualização de imports (feita nesta mudança).
