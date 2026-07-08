# SPEC — Helper Financeiro v2 (EARS)

- **Versão:** 2.3.0 (ciclo aberto) · **Status:** Ativo
- **Sintaxe:** EARS (Easy Approach to Requirements Syntax), em português
- **Regido por:** `CONSTITUTION.md` · **Detalha:** `PRD.md`

## Convenções EARS
- **Ubíquo:** "O sistema DEVE …"
- **Evento:** "QUANDO ‹gatilho›, o sistema DEVE ‹resposta›."
- **Estado:** "ENQUANTO ‹estado›, o sistema DEVE …"
- **Opcional:** "ONDE ‹recurso presente›, o sistema DEVE …"
- **Indesejado:** "SE ‹condição›, ENTÃO o sistema DEVE …"

Prefixos de `REQ-ID`: `F` funcional · `NF` não-funcional · `SEC` segurança/privacidade ·
`LLM` agente · `GRD` guardrail.

---

## 1. Requisitos funcionais (determinístico — herdados da v1)

- **REQ-F-001** — O sistema DEVE calcular parcela (Price), saldo devedor, custo
  total e CET a partir de valor, taxa e prazo.
- **REQ-F-002** — O sistema DEVE classificar a saúde financeira pelo
  comprometimento de renda (Saudável ≤30% < Atenção ≤50% < Crítico).
- **REQ-F-003** — O sistema DEVE simular quitação por avalanche e bola de neve,
  retornando meses até quitar e juros totais.
  > *Modelo declarado (auditoria F-10):* o simulador aplica juros compostos
  > sobre o saldo e abate a parcela nominal constante — uma simplificação que
  > serve à comparação **relativa** entre estratégias; os meses absolutos podem
  > divergir do cronograma Price contratual. Essa nota DEVE acompanhar o
  > relatório gerado.
- **REQ-F-004** — QUANDO o usuário fornecer um PDF de contrato, o sistema DEVE
  extrair tipo, valor, taxa, CET, nº de parcelas e valor da parcela (melhor
  esforço) e pré-preencher o formulário para conferência.
- **REQ-F-005** — O sistema DEVE gerar planilha `.xlsx`, relatório `.docx` e
  carta de proposta `.docx`.
- **REQ-F-006 (v2.2, ADR-0008)** — O sistema DEVE aceitar renda e despesas
  informadas **por categoria** (renda: salário/extra/outras; fixas: moradia,
  contas da casa, transporte, saúde, educação, assinaturas, outras;
  variáveis: mercado, lazer, vestuário, imprevistos, outras) e DEVE derivar
  os agregados do perfil **por soma determinística** no `core` (roll-up) —
  nunca por digitação separada do total.
- **REQ-F-007 (v2.2)** — O sistema DEVE calcular a cobertura da reserva de
  emergência em **meses de despesas totais** (reserva ÷ despesas); SE as
  despesas totais forem zero, ENTÃO o indicador NÃO DEVE ser exibido como
  número (sem significado).
- **REQ-F-008 (v2.2)** — QUANDO o usuário editar qualquer campo do orçamento,
  a GUI DEVE atualizar imediatamente os totais por seção, a cobertura da
  reserva e o resumo (fluxo de caixa livre e comprometimento com dívidas,
  com os limiares do REQ-F-002). *(A aritmética vive no `core`; a GUI apenas
  formata — REQ-NF-004.)*
- **REQ-F-009 (v2.2, M6)** — SE o texto de um campo numérico não for
  interpretável como número no padrão brasileiro, ENTÃO a GUI DEVE sinalizar
  o campo visualmente em vez de tratá-lo silenciosamente como zero. Campo
  vazio é válido e vale zero por design. *(A regra de interpretação vive em
  `core.utils.texto_numerico_valido`; a GUI só aplica o estilo — REQ-NF-004.)*

### 1.1 GUI web — redesign "Clareza" (v2.3, ADR-0009)

> A apresentação migra para **Electron + React/TypeScript** (`gui_web/`)
> consumindo o **sidecar** Python (REQ-NF-005). Toda a aritmética permanece no
> `core` — a casca fina agora é o TS (REQ-NF-004). Migração **paralela** ao
> `tkinter` até a paridade das 6 telas.

- **REQ-F-010 (v2.3)** — O sistema DEVE apresentar um shell de janela larga com
  topbar (marca + navegação das 6 telas) e alternância de tema; o modo escuro
  DEVE ser **persistido** (`localStorage`) e reidratado ao abrir.
