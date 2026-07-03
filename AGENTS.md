# AGENTS.md — Guia para o agente de código (IDE)

> Leia este arquivo **antes de escrever qualquer código** neste repositório.
> Vale para Claude Code, Cursor, Windsurf, Copilot etc. Pode ser copiado/symlink
> para `CLAUDE.md` ou `.cursorrules`.

## Ordem de leitura obrigatória
1. `docs/CONSTITUTION.md` — princípios in**violáveis** (P1–P8, hard rules).
2. `docs/SPEC.md` — o que construir (EARS, REQ-IDs, contratos).
3. `docs/PLAN.md` — como construir (arquitetura, stack, denylist).
4. `docs/TASKS.md` — em que ordem. Pegue a próxima task ⬜.

## Regras de trabalho (harness & guardrails)
- **Rastreabilidade:** todo commit cita o `REQ-ID` e a `T-ID` que atende.
- **Teste primeiro do guardrail:** ao implementar um `REQ-GRD-*`, escreva/rode o
  teste do harness correspondente (`docs/HARNESS §7`).
- **Fonte da verdade numérica:** nunca calcule finanças em prompt nem no
  pós-processamento do LLM (P1). Números vêm do `core/`.
- **Dependência em camadas:** `core/` não importa `agent/`, `outputs/`, `gui/`.
  Setas só apontam para baixo (`PLAN §1`).
- **Denylist:** não adicione bibliotecas fora do `PLAN §Stack`. Nada de
  framework web, ORM ou telemetria.
- **Segredos:** chave de API só via variável de ambiente; nunca em código/log.

## Quando PARAR e perguntar (NEEDS_CLARIFICATION)
Se um requisito estiver ambíguo, uma feature nova for sugerida, ou a stack
precisar mudar: **não improvise**. Marque `NEEDS_CLARIFICATION` no PR/comentário
e pare. Mudança de arquitetura exige uma ADR nova em `docs/adr/`.

## Comandos úteis
```bash
uv sync --group dev              # instala tudo (pyproject.toml + uv.lock)
uv run pytest -q                 # harness offline (deve ficar verde)
uv run ruff check .              # lint — mesmo portão do CI
uv run mypy core agent guardrails outputs main.py
uv run python demo_saidas.py     # gera exemplos determinísticos
uv run python main.py            # abre a GUI
```

## Definição de Pronto
Ver `docs/TASKS.md §DoD`. Resumo: adere ao SPEC, tem teste verde offline, não
viola guardrail, sem PII/chave em claro.
