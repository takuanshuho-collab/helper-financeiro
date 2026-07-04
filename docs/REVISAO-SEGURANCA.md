# Revisão de Segurança — M4 (T-403)

- **Data:** 2026-07-04 · **Escopo:** REQ-SEC-001/002/003, H2, P8
- **Método:** varredura estática (grep) de logs/prints/segredos + leitura dos
  pontos de saída de dados (providers, cache, checkpoints, telemetria).

## 1. Chaves de API (REQ-SEC-001/002) — ✅

- `HF_API_KEY` é lida **somente** de variável de ambiente
  (`agent/config.py`), nunca hardcoded.
- A chave aparece em exatamente **um** ponto de uso: o cabeçalho
  `Authorization: Bearer` do `OpenAICompatProvider` (`agent/provider.py`).
  Nunca é logada, impressa ou serializada.
- Cloud sem chave falha cedo com `RuntimeError` — a mensagem cita o REQ,
  não a chave.
- `.gitignore` bloqueia `.env` e `*.key` (além de `dist/`, `build/`).

## 2. PII em logs (REQ-GRD-002/SEC-003) — ✅

Inventário completo de chamadas de log no código do produto:

| Local | O que loga | PII? |
|---|---|---|
| `agent/grafo.py` / `agent/agente.py` | motivos de degradação (códigos: `ERRO_PROVIDER:X`, `REQ-GRD-001:...`) | Não |
| `agent/extracao.py` | **nomes** de campos descartados (`saldo_devedor:SEM_FONTE`) e códigos de inconsistência — nunca valores nem trechos do documento | Não |
| `agent/ingestao.py` | contagem de chunks e tamanho do documento (números) | Não |
| `agent/provider.py` | host do `HF_BASE_URL` quando "local" aponta para fora (aviso de configuração) | Não |

A GUI mostra erros em `messagebox` (exibição local ao próprio usuário) e não
escreve arquivos de log.

## 3. Fronteiras de dados (H2) — ✅

- **Cloud** só recebe `FatosFinanceiros` anonimizados; o cinto `contem_pii()`
  varre o payload serializado imediatamente antes do envio (nó
  `verificar_pii`).
- **Extração de documentos** recusa provider cloud por construção
  (`obter_extrator` levanta `EXTRACAO_LOCAL_ONLY`) — o documento bruto
  contém PII e só toca o modelo local.
- **Desanonimização** acontece em um único módulo (`agent/exibicao.py`), na
  fronteira da exibição local; o mapa token→real vive apenas em memória.

## 4. Persistência e checkpoints (REQ-SEC-003) — ✅

- Cache de análises: só memória (LRU), só conteúdo aprovado, só tokens.
- Checkpointers dos grafos: `InMemorySaver` — nada em disco. Desde o M4 o
  estado carrega **apenas dicts/primitivos** (`model_dump()`), e o
  serializador usa **allowlist explícita** de tipos
  (`criar_checkpointer()` em `agent/grafo.py`): tipo não registrado não é
  mais desserializado silenciosamente.
- Observação registrada: o estado da extração contém o **texto bruto do
  documento** (PII) — aceitável porque é memória do processo, morre com a
  sessão. Persistir em disco continua **proibido** sem as condições do
  ADR-0006 (pós-anonimização + opt-in).

## 5. Telemetria — ✅

- LangSmith permanece desligado: o código não define `LANGSMITH_*`/
  `LANGCHAIN_*` em lugar nenhum (opt-in que nunca é ativado).
- Nenhuma dependência de telemetria na stack (denylist da CONSTITUTION).

## 6. Conclusão

Nenhum achado bloqueante. Duas ressalvas ficam registradas como condição de
contorno (não como pendência): o documento bruto no estado em memória da
extração (item 4) e a exibição de exceções em `messagebox` (local, sem
persistência). Aprovado para o freeze do M4.