- **REQ-F-011 (v2.3)** — A tela **Visão geral** DEVE exibir o diagnóstico de
  saúde (anel de comprometimento da renda), 4 métricas (renda, despesas,
  parcelas/mês, saldo devedor), a lista de dívidas ordenada e a estratégia
  recomendada — todos derivados **ao vivo** do sidecar.
- **REQ-F-012 (v2.3)** — A tela **Perfil/orçamento** DEVE apresentar a
  itemização por categoria, a barra de alocação da renda e a barra-resumo
  (fluxo / comprometimento / despesas), reusando o roll-up determinístico
  (REQ-F-006/007/008).
- **REQ-F-013 (v2.3)** — A tela **Dívidas** DEVE listar as dívidas ordenadas
  por taxa e exibir as estatísticas (saldo total, parcelas/mês, **taxa média
  ponderada pelo saldo**, custo até quitar), com CRUD (adicionar/editar/remover).
- **REQ-F-014 (v2.3)** — A tela **Contrato PDF** DEVE permitir selecionar um
  PDF, extrair os campos **localmente** com citação da fonte e exigir
  **confirmação humana** antes de usá-los (reusa REQ-F-004 e REQ-GRD-005;
  `interrupt`→resume do grafo).
- **REQ-F-015 (v2.3)** — A tela **Análise** DEVE recalcular estratégias e
  oportunidades de portabilidade conforme o pagamento extra e a taxa-alvo,
  oferecer a análise sênior (IA, sob guardrails) e exportar `.xlsx`/`.docx`.
- **REQ-F-016 (v2.3)** — A tela **Carta ao credor** DEVE oferecer os tipos de
  proposta (quitação à vista / portabilidade / redução), campos contextuais por
  tipo e pré-visualização **ao vivo**, gerando a carta `.docx`.
- **REQ-F-017 (v2.4, ADR-0012)** — Cada campo do orçamento (renda/fixas/
  variáveis) PODE ser detalhado em **rubricas** criadas pelo usuário numa
  planilha dedicada; campo com rubricas DEVE valer a **soma das rubricas**
  (roll-up no `core`) e ficar somente-leitura na aba Perfil. As rubricas
  DEVEM entrar no export `.xlsx` (aba "Orçamento detalhado").
- **REQ-F-018 (v2.4, ADR-0012)** — O estado do usuário (perfil, dívidas e
  rubricas) DEVE ser **persistido localmente** (SQLite gerido pelo sidecar em
  `%APPDATA%\HelperFinanceiro\dados.db`; `HF_DB_PATH` sobrescreve p/ testes),
  com hidratação no boot e auto-save — o app lembra o usuário entre sessões.
- **REQ-F-019 (v2.5, ADR-0013)** — O usuário PODE **arquivar a competência**
  (`AAAA-MM`): snapshot imutável do perfil + rubricas (rearquivar substitui);
  o sistema DEVE **comparar competências** (ou uma competência com o
  orçamento vivo) campo a campo — valor anterior, atual, delta e variação
  percentual calculados no `core`.
- **REQ-F-020 (v2.5, ADR-0013)** — Ao nomear uma rubrica, a GUI DEVE oferecer
  **sugestões locais** de nomes comuns por campo (autocompletar nativo, sem
  rede).
- **REQ-F-021 (v2.6, ADR-0014)** — O usuário PODE **importar um extrato/fatura
  CSV**: o parse DEVE ser determinístico no `core` (separador, colunas,
  valores BR/US, agrupamento por estabelecimento, competência sugerida pelas
  datas); a LLM local PODE **apenas rotular** os grupos com campos do
  orçamento (nenhum número passa pelo modelo; rótulo inválido é descartado);
  o sistema DEVE exigir **revisão humana** antes de aplicar e DEVE degradar
  para classificação manual sem LLM (P8). A importação **acrescenta** rubricas
  no destino escolhido (orçamento vivo ou competência) — nunca apaga.
- **REQ-F-022 (v2.6, ADR-0014)** — Com 2 ou mais competências arquivadas, o
  sistema DEVE exibir o **gráfico de evolução** (totais por seção + zoom por
  campo); as séries DEVEM vir prontas do `core` (`serie_evolucao`) — o front
  só projeta e formata (REQ-NF-005).
- **REQ-F-023 (v2.6, ADR-0014)** — QUANDO houver competências arquivadas, o
  export `.xlsx` DEVE incluir a aba **"Evolução mensal"** (campos ×
  competências, totais por seção como fórmula `=SUM` e gráfico nativo),
  sujeita ao Gate B (zero erro de fórmula).
