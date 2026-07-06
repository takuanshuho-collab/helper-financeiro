# ADR-0010 — Extração PDF→Markdown (pymupdf4llm) e LLM local OpenAI-compatible

- **Status:** Aceita (2026-07-05)
- **Contexto de processo:** ajuste dentro do ciclo **v2.3.0** (aberto pela
  ADR-0009), surgido durante o T-901 (tela Contrato PDF). Toca código nascido
  na Fase 2.5 (extração Code-First, ADR-0006/0007) e nos providers (ADR-0002/
  0005). Refina a **invariante H2** (ver §Decisão B) sem afrouxá-la.

## Contexto

Ao testar o T-901 com um modelo local, a extração assistida por IA **nunca
rodava**: o banner caía sempre em "extração clássica". Duas causas somadas:

1. **Extrator de texto fraco para a LLM.** O `pdfplumber` (`extract_text`)
   achata tabelas — e contratos são cheios delas (grade de taxas, cronograma de
   parcelas). O regex clássico, no melhor caso, recupera `tipo` e `taxa`; saldo
   e parcela ficam de fora. Sem estrutura, a LLM também extrai mal.
2. **Servidor local não-Ollama não era suportado.** O mantenedor roda o modelo
   no **LM Studio** (porta `1234`, API **OpenAI-compatible** `/v1`). O código:
   - apontava por padrão para o Ollama (`localhost:11434`, API nativa
     `/api/chat`) — porta e dialeto errados; e
   - **recusava** `provider="openai_compat"` para extração
     (`EXTRACAO_LOCAL_ONLY`), assumindo que "openai_compat = nuvem = risco de
     PII". Um LM Studio em **loopback** é local, mas caía nessa trava.

A licença do `pymupdf4llm`/PyMuPDF é **AGPL-3.0**. O mantenedor confirmou que o
app **não é distribuído comercialmente** (sem SaaS), então a AGPL é aceitável
neste projeto — o bloqueio deixa de existir.

## Decisão

### A. Extração de texto: PDF → **Markdown** com `pymupdf4llm`

- O sidecar passa a extrair o documento como **Markdown** (`pymupdf4llm.
  to_markdown`), preservando títulos e **tabelas** — muito mais sinal para a
  LLM de extração. Abertura **em memória** (`pymupdf.open(stream=..., filetype=
  "pdf")`): o documento bruto (com PII) nunca toca o disco (H2).
- **Fallback MIT:** se o `pymupdf4llm` faltar ou falhar, `extrair_markdown_pdf_
  bytes` devolve `""` e o chamador usa o `pdfplumber` (`extrair_texto_pdf_bytes`,
  licença MIT). A **extração clássica por regex** continua rodando sobre o
  **texto plano** do pdfplumber — comportamento inalterado.
- O Markdown alimenta **a LLM**; o regex clássico segue no texto plano.

### B. LLM local OpenAI-compatible + invariante H2 **por endpoint**

- A invariante do H2 passa a ser o **endpoint**, não o nome do provider:
  `ConfigAgente.endpoint_local` é `True` para **loopback** (`localhost`,
  `127.0.0.0/8`, `::1`). O documento/os fatos só "saem da máquina" quando o
  endpoint é **remoto**.
- **Extração** (`obter_extrator`): permitida para **qualquer** endpoint local;
  recusada (`EXTRACAO_LOCAL_ONLY`) apenas para endpoints remotos. O **dialeto**
  segue o provider — `OllamaExtrator` (nativo `/api/chat`) ou o novo
  **`OpenAICompatExtrator`** (`/v1/chat/completions` + `response_format`
  json_schema, para LM Studio/llama.cpp/vLLM).
- **Análise** (`OpenAICompatProvider`): a `api_key` passa a ser exigida **só**
  para endpoints remotos (SEC-002); um servidor local em loopback dispensa
  chave. O `Authorization` só é enviado quando há chave.
- **Guardrail de PII** (`verificar_pii`): a varredura pré-envio (REQ-GRD-002)
  incide **quando o endpoint é remoto** — antes olhava `provider ==
  "openai_compat"`. Isso é mais correto: pega até um `provider="local"` mal
  configurado apontando para fora.

### C. Configuração para o LM Studio

Apontar o sidecar via ambiente: `HF_PROVIDER=openai_compat`,
`HF_BASE_URL=http://localhost:1234/v1`, `HF_MODEL=<id do modelo no LM Studio>`.

## Alternativas consideradas

- **Manter só o pdfplumber** (MIT): permissivo, mas mantém a extração fraca em
  tabelas — o problema que originou a ADR. Fica como **fallback**.
- **Markdown "caseiro" via `pdfplumber.extract_tables()`** (MIT): capturaria
  parte do ganho sem AGPL. Descartado porque a licença deixou de ser bloqueio e
  o `pymupdf4llm` entrega Markdown estruturado com muito menos código próprio.
- **Novo `provider="local_openai"`**: explícito, mas duplicaria semântica. A
  invariante **por endpoint** (loopback) é mais simples e mais correta.
- **Tratar loopback OpenAI-compat como nuvem** (status quo): bloquearia o LM
  Studio local sem ganho de segurança — o tráfego nunca sai da máquina.

## Consequências

- **Positivas:** extração muito melhor (Markdown/tabelas → a LLM recupera
  saldo/parcela/prazo, não só tipo/taxa); suporte a servidores locais
  OpenAI-compatible (LM Studio hoje; llama.cpp/vLLM de graça) — inclusive para a
  Análise (T-902); invariante H2 mais precisa (baseada em onde o dado vai, não
  no rótulo do provider).
- **Custos / riscos:** dependência **AGPL** (`pymupdf4llm`/PyMuPDF) — aceitável
  só enquanto o app não for distribuído comercialmente; se isso mudar, revisar
  (fallback pdfplumber já cobre). Footprint maior no PyInstaller (PyMuPDF nativo
  + `onnxruntime`). A citação (`trecho_fonte`) exibida pode conter marcas de
  Markdown — cosmético.
- **Governança:** os testes que codificavam "openai_compat = nuvem" foram
  atualizados para a semântica **remoto = nuvem** (mesma intenção do H2). Sem
  alteração de requisito congelado além do refino aqui registrado.
```
