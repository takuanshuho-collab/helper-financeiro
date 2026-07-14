# 💰 Helper Financeiro

Programa de desktop que analisa a situação financeira do usuário,
lê contratos de empréstimo em PDF, define estratégias de quitação e gera
**planilha (.xlsx)**, **relatório (.docx)** e **cartas de proposta ao credor (.docx)**.

Desde o ciclo v2.3 (ADR-0009) a interface oficial é a **GUI web** (Electron +
React) falando com o núcleo Python por um **sidecar local**; a janela tkinter
clássica segue como fallback (`--tkinter`). O ciclo v2.4 (ADR-0012) trouxe o
**orçamento detalhado por rubricas** (planilha editável dentro do app) e a
**persistência local**: perfil, dívidas e rubricas ficam salvos entre sessões.
O ciclo v2.5 (ADR-0013) adicionou o **histórico mensal**: arquive a
competência e compare os meses ("seu mercado subiu 12,5%"), com sugestões de
nomes ao criar rubricas. O ciclo v2.6 (ADR-0014) fechou o circuito do dado:
**importe o extrato/fatura CSV** do banco (a IA local só sugere a
classificação — você revisa antes de aplicar), acompanhe o **gráfico de
evolução** por categoria e leve o histórico para o `.xlsx` (aba "Evolução
mensal"). O ciclo v2.7 (ADR-0015) trouxe o **OCR local**: contrato, comprovante
ou extrato **escaneado** (foto/PDF sem texto) é lido por OCR **na sua máquina**
(RapidOCR + PP-OCRv6 medium, modelos embarcados — sem rede) e alimenta a mesma
extração do Contrato e a mesma importação do CSV. O ciclo v2.8 (ADR-0016)
transformou o app num **cofre**: senha mestra + **TOTP** com códigos de
recuperação (sem backdoor), banco local cifrado com **SQLCipher** e auto-lock —
e a **IA local deixou de exigir programa de terceiros**: o `llama-server`
(llama.cpp) vem embarcado e o próprio app baixa o modelo (catálogo verificado
por SHA-256) ou aceita um `.gguf` seu; quem já usa Ollama/LM Studio continua
podendo apontar para ele (`HF_BASE_URL`). O ciclo v2.9 (ADR-0017) foi de
**saúde de código**: auditoria completa (34 achados), 26 correções com teste
de regressão — destaque para o **Job Object** que garante que nenhum
`llama-server` fica órfão nem num encerramento forçado — e dependências
órfãs removidas (instalador ~21 MB menor). Nenhum recurso novo, zero
mudança de comportamento visível. O ciclo v2.10 (ADR-0018) atualizou o
**Electron para a versão atual (43)** — dez majors de uma vez, eliminando os
CVEs conhecidos — mantendo tudo como estava para o usuário.

---

## 🧠 Como o projeto é organizado

A ideia central é separar o **cérebro** (contas) da **casca** (janela) e das
**saídas** (arquivos). É como uma cozinha profissional: o chef (`core`) sabe
cozinhar sem se importar com o salão; o salão (`gui`) serve; e a copa (`outputs`)
embala para viagem. Trocar o salão não muda a receita.

```
helper_financeiro/
├── main.py                 # ponto de entrada: GUI web (fallback --tkinter)
├── pyproject.toml          # dependências + config de ruff/mypy/pytest/coverage
├── core/                   # CÉREBRO — Python puro, sem interface
│   ├── models.py           # Divida, PerfilFinanceiro (as "fichas")
│   ├── utils.py            # parse/format de valores em padrão brasileiro
│   ├── calculos.py         # Price, saldo devedor, CET, portabilidade
│   ├── diagnostico.py      # comprometimento, fluxo, ranking, classificação
│   ├── estrategias.py      # avalanche, bola de neve, simulador de quitação
│   └── extrator_pdf.py     # lê o PDF e acha os campos do contrato
├── outputs/                # COPA — gera os arquivos
│   ├── planilha.py         # .xlsx com fórmulas e gráfico
│   ├── relatorio.py        # .docx de análise
│   └── proposta.py         # .docx da carta de negociação
├── sidecar/                # FRONTEIRA — FastAPI em loopback + token (ADR-0009)
├── gui_web/                # SALÃO oficial — Electron + React/TS (6 telas)
└── gui/
    └── app.py              # SALÃO clássico (tkinter) — fallback
```

Por que essa separação importa para você: se um dia quiser trocar a janela por
uma versão web, ou expor tudo via linha de comando, **nada do `core` muda**.

---

## ▶️ Como rodar (modo desenvolvedor)

O projeto usa [uv](https://docs.astral.sh/uv/) para gerenciar ambiente e
dependências (declaradas em `pyproject.toml`, travadas em `uv.lock`):

```bash
# 1. instalar dependências Python (cria .venv automaticamente)
uv sync

# 2. instalar o front (uma vez)
cd gui_web && npm install && cd ..

# 3. rodar a GUI web (oficial)
uv run python main.py            # equivale a `npm start` em gui_web/

# alternativa: a janela tkinter clássica (fallback)
uv run python main.py --tkinter
```

> Instalador para usuário final (sem Python/Node): `cd gui_web && npm run dist`
> gera o `Helper Financeiro Setup <versão>.exe` (T-1001; requer o sidecar
> congelado: `uv run --group build pyinstaller SidecarHF.spec --noconfirm`).

> No Linux, se o fallback der erro de `tkinter`, instale: `sudo apt install python3-tk`.
> No Windows não é necessário — já vem com o Python.

---

## 🖥️ Fluxo de uso

1. **Aba Perfil** — preencha o orçamento mensal por categoria (renda,
   despesas fixas e variáveis, reserva e FGTS); os totais, a cobertura da
   reserva e o fluxo de caixa são calculados na hora. O botão **Detalhar
   orçamento** abre a planilha de **rubricas** (v2.4): individualize cada
   gasto ("Conta de luz", "Internet"...) e o campo do Perfil passa a valer a
   soma. Tudo que você digita é **salvo automaticamente** e volta na próxima
   abertura.
2. **Aba Dívidas** — cadastre cada dívida (credor, tipo, saldo, taxa, parcela).
3. **Aba Contrato PDF** *(opcional)* — selecione um contrato; os campos são
   extraídos e jogados no formulário da aba Dívidas para você **conferir**.
   ⚠️ O contrato traz os valores **originais**; ajuste o **saldo devedor atual**
   e as **parcelas restantes** antes de adicionar.
4. **Aba Análise** — defina o pagamento extra mensal e a taxa-alvo de
   portabilidade, clique em **Analisar** e gere a **planilha** e o **relatório**.
   O botão **🧠 Gerar análise sênior** consulta o CONSELHEIRO (IA local, leva
   alguns minutos — a janela continua utilizável) e mostra a narrativa num
   painel rotulado *assistido por IA*; se o LLM falhar, um indicador de **modo
   degradado** aparece e o diagnóstico determinístico continua valendo. A
   última análise aprovada entra no relatório `.docx` em seção própria.
5. **Aba Carta ao credor** — escolha a dívida e o tipo de proposta (quitação,
   portabilidade ou redução) e gere a carta.

---

## 📦 Como gerar o `.exe` (PyInstaller, T-401)

Uma linha, usando o próprio ambiente do uv (o spike T-257 provou que o
langgraph congela sem `--collect` extra; só o `pdfplumber` e o
`python-docx` carregam dados que o PyInstaller não detecta sozinho):

```bash
uv run --with pyinstaller pyinstaller --noconfirm --onefile --windowed \
  --name HelperFinanceiro \
  --collect-all pdfplumber --collect-all pdfminer --collect-data docx \
  main.py
```

> No **PowerShell** troque `\` por `` ` `` no fim das linhas (ou escreva tudo
> numa linha só); no **CMD** use `^`.

O executável final fica em `dist/HelperFinanceiro.exe`. A IA local continua
opcional no `.exe`: sem Ollama instalado, o programa funciona normalmente e o
painel de IA degrada com o motivo indicado (P8).

Dica: se o `.exe` reclamar de módulo faltando, rode uma vez pelo terminal
(`dist\HelperFinanceiro.exe` a partir do CMD) para ver a mensagem de erro e
adicione o pacote em falta com outro `--collect-all`.

---

## 🔒 Privacidade

Tudo roda **localmente**: os dados financeiros, os PDFs e os extratos CSV não
saem da sua máquina. O estado do app (perfil, dívidas e rubricas) fica num
banco local em `%APPDATA%\HelperFinanceiro\dados.db` — desde o v2.8
**cifrado com SQLCipher**, protegido por senha mestra + TOTP (cofre sem
backdoor: perdeu a senha E os códigos de recuperação, os dados são
irrecuperáveis por design). A única exceção de rede é **opt-in**: o download
do modelo de IA no 1º uso (catálogo com SHA-256 verificado, REQ-NF-007);
análises, OCR e extração nunca tocam a internet.

---

## ⚠️ Aviso

Esta ferramenta é de **apoio à decisão** com base nos dados informados. Não
constitui aconselhamento financeiro ou de investimento personalizado. Taxas de
mercado e regras de programas públicos de renegociação e feirões de dívida
mudam com frequência (e programas terminam) — confirme os números e a vigência
antes de decidir.

---

## 🧭 v2 — Spec-Driven Development + Agente Financeiro Sênior

A v2 adiciona uma camada de IA (**CONSELHEIRO**, agente financeiro sênior via
LLM) sob **guardrails** que garantem correção numérica, privacidade (LGPD) e
conformidade, tudo governado por artefatos SDD prontos para uma IDE.

Princípio central: **o `core/` determinístico é a única fonte de verdade dos
números; o LLM só interpreta.** Um validador pós-geração rejeita qualquer cifra
inventada, e o sistema **degrada com segurança** (entrega o determinístico) se o
LLM falhar.

Estrutura nova:
```
docs/         # PRD, SPEC (EARS), PLAN, TASKS, HARNESS, CONSTITUTION, ADRs, FREEZE
AGENTS.md     # guia para o agente de código na IDE
agent/        # schemas, prompts, provider (agnóstico), orquestração
guardrails/   # pii, validador_numerico, conteudo
tests/        # harness (pytest) — roda offline com FakeProvider
```

Comece por [`docs/INDEX.md`](docs/INDEX.md). Rodar o harness:
```bash
uv sync --group dev
uv run pytest -q             # harness verde, offline
uv run python demo_agente.py
```

Qualidade (mesmos portões do CI — ver `.github/workflows/ci.yml`):
```bash
uv run ruff check .
uv run mypy core agent guardrails outputs contracts scripts main.py
uv run pre-commit install    # instala os hooks de commit (uma vez)
```

### Usando o CONSELHEIRO com um LLM de verdade (M2)

Desde o v2.8 (ADR-0016) **nenhum programa de terceiros é necessário**: o
`llama-server` (llama.cpp) viaja embarcado no pacote e o modelo GGUF é
instalado pelo próprio app (tela "Configuração da IA"). O provider continua
**agnóstico** (ADR-0002/0005): defina `HF_BASE_URL` para usar o seu
Ollama/LM Studio (a env definida tem precedência sobre o runtime embarcado);
um endpoint OpenAI-compatible na nuvem entra por variável de ambiente e **só
recebe dados anonimizados** (H2).

```bash
# 1. instalar o Ollama (https://ollama.com) e baixar os modelos
ollama pull qwen2.5:3b        # padrão: roda 100% numa GPU de 4 GB
ollama pull nomic-embed-text  # embeddings da ingestão de documentos (M2.5)

# 2. (opcional) validar a integração e comparar modelos
uv run pytest -m ollama
uv run python scripts/bench_schema.py --modelos qwen2.5:3b qwen3:4b --n 5
```

> **Licença do modelo:** `qwen2.5:3b` usa a Qwen Research License (não
> comercial). Para uso comercial, `HF_MODEL=qwen3:4b` (Apache 2.0) — ver
> ADR-0006.

| Variável | Padrão | Para quê |
|---|---|---|
| `HF_PROVIDER` | `local` | `local` (Ollama) · `openai_compat` (nuvem) · `fake` (testes) |
| `HF_BASE_URL` | `http://localhost:11434/v1` | endpoint do provider |
| `HF_MODEL` | `qwen2.5:3b` | modelo a usar |
| `HF_API_KEY` | *(vazia)* | chave da nuvem — **só via ambiente** (REQ-SEC-002) |
| `HF_MODO_DEGRADADO` | `0` | `1` pula o LLM e entrega só o determinístico (P8) |
| `HF_TIMEOUT` | `60` | timeout por chamada, em segundos |
| `HF_CACHE` | `1` | cache em memória de análises aprovadas (T-205) |

Se o LLM estiver fora do ar, sem chave ou desobedecer aos guardrails, o
sistema **degrada com segurança**: você sempre recebe o diagnóstico
determinístico completo, com o motivo registrado.

### Extração Code-First de contratos e extratos (M2.5)

O pipeline agora é um **grafo LangGraph** (ADR-0006) e sabe ler documentos
(ADR-0007): o **modelo extrai** as variáveis (`capital`, `taxa`, `prazo`...),
o **código verifica e calcula**, e **você confirma** antes de qualquer uso:

- cada campo extraído exige a **citação literal** do documento — valor sem
  fonte verificável é descartado automaticamente;
- os campos são checados entre si (a parcela recalculada via Price precisa
  bater com a extraída);
- o fluxo **pausa** para você conferir os campos (mesma filosofia do "confira
  antes de adicionar" da aba Contrato PDF) — a tela chega no M3;
- a extração roda **somente no modelo local**: o documento bruto (com seus
  dados) nunca sai da máquina;
- se o modelo falhar, o extrator regex clássico continua funcionando.