- **REQ-F-024 (v2.7, ADR-0015)** — QUANDO um documento for um **PDF escaneado
  ou uma imagem** (JPG/PNG), o sistema DEVE detectá-lo de forma
  **determinística** (`core.documento`: densidade de texto por página para
  PDF, extensão para imagem) e passá-lo pelo **OCR local** (RapidOCR +
  PP-OCRv6, na máquina) antes da extração; sem o motor de OCR, DEVE degradar
  para preenchimento manual (P8). PDF com camada de texto NÃO passa por OCR.
- **REQ-F-025 (v2.7, ADR-0015)** — Antes da extração pela LLM, o `core` DEVE
  envolver os candidatos por **tipo** (`<valor>`, `<data>`, `<percentual>`) —
  nunca semanticamente; e a trave de citação literal DEVE tolerar o **ruído de
  glifo do OCR** (`0`↔`O`, `1`↔`l`↔`I`, `5`↔`S`, `8`↔`B`) por normalização
  determinística, **sem** afrouxar H1 (número sem citação verificável continua
  descartado).
- **REQ-F-026 (v2.7, ADR-0015)** — O usuário PODE **importar um comprovante/
  extrato escaneado** (imagem ou PDF sem texto): após o OCR local, os
  lançamentos DEVEM ser reconstruídos por layout e seguir a **mesma**
  classificação, revisão humana e regra de acréscimo da importação de CSV
  (REQ-F-021).

## 2. Requisitos do Agente (LLM)

- **REQ-LLM-001** — O sistema DEVE oferecer uma análise qualitativa produzida
  por um Agente Financeiro Sênior a partir de `FatosFinanceiros`.
- **REQ-LLM-002** — O agente DEVE retornar **saída estruturada** aderente ao
  schema `AnaliseAgente`; SE a saída não aderir, ENTÃO o sistema DEVE tentar
  1 (uma) recuperação e, persistindo a falha, cair em modo degradado (P8).
- **REQ-LLM-003** — O sistema DEVE ser **agnóstico de provedor**, suportando
  endpoint OpenAI-compatible (nuvem) e Ollama (local) via configuração.
- **REQ-LLM-004** — ENQUANTO o provedor estiver em modo `local`, o sistema DEVE
  operar sem qualquer tráfego de rede externo.
- **REQ-LLM-005** — O agente DEVE produzir: sumário executivo, diagnóstico
  interpretado, prioridades justificadas, roteiro de negociação e alertas.
- **REQ-LLM-006** — SE os fatos forem insuficientes, ENTÃO o agente DEVE
  declarar baixa confiança e NÃO preencher com suposições.

## 3. Guardrails (obrigatórios)

- **REQ-GRD-001 (H1)** — O sistema DEVE rejeitar qualquer cifra na saída do LLM
  que não corresponda a um valor dos `FatosFinanceiros` dentro da tolerância:
  **±1% relativo** para moeda/percentual e **±0** para contagens (meses,
  parcelas). SE houver cifra não fundamentada, ENTÃO o sistema DEVE marcar a
  análise como "não confiável" e cair em modo degradado.
- **REQ-GRD-002 (H2)** — QUANDO o provedor for cloud, o sistema DEVE enviar
  apenas dados anonimizados; nome, CPF e nome de credor DEVEM estar tokenizados.
- **REQ-GRD-003 (H3)** — O sistema DEVE anexar o aviso legal a toda saída
  exibida ou exportada que contenha análise do agente.
- **REQ-GRD-004 (H6)** — SE a saída do LLM contiver recomendação de investimento
  ou promessa de retorno, ENTÃO o sistema DEVE removê-la/sinalizá-la.
- **REQ-GRD-005 (H5/P5)** — O sistema DEVE tratar texto extraído de PDF como
  dado não-confiável e NUNCA enviá-lo cru ao LLM; apenas fatos tipados trafegam.
- **REQ-GRD-006 (H8)** — QUANDO um guardrail bloquear a saída do agente, o
  sistema DEVE registrar o motivo (sem PII) e ainda entregar o determinístico.

## 4. Segurança e privacidade

- **REQ-SEC-001** — O sistema NÃO DEVE persistir PII nem chaves de API em texto
  claro no repositório ou em logs.
