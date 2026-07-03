# 💰 Helper Financeiro

Programa de desktop (tkinter) que analisa a situação financeira do usuário,
lê contratos de empréstimo em PDF, define estratégias de quitação e gera
**planilha (.xlsx)**, **relatório (.docx)** e **cartas de proposta ao credor (.docx)**.

---

## 🧠 Como o projeto é organizado

A ideia central é separar o **cérebro** (contas) da **casca** (janela) e das
**saídas** (arquivos). É como uma cozinha profissional: o chef (`core`) sabe
cozinhar sem se importar com o salão; o salão (`gui`) serve; e a copa (`outputs`)
embala para viagem. Trocar o salão não muda a receita.

```
helper_financeiro/
├── main.py                 # ponto de entrada: abre a janela
├── requirements.txt
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
└── gui/
    └── app.py              # SALÃO — janela tkinter com 5 abas
```

Por que essa separação importa para você: se um dia quiser trocar a janela por
uma versão web, ou expor tudo via linha de comando, **nada do `core` muda**.

---

## ▶️ Como rodar (modo desenvolvedor)

```bash
# 1. (opcional) criar ambiente virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate

# 2. instalar dependências
pip install -r requirements.txt

# 3. rodar
python main.py
```

> No Linux, se der erro de `tkinter`, instale: `sudo apt install python3-tk`.
> No Windows não é necessário — já vem com o Python.

---

## 🖥️ Fluxo de uso

1. **Aba Perfil** — informe renda, despesas, reserva e FGTS.
2. **Aba Dívidas** — cadastre cada dívida (credor, tipo, saldo, taxa, parcela).
3. **Aba Contrato PDF** *(opcional)* — selecione um contrato; os campos são
   extraídos e jogados no formulário da aba Dívidas para você **conferir**.
   ⚠️ O contrato traz os valores **originais**; ajuste o **saldo devedor atual**
   e as **parcelas restantes** antes de adicionar.
4. **Aba Análise** — defina o pagamento extra mensal e a taxa-alvo de
   portabilidade, clique em **Analisar** e gere a **planilha** e o **relatório**.
5. **Aba Carta ao credor** — escolha a dívida e o tipo de proposta (quitação,
   portabilidade ou redução) e gere a carta.

---

## 📦 Como gerar o `.exe` (PyInstaller)

O `pdfplumber` carrega arquivos de dados que o PyInstaller não detecta sozinho,
então usamos `--collect-all` para ele e suas dependências:

```bash
pip install pyinstaller

pyinstaller --noconfirm --onefile --windowed ^
  --name "HelperFinanceiro" ^
  --collect-all pdfplumber ^
  --collect-all pdfminer ^
  --collect-data docx ^
  main.py
```

> `^` é a continuação de linha no **CMD do Windows**. No PowerShell use `` ` ``;
> em Linux/macOS use `\`.

O executável final fica em `dist/HelperFinanceiro.exe`.

Dica: se o `.exe` reclamar de módulo faltando ao abrir um PDF, rode uma vez pelo
terminal (`HelperFinanceiro.exe` a partir do CMD) para ver a mensagem de erro e
adicione o pacote em falta com outro `--collect-all`.

---

## 🔒 Privacidade

Tudo roda **localmente**: os dados financeiros e os PDFs não saem da sua máquina.
Nenhuma informação é enviada pela internet.

---

## ⚠️ Aviso

Esta ferramenta é de **apoio à decisão** com base nos dados informados. Não
constitui aconselhamento financeiro ou de investimento personalizado. Taxas de
mercado e regras de programas de renegociação (ex.: Desenrola) mudam com
frequência — confirme os números vigentes antes de decidir.

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
pip install -r requirements-dev.txt
pytest -q            # 20 testes verdes, offline
python demo_agente.py
```

O provider é **agnóstico**: por padrão aponta para **Ollama local** (LGPD /
offline); pode usar endpoint OpenAI-compatible na nuvem via variáveis de
ambiente. Ver `docs/ADR-0002` e `agent/config.py`.
