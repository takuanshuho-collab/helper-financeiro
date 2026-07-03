# PRD — Helper Financeiro v2

- **Produto:** Helper Financeiro (desktop, offline-first)
- **Versão do documento:** 2.0.0
- **Status:** Proposto
- **Codinome da camada de IA:** CONSELHEIRO (Agente Financeiro Sênior)
- **Depende de:** `docs/CONSTITUTION.md`

---

## 1. Problema

Pessoas endividadas raramente têm clareza de (a) quão comprometida está a
renda, (b) qual dívida atacar primeiro, e (c) como negociar com o credor. Os
números existem nos contratos, mas ninguém traduz isso em **decisão** e em
**ação** (uma carta, uma ordem de ataque, um pedido de portabilidade).

A v1 já resolve o cálculo determinístico. Falta a camada de **interpretação
sênior**: transformar indicadores em uma leitura de analista experiente e em um
roteiro de negociação — sem cair em imprecisão ou em aconselhamento indevido.

## 2. Objetivo (v2)

Adicionar um **Agente Financeiro Sênior via LLM** que interpreta os fatos
determinísticos e produz análise qualitativa, priorização justificada e
roteiro de negociação, sob **guardrails** que garantem correção numérica,
privacidade (LGPD) e conformidade (não é aconselhamento licenciado). Tudo
empacotado como projeto **Spec-Driven**, pronto para evoluir dentro de uma IDE
com agente de código.

## 3. Usuários

| Persona | Necessidade | Nível técnico |
|---|---|---|
| **Endividado (usuário final)** | Entender a situação e saber o próximo passo | Baixo |
| **Orientador informal** (parente/RH) | Gerar relatório e carta para ajudar alguém | Médio |
| **Desenvolvedor (mantenedor)** | Evoluir o projeto com segurança na IDE | Médio |

## 4. Metas de sucesso

| Métrica | Alvo |
|---|---|
| Correção numérica da saída do agente | 100% (todo número rastreável ao `core`) |
| Vazamento de PII para LLM cloud | 0 |
| Execução ponta-a-ponta sem internet | Sim (modo local ou degradado) |
| Cobertura de REQs por testes no harness | 100% dos REQ-GRD e REQ-LLM |
| Tempo do diagnóstico determinístico | < 1 s (sem contar o LLM) |

## 5. Escopo

### 5.1 Dentro do escopo (v2)
- Camada de agente LLM (CONSELHEIRO) com saída estruturada (Pydantic).
- Guardrails: consistência numérica, anonimização de PII, filtro de conteúdo,
  injeção de aviso legal, degradação segura.
- Provider **agnóstico** (OpenAI-compatible): nuvem **ou** Ollama local.
- Harness de avaliação executável (pytest) com casos-ouro e "LLM-as-judge"
  opcional.
- Suite de artefatos SDD e guia para IDE (`AGENTS.md`).
- Integração da narrativa do agente no relatório `.docx` e na GUI.

### 5.2 Fora do escopo (v2)
- OCR de contratos escaneados (fica para v3 — reaproveitar ÓCULO/OnnxTR).
- Open Finance / puxar dados bancários automaticamente.
- Multiusuário, nuvem, sincronização.
- Qualquer recomendação de investimento.

## 6. Restrições e premissas
- **RES-1:** Roda em Windows (empacotável como `.exe`), Python 3.12+.
- **RES-2:** LGPD — anonimização obrigatória antes de LLM cloud (P3, H2).
- **RES-3:** Não é aconselhamento financeiro licenciado (P4).
- **RES-4:** Regras de programas (ex.: Desenrola) mudam; o sistema não as
  "fixa" em código como verdade permanente — ver `NEEDS_CLARIFICATION`.

## 7. Riscos
| Risco | Mitigação |
|---|---|
| LLM alucina números | Guardrail H1 (validador numérico) + P1 |
| PII vaza para nuvem | Anonimização H2 + modo local-first |
| Prompt injection via PDF | P5/H5: fatos tipados, texto de PDF nunca é comando |
| Usuário trata saída como conselho garantido | P4/H3: aviso legal em toda saída |
| Custo/latência de API | Modo local (Ollama) + cache + degradação segura |

## 8. Questões abertas (NEEDS_CLARIFICATION)
- **NC-1:** Modo **local-first é mandatório** (Ollama sempre) ou nuvem é
  aceitável desde que anonimizada? *(Assunção atual: agnóstico, com local
  como padrão recomendado.)*
- **NC-2:** Há requisito de **operação 100% offline**? *(Assunção: sim, com
  degradação segura quando não houver LLM.)*
- **NC-3:** Orçamento de **custo/tokens** por análise, se usar nuvem?
- **NC-4:** Deve-se **incluir dados do Desenrola** vigente na análise, sabendo
  que a regra expira/muda? *(Assunção: mencionar como contexto, sempre com
  ressalva de verificar vigência.)*
