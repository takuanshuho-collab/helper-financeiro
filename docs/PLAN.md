# PLAN — Helper Financeiro v2

- **Versão:** 2.0.0 · **Implementa:** `SPEC.md` · **Regido por:** `CONSTITUTION.md`

---

## 1. Arquitetura em camadas

```
┌─────────────────────────────────────────────────────────────┐
│  gui/  (tkinter)  — apresenta números + análise da IA         │
│                     com separação visual explícita            │
└───────────────▲───────────────────────────▲──────────────────┘
                │                            │
        ResultadoAnalise             (arquivos .xlsx/.docx)
                │                            │
┌───────────────┴───────────────┐   ┌────────┴───────────────────┐
│  agent/  (orquestra a IA)      │   │  outputs/ (geradores)      │
│  agente.py · provider.py       │   │  planilha · relatorio ·    │
│  prompts.py · schemas · config │   │  proposta                  │
└───────▲───────────────▲────────┘   └────────────────────────────┘
        │               │
   FatosFinanceiros   guardrails/  (pii · validador_numerico · conteudo)
        │               │
┌───────┴───────────────┴────────────────────────────────────────┐
│  core/  (motor determinístico — Python puro, FONTE DA VERDADE)   │
│  models · calculos · diagnostico · estrategias · extrator_pdf    │
└──────────────────────────────────────────────────────────────────┘
```

**Regra de dependência (P1/REQ-NF-004):** setas só apontam para baixo. `core`
não importa `agent`, `outputs` nem `gui`. `agent` depende de `core`,
`guardrails` e `contracts`. Nada importa `gui`.

**Camada `contracts/` (ADR-0004):** os schemas Pydantic vivem em
`contracts/schemas.py`, pacote sem dependências internas. `agent` e
`guardrails` importam tipos apenas de lá — nunca um do outro.

## 2. Fluxo de uma análise (caminho feliz)

1. GUI monta `PerfilFinanceiro` (entradas do usuário + PDF conferido).
2. `core` calcula tudo → `diagnostico` + `estrategias`.
3. `agent.montar_fatos()` converte em `FatosFinanceiros` e **anonimiza**
   (guardrails/pii) → tokens `CREDOR_n`, `PESSOA_n`.
4. `agent.provider` chama o LLM (local Ollama ou cloud) com **saída estruturada**.
5. `guardrails` validam: schema → **consistência numérica (H1)** → conteúdo (H6)
   → aviso legal (H3).
6. Se ok: `de-tokeniza` para exibição e devolve `ResultadoAnalise(modo="completo")`.
7. Se qualquer etapa falhar: `ResultadoAnalise(modo="degradado")` com o
   determinístico intacto (P8).

## 3. Stack (congelada — ver Denylist na CONSTITUTION)

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Linguagem | Python 3.12+ | v1, empacotável em `.exe` |
| GUI | tkinter (stdlib) | offline, sem JS, vira `.exe` |
| Planilha | openpyxl | fórmulas + gráfico |
| Documentos | python-docx | `.docx` sem Node |
| PDF | pdfplumber | extração de texto |
| Schemas | pydantic v2 | contratos tipados |
| LLM (structured) | instructor (opcional) + cliente OpenAI-compatible | agnóstico nuvem/local |
| LLM local | Ollama (ex.: Qwen) | LGPD / offline |
| Testes | pytest | harness |

**Não entram (denylist):** frameworks web, ORMs, libs de telemetria, cálculo
financeiro dentro de prompts.

## 4. Provider agnóstico (REQ-LLM-003/004)

- Interface única `LLMProvider.analisar(fatos) -> AnaliseAgente`.
- Implementações: `OllamaProvider` (base_url local), `OpenAICompatProvider`,
  `FakeProvider` (determinístico, para o harness — sem rede).
- Seleção por `agent/config.py` (env). Padrão recomendado: **local-first**.

## 5. Anonimização (REQ-GRD-002/SEC-003)
- `mascarar(perfil) -> (fatos_tokenizados, mapa)`; `mapa` só em memória.
- Tokens estáveis por execução: `CREDOR_1..n` na ordem das dívidas.
- `desmascarar(texto, mapa)` restaura para exibição local.

## 6. Guardrail de consistência numérica (REQ-GRD-001/H1)
- Extrai todos os números (R$, %, inteiros) dos campos de texto da `AnaliseAgente`.
- Compara com o conjunto permitido (todos os números de `FatosFinanceiros`).
- Tolerância: ±1% relativo (moeda/%) e exato (contagens).
- Número órfão ⇒ violação ⇒ modo degradado + log do REQ violado.

## 7. Sequenciamento (milestones)
- **M1 — Contratos & guardrails determinísticos** (schemas, pii, validador,
  conteúdo) + harness verde offline. *Sem LLM real ainda (FakeProvider).*
- **M2 — Providers reais** (Ollama, OpenAI-compat) + config + degradação.
- **M3 — Integração de saída** (narrativa no `.docx` e painel na GUI).
- **M4 — Empacotamento** (.exe) e ata de freeze.

## 8. Riscos técnicos
- Modelos locais pequenos podem não aderir bem ao schema → usar `instructor`
  + `MODO_DEGRADADO` como rede de segurança (P8).
- pdfplumber no PyInstaller → `--collect-all` (ver README).
