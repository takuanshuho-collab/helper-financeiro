# ADR-0019 — Ciclo v2.11: endurecimento dormente, higiene de linter e complexidade sob catraca

- **Status:** Aceita (design validado em brainstorming com o mantenedor) ·
  **Data:** 2026-07-13
- **Relacionada a:** achados **C-23, C-28, C-29, C-35** do
  `RELATORIO-AUDITORIA.md` (auditoria v2.9, ADR-0017); regras herdadas da
  ADR-0017 §E (zero regressão) e ADR-0018 §5 (auditoria de deps no
  fechamento)
- **Ciclo:** v2.11.0 · **Milestones:** M21 (T-2101..T-2102) e M22
  (T-2201..T-2204)

## Contexto

Restaram quatro achados da auditoria v2.9 (C-15/code signing segue travado
no certificado, fora deste ciclo): **C-23** — no fallback POSIX
(`~/.helper_financeiro`) os arquivos do cofre nascem `0644`, mas não existe
build POSIX hoje (Windows/`%APPDATA%` protegido por ACL); **C-28** —
`gerar_relatorio` (`outputs/relatorio.py`) é o maior hotspot de complexidade
(C901 dispara; ~94 statements); **C-29** — hotspots secundários
`_aba_evolucao` (`outputs/planilha.py`) e `baixar_modelo`
(`sidecar/gestor_modelos.py`); **C-35** — grupo "estilo/falsos positivos"
(ARG001, ERA001, S608, PLW0603, FURB122), classificado na auditoria como
"sem ação por definição".

## Decisão

### M21 — Endurecimento e higiene (tasks independentes, paralelizáveis)

- **T-2101 (C-23, endurecimento dormente):** `0o600` nos arquivos e `0o700`
  nas pastas do cofre no ramo POSIX — pontos únicos: `sidecar/arquivos.py`
  (`gravar_json_atomico`, ganho da T-1909) e a criação de pasta/banco em
  `sidecar/persistencia.py`. No Windows é inerte (no-op); unit tests provam
  os flags via monkeypatch de `os.name`/`os.open`. Fecha o achado de vez.
- **T-2102 (C-35, mini-varredura):** reavaliação item a item (decisão do
  mantenedor no brainstorming) com **veredito triplo** por item: (a)
  corrigir, se a reavaliação achar mérito real; (b) **suprimir formalmente**
  (`# noqa: XXX — <motivo>` na linha ou `per-file-ignores` comentado no
  pyproject); (c) manter como está, se a supressão poluir mais que o aviso.
  Aceite: `ruff check` com as regras desses grupos ativadas roda limpo ou
  100% justificado em código — auditoria futura não reabre. **Nenhuma
  mudança de comportamento**: bug real encontrado PARA a task e vira achado
  novo para o portão.

### M22 — Complexidade sob catraca (sequência rígida)

- **T-2201 (golden-master, ANTES de qualquer refatoração):**
  `tests/test_golden_outputs.py` com extratores determinísticos — `.docx` →
  lista ordenada de `(estilo, texto)` de parágrafos + células (python-docx);
  `.xlsx` → por aba, `(coordenada, valor_ou_fórmula)` na ordem (openpyxl;
  fórmula comparada como string). Goldens das 3 fixtures do harness
  (`PERFIL_ATENCAO`/`CRITICO`/`SAUDAVEL`, variantes com/sem
  dívidas/rubricas onde fizer diferença) congelados como **JSON versionado**
  em `tests/golden/` — legível em diff, regenerável SÓ com
  `HF_REGENERAR_GOLDEN=1` (o teste se recusa a regenerar em CI). Campo
  volátil (ex.: data) é **mascarado no extrator**, nunca no golden, com a
  máscara documentada. A task fixa o estado ATUAL — commit separado, régua
  antes da obra.
- **T-2202 (C-28):** `gerar_relatorio` refatorado por seção — **extrair,
  não reescrever**: cada seção vira função privada que recebe documento e
  dados; movimentação de código sem melhorar prosa, ordem ou formatação.
  Proibido mudar assinatura pública, mensagens de erro, logs ou string
  visível. Aceite: golden idêntico + suíte + C901 da função abaixo do teto.
- **T-2203 (C-29):** mesmo contrato para `_aba_evolucao` (extrair
  cabeçalho/série/resumo/gráfico) e `baixar_modelo` (extrair
  validação/retomada/promoção).
- **T-2204 (fechamento):** medir o pior C901 restante no repo → fixar
  `max-complexity` nesse valor → ativar **`C901` no `[tool.ruff.lint]` como
  catraca permanente** ("só aperta", mesma filosofia do piso de cobertura;
  o teto acomoda o legado existente — impede crescer, não pune fora de
  escopo; recalibração futura só para baixo). Gates completos, auditoria de
  deps (ADR-0018 §5), ata `FREEZE.md` v2.11.0.

### Critérios de fechamento

Goldens idênticos pós-refatoração; C901 ativo e verde; suíte completa verde
com cobertura ≥ 96,6%; E2E dev verde; `npm audit`/`pip-audit` registrados;
ata v2.11.0. **Smoke do pacote NSIS não obrigatório** neste ciclo (nenhuma
dependência sobe — ADR-0017 §E.4 não dispara; GUI/Electron intocados),
decisão registrada aqui e na ata.

## Riscos aceitos

| Risco | Mitigação |
|---|---|
| Golden frágil a campo volátil (datas) | máscara no extrator, documentada no teste |
| Refatoração "melhorar sem querer" a prosa | diretriz extrair-não-reescrever + golden acusa qualquer desvio |
| C-35 virar túnel de retrabalho | veredito (c) "manter como está" disponível por item |
| Catraca C901 atrapalhar ciclo futuro | teto = pior caso existente; recalibração documentada |

## Alternativas rejeitadas (Decision Log do brainstorming)

- **C-35 silenciado direto / fora do ciclo:** o mantenedor preferiu
  reavaliar item a item antes de suprimir.
- **C-23 adiado até existir build POSIX / "não se aplica":** dependeria de
  memória futura; o endurecimento dormente custa pouco e fecha o achado.
- **Confiar na suíte atual como régua dos refactors:** ela não fixa prosa
  nem ordem das seções; **byte a byte:** impossível (docx/xlsx são zips com
  metadados variáveis).
- **Sem catraca / catraca só informativa:** o problema voltaria em silêncio,
  como aconteceu até a auditoria v2.9.
- **Milestone único / um por achado:** perde paralelismo ou vira cerimônia
  (YAGNI de processo).
- **Regeneração livre dos goldens:** destruiria a prova — só por flag
  explícita fora do CI.
