# SPEC — Helper Financeiro v2 (EARS)

- **Versão:** 2.2.0 · **Status:** Ativo
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

## 5. Não-funcionais

- **REQ-NF-001** — O diagnóstico determinístico DEVE concluir em < 1 s para até
  50 dívidas.
- **REQ-NF-002** — O sistema DEVE funcionar offline (modo local ou degradado).
- **REQ-NF-003** — Toda planilha gerada DEVE ter **zero erro de fórmula**.
- **REQ-NF-004** — O código DEVE seguir a arquitetura em camadas do `PLAN`
  (core sem dependência de GUI/LLM).

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