- **REQ-SEC-002** — A chave de API DEVE ser lida de variável de ambiente.
- **REQ-SEC-003** — O mapa de anonimização (token → valor real) DEVE permanecer
  apenas em memória local durante a execução.
- **REQ-SEC-004 (v2.3, ADR-0009)** — A GUI web DEVE falar com o núcleo apenas
  por um **sidecar local** em `127.0.0.1` (porta efêmera) autenticado por
  **token por sessão**; o Electron DEVE usar `contextIsolation`/`sandbox`,
  `nodeIntegration` desligado, **CSP estrita** e **nenhum código remoto**. O
  tracing (LangSmith) e o auto-updater são **opt-in via env**: o tracing DEVE
  apontar para endpoint **local/self-hosted** (não trafega a terceiros) e o
  updater DEVE usar pacote **assinado**; nenhum deles DEVE transmitir PII.

## 5. Não-funcionais

- **REQ-NF-001** — O diagnóstico determinístico DEVE concluir em < 1 s para até
  50 dívidas.
- **REQ-NF-002** — O sistema DEVE funcionar offline (modo local ou degradado).
- **REQ-NF-003** — Toda planilha gerada DEVE ter **zero erro de fórmula**.
- **REQ-NF-004** — O código DEVE seguir a arquitetura em camadas do `PLAN`
  (core sem dependência de GUI/LLM).
- **REQ-NF-005 (v2.3, ADR-0009)** — A GUI web DEVE consumir a lógica de negócio
  **exclusivamente** do sidecar Python (contrato RPC local sobre `core`/`agent`/
  `guardrails`/`outputs`); o front **NÃO DEVE** reimplementar cálculo financeiro
  em TypeScript — fonte única da verdade, extensão do REQ-NF-004.
- **REQ-NF-006 (v2.7, ADR-0015)** — O OCR DEVE rodar **100% na máquina** do
  usuário, com os modelos **empacotados** (sem download em execução) e **sem
  rede**; a imagem/PDF com PII nunca sai do computador (H2/H7). Sem o motor
  disponível, o sistema degrada (P8), nunca recorre a OCR na nuvem.

---

## 6. Contratos de dados (Pydantic v2)

> Fonte da verdade em `contracts/schemas.py` (ADR-0004). Estes contratos são a
> fronteira entre o determinístico e o LLM.

### 6.1 `FatosFinanceiros` (entrada do agente — apenas números + tokens)
```python
class DividaFato(BaseModel):
    token: str            # "CREDOR_1" (anonimizado)
    tipo: str
    saldo_devedor: float
    taxa_mensal: float    # decimal
    taxa_anual: float
    parcela: float
    parcelas_restantes: int

class EstrategiaFato(BaseModel):
    metodo: str           # "avalanche" | "bola_de_neve"
    meses: int | None
    juros_pagos: float
    quitavel: bool
    ordem: list[str]      # tokens

class FatosFinanceiros(BaseModel):
    comprometimento_renda: float
    classificacao: str
    fluxo_caixa: float
    saldo_devedor_total: float
    juros_totais_futuros: float
    dividas: list[DividaFato]
    estrategias: list[EstrategiaFato]
    tem_deficit: bool
```

### 6.2 `AnaliseAgente` (saída do agente — texto + estrutura, sem números novos)
```python
class Prioridade(BaseModel):
    ordem: int
    credor_token: str
    justificativa: str

class PassoNegociacao(BaseModel):
    credor_token: str
    abordagem: str                 # "quitacao" | "portabilidade" | "reducao"
    argumentos: list[str]
    concessoes_possiveis: list[str]

class AnaliseAgente(BaseModel):
    sumario_executivo: str
    diagnostico_interpretado: str
    prioridades: list[Prioridade]
    roteiro_negociacao: list[PassoNegociacao]
    alertas_risco: list[str]
    confianca: float               # 0.0–1.0, auto-avaliada
```

### 6.3 `ResultadoAnalise` (o que a aplicação consome)
```python
class ResultadoAnalise(BaseModel):
    fatos: FatosFinanceiros
    analise: AnaliseAgente | None  # None em modo degradado
    modo: str                      # "completo" | "degradado"
    guardrails_violados: list[str] # ex.: ["REQ-GRD-001"]
    aviso_legal: str
```

---

## 7. Matriz de rastreabilidade (REQ → Task → Teste)
Ver `TASKS.md` (coluna "REQ") e `HARNESS.md` (coluna "Cobre"). Regra P6: todo
`REQ-GRD-*` e `REQ-LLM-*` tem teste executável no harness.
