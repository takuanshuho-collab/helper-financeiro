# ADR-0007 — LlamaIndex como camada de ingestão local (retriever-only)

- **Status:** Aceita · **Data:** 2026-07-04
- **Relacionada a:** REQ-GRD-001/002/005, REQ-NF-002, H1/H2/H5, T-254/T-255/T-256

## Contexto

A Fase 2.5 introduz leitura de documentos financeiros não estruturados
(contratos, extratos) para alimentar a extração Code-First de variáveis
(`capital`, `taxa`, `prazo`, ...). Documentos reais estouram a janela de
contexto de um modelo de 3B (`num_ctx 8192`) e o parse por regex do
`core/extrator_pdf.py` é frágil por natureza (cada banco formata diferente).
Precisamos de: leitura de PDF, chunking, embeddings e recuperação top-k —
tudo **local** (REQ-NF-002/LGPD).

## Decisão

**LlamaIndex entra APENAS como camada de ingestão/retrieval. Nunca de síntese.**

- Pacotes mínimos: `llama-index-core`, `llama-index-embeddings-ollama`,
  `llama-index-readers-file`. **Nunca** o metapacote `llama-index` (arrasta
  integrações OpenAI) nem `llama-index-llms-*` (a síntese é nossa).
- Pipeline em `agent/ingestao.py`:
  `documento → SentenceSplitter → VectorStoreIndex (memória) → retriever top-k`.
- Embeddings: `OllamaEmbedding` com `nomic-embed-text` (~274 MB, roda no
  mesmo Ollama). **Não** `HuggingFaceEmbedding`: arrastaria torch e
  sentence-transformers, multiplicando o tamanho do freeze M4.
- **Proibido `as_query_engine()`**: o query engine chamaria um LLM por conta
  própria, por fora dos guardrails (H1/H2). Só `as_retriever()` — os chunks
  recuperados entram no NOSSO pipeline, delimitados, e passam pelos guardrails
  como qualquer outra entrada.
- Índice **em memória** por sessão (SimpleVectorStore). Persistir índice em
  disco = persistir conteúdo do documento → mesma condição do checkpointer no
  ADR-0006 (REQ-SEC-003, opt-in), adiado.

## Tratamento de segurança dos chunks (inegociável)

Texto vindo de PDF é **entrada não confiável** (H5, `PDF_MALICIOSO` do
harness):

1. Chunk recuperado passa pelo cinto de PII (H2) antes de qualquer prompt.
2. Chunk entra no prompt **delimitado** (mesmo padrão `<FATOS>`), nunca como
   instrução.
3. Números citados de chunks entram no conjunto permitido do grounding (H1)
   apenas quando o chunk participou da chamada — nunca globalmente.
4. Extração exige **citação verbatim** (`trecho_fonte`) verificada por código:
   valor sem trecho correspondente no documento é descartado (anti-alucinação
   na entrada, espelho do H1 na saída).

## Consequências

- Extratos/contratos de qualquer formato passam a ser legíveis sem regex por
  banco; o `core/extrator_pdf.py` (regex) vira fallback determinístico.
- Custo assumido: `llama-index-core` puxa pandas/aiohttp/sqlalchemy (~40
  pacotes). **Spike T-257 (2026-07-04): freeze PyInstaller `--onefile` com
  langgraph + llama-index-core fecha em ~84 MB, sem nenhum `--collect-*`
  extra, e o pipeline (grafo + verificador + ingestão) roda no .exe.** Risco
  M4 aceito; se um dia o tamanho incomodar, o fallback registrado é mover a
  ingestão para grupo opcional (`uv sync --group rag`) e o produto degrada
  para o extrator regex (P8 na entrada).
- O bench de embeddings fica fora do escopo: `nomic-embed-text` é o padrão
  até dados dizerem o contrário.
