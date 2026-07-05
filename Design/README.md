# Handoff: Helper Financeiro — App de diagnóstico e negociação de dívidas

## Overview
Helper Financeiro é uma ferramenta que ajuda uma **pessoa endividada a organizar as próprias finanças**: cadastra orçamento e dívidas, recebe um **diagnóstico de saúde financeira** (Saudável / Atenção / Crítico), simula **estratégias de quitação** (avalanche e bola de neve), avalia **portabilidade**, e gera uma **carta de negociação** ao credor. Existe hoje como programa desktop em Python/tkinter; este handoff cobre o **redesign moderno** (direção visual "Clareza", tom fintech jovem) como um app desktop de janela larga com **dashboard central + 6 seções**.

Todos os números do dashboard, das estratégias, da portabilidade e da narrativa da "IA" são **calculados ao vivo** a partir do orçamento e das dívidas — não são estáticos.

## About the Design Files
O arquivo neste pacote (`Helper Financeiro App.dc.html`) é uma **referência de design criada em HTML** — um protótipo de alta fidelidade que demonstra aparência e comportamento pretendidos, **não é código de produção para copiar diretamente**. Ele usa um pequeno runtime interno ("DC") só para o protótipo; ignore-o. A tarefa é **recriar estas telas no ambiente do codebase de destino** (React, Vue, SwiftUI, etc.) usando os padrões e bibliotecas já estabelecidos ali. Se ainda não existe um ambiente, escolha o framework mais adequado (recomendado: React + TypeScript, dado o desktop de janela larga) e implemente lá.

A lógica financeira do programa original (Python) é a **fonte de verdade** dos cálculos e deve ser reproduzida fielmente (ver seção "Regras de negócio").

## Fidelity
**Alta fidelidade (hi-fi).** Cores, tipografia, espaçamento e interações são finais. Recrie a UI fielmente usando as bibliotecas do codebase. Os valores exatos estão em "Design Tokens".

---

## Layout global (shell)
- **Janela**: 1280×840 px, cantos arredondados 16px, `overflow:hidden`, sombra `0 30px 80px -30px rgba(60,45,20,.45)`. Fundo da área externa `#d9d4c9`; fundo do app `#f4f1ea`; texto base `#2a2435`. Coluna flex (topbar fixa + área de conteúdo rolável).
- **Topbar** (`.bbar`, altura ~62px, `padding:14px 26px`, fundo `#fff`, borda inferior `#ece7dd`):
  - **Marca**: quadrado 34px, radius 10, gradiente `135deg,#6a5bf0→#4a38d8`, ícone de cifrão branco. Ao lado: nome "Helper Financeiro" (15px/800) + kicker "DIAGNÓSTICO · ESTRATÉGIAS · PROPOSTAS" (9px, uppercase, tracking .15em, cor `#6a5bf0`).
  - **Navegação** (`.bnav`): 6 abas — Visão geral, Perfil, Dívidas, Contrato PDF, Análise, Carta ao credor. Item: 13px/600, cor `#8a8394`, padding `9px 14px`, radius 11. Hover: fundo `#f4f1fb`, cor `#6a5bf0`. Ativo (`.on`): fundo `#efecfe`, cor `#5343e0`.
  - **Direita** (`.bava`): botão de tema (lua/sol, 38px, radius 11) + nome do usuário + avatar circular 38px (gradiente `135deg,#ff9a76→#ff7a59`, iniciais).
- **Conteúdo** (`.scr`): rolável, `padding:24px 30px 30px`. Scrollbar fina 9px, thumb `#d8d0c2`.
- **Cabeçalho de tela** (`.head`): H1 22px/800 (tracking -.5px) + subtítulo 13px `#8a8394`, e à direita geralmente um "pill" de status.

## Telas / Views

### 1. Visão geral (dashboard)
- **Saudação** "Olá, {primeiroNome} 👋" + pill de saúde à direita.
- **Hero** (`.card.hero`, grid `1fr 250px`): à esquerda kicker "DIAGNÓSTICO DE SAÚDE FINANCEIRA", rótulo grande (32px/800) na cor da saúde (ex.: "Atenção"), subtítulo, e um parágrafo descritivo que cita % de comprometimento e a folga mensal. À direita, um **anel de progresso** (conic-gradient) de 150px mostrando o % da renda comprometido com parcelas.
- **4 métricas** (`.grid4` de `.mcard`): Renda líquida, Despesas, Parcelas/mês, Saldo devedor — cada uma com chip de ícone colorido, valor 23px/800 e uma linha de delta.
- **Duas colunas** (`.cols` `1.12fr 1fr`):
  - **Suas dívidas**: lista ordenada da mais cara para a mais barata; cada linha tem chip com iniciais do tipo (cor pela faixa de taxa), nome do tipo + selo "Mais cara" na primeira, credor · nº de parcelas, saldo e taxa.
  - **Estratégia de quitação**: card "Avalanche" (vencedora, selo "Recomendada") e "Bola de neve" (alternativa), cada um com meses para quitar + juros pagos; botão "Ver análise completa →".

### 2. Perfil e orçamento
- Card de identidade (Nome, CPF).
- **Barra "Para onde vai a sua renda"** (`.allocbar`): segmentos empilhados Fixas (vermelho `#fa5252`) / Variáveis (laranja `#e8890c`) / Parcelas (violeta `#5343e0`) / Sobra (verde `#12b886`), com legenda mostrando valor + % da renda; "Sobra no mês" em destaque à direita. Larguras animadas (`width .35s cubic-bezier(.4,0,.2,1)`).
- **Quatro cards de categoria** em grid 2×2, cada um com cabeçalho de seção (chip de ícone + nome + **total da categoria à direita**):
  - Renda líquida mensal (ícone verde): Salário/benefício líquido, Renda extra/autônoma, Outras rendas.
  - Despesas fixas (ícone vermelho): Moradia, Contas da casa, Transporte, Saúde, Educação, Assinaturas/academia, Outras fixas.
  - Despesas variáveis (ícone laranja): Mercado, Lazer/delivery, Vestuário/cuidados, Imprevistos, Outras variáveis.
  - Reserva e FGTS (ícone violeta): Reserva de emergência, Saldo de FGTS, e "Cobertura da reserva" (meses).
  - Campos monetários usam o input `.ipre` com prefixo "R$" e texto alinhado à direita.
- **Barra-resumo** (`.sumbar`, 3 colunas): Fluxo de caixa livre, Comprometimento com dívidas (%), Despesas totais.

### 3. Dívidas
- **Faixa de estatísticas** (`.dstats`, 4 tiles): Saldo devedor total, Parcelas por mês, Taxa média (a.m., **ponderada pelo saldo**), Custo até quitar (Σ parcela×restantes).
- **Lista de dívidas** (`.dcard`), ordenada por taxa desc.: acento colorido à esquerda (`border-left:4px solid` cor da faixa), chip de iniciais, tipo + selo "Mais cara", credor · parcela · nº restante, e uma **barra de participação** no saldo total ("X% do saldo total"). Botões editar/remover (`.iconbtn`) à direita.
- **Formulário** (coluna direita): Credor, Tipo (select), Saldo devedor, Taxa % a.m., Parcela, Parcelas restantes, botão "+ Adicionar dívida". Editar preenche o formulário e vira "Salvar dívida".
- Estado vazio quando não há dívidas.

### 4. Contrato PDF (extração)
- **Drop-zone** (`.dropzone`, tracejada violeta): "Arraste o contrato aqui ou selecione um PDF", subtítulo reforçando **offline/privado**, botões "Selecionar contrato PDF…" e "Extrair com IA local".
- **Idle**: card "Como funciona" com 3 passos numerados (Selecione → IA extrai com citação → Confira e envie).
- **Pós-extração**: card "Campos encontrados" com selo "confiança alta" e **tiles** (Tipo, Valor financiado, Valor da parcela, Taxa mensal em vermelho, Nº de parcelas, Taxa anual, CET anual). Ao lado, card "Confira antes de usar" com a **citação literal** do documento (cláusula/fonte/confiança) e botão "Enviar para Dívidas →".

### 5. Análise
- Barra de parâmetros: **Pagamento extra por mês (R$)**, **Taxa-alvo p/ portabilidade (% a.m.)**, botão "Analisar".
- **4 métricas**: Classificação, Fluxo de caixa, Saldo devedor, Comprometimento.
- **Estratégias de quitação** (avalanche vs. bola de neve) com meses, juros pagos, economia/1ª quitação, alvo de cada método — **recalculadas** conforme o extra.
- **Recomendações**: lista numerada priorizada (quitar a mais cara, direcionar a folga, reforçar reserva, avaliar portabilidade, evitar cheque especial).
- **Oportunidades de portabilidade** (`.card.panel`): para cada dívida acima da taxa-alvo, linha com parcela atual → nova, taxa atual → alvo, economia mensal e **economia total**; "Economia potencial total" em destaque. Estado vazio quando nenhuma dívida está acima do alvo.
- **Análise sênior (IA)** (`.aibox`): botão "Gerar análise sênior" com estado de loading (spinner ~1,5s) e depois 3 parágrafos gerados a partir dos números reais. Aviso "revise antes de agir".
- **Exportações**: botões "Gerar planilha (.xlsx)" e "Gerar relatório (.docx)".

### 6. Carta ao credor
- Formulário (coluna esquerda): **Dívida (credor)** select; **Tipo de proposta** como **cards selecionáveis** (Quitação à vista / Portabilidade / Redução de taxa), cada um com ícone + descrição; Nº do contrato (opcional); e **campos contextuais** que aparecem conforme o tipo — Valor à vista (quitação), Banco + Taxa concorrente (portabilidade), nota explicativa (renegociação). Botão "Gerar carta (.docx)".
- **Pré-visualização** (`.letter`): folha com cabeçalho (remetente/data), corpo formal que se **reescreve ao vivo** conforme credor e tipo, e linha de assinatura.

---

## Interactions & Behavior
- **Navegação**: clicar numa aba troca a tela (estado `screen`); a aba ativa recebe `.on`.
- **Cálculo reativo**: qualquer edição de renda/despesa/dívida/extra/taxa-alvo recalcula, na mesma renderização, totais, diagnóstico, estratégias, portabilidade e a narrativa da IA.
- **Dívidas CRUD**: adicionar (valida credor não-vazio), editar (move a dívida de volta ao formulário), remover.
- **IA**: botão dispara loading (~1500ms) e revela a análise; não recomeça se já estiver carregando.
- **Contrato**: os botões simulam a extração e revelam os campos + citação (mock; no app real, ler o PDF com o motor local).
- **Modo escuro**: botão de tema na topbar alterna claro/escuro; a preferência é **persistida** (localStorage `hf_dark`) e reidratada ao abrir. A classe `dark` é aplicada ao container `.app`.
- **Transições**: barras (alocação/participação) animam largura em 0.35s ease; hovers em 0.15s.

## State Management
Variáveis de estado necessárias:
- `screen`: aba atual (`geral|perfil|dividas|contrato|analise|carta`).
- `dark`: boolean (persistido em localStorage `hf_dark`).
- `perfil`: nome, cpf, e o mapa de campos de orçamento (salário, extra, outras; moradia, contas, transporte, saúde, educação, assinaturas, outras-fixas; mercado, lazer, vestuário, imprevistos, outras-variáveis; reserva, fgts). Guardados como string (input formatado) e parseados para número.
- `debts[]`: `{ credor, tipo, saldo, taxa (% a.m.), parcela, restantes }`.
- `novo`: rascunho do formulário de dívida; `editIdx` para modo edição.
- `extra` (pagamento extra), `alvo` (taxa-alvo de portabilidade).
- `carta`: `{ credor, tipo, contrato, valor, banco, taxa }`.
- `iaRun` / `iaLoading`, `contratoRun`: flags de UI.

Derivados (recalculados a cada render): renda/fixas/variáveis/despesas, parcelas totais, saldo devedor, juros futuros, fluxo de caixa, % comprometimento, classificação de saúde, ranking por taxa, taxa média ponderada, custo até quitar, simulações avalanche/bola de neve, oportunidades de portabilidade, parágrafos da narrativa.

## Regras de negócio (fonte: programa Python original — reproduzir fielmente)
- **Parse pt-BR**: remover pontos de milhar, vírgula → ponto decimal.
- **Fluxo de caixa** = renda − despesas − parcelas. **Comprometimento** = parcelas / renda.
- **Classificação de saúde** (por comprometimento): ≤ 30% = **Saudável** (`#0e9f6e`), ≤ 50% = **Atenção** (`#e8890c`), acima = **Crítico** (`#e03131`).
- **Cobertura da reserva** (meses) = reserva / despesas; ≥3 verde, ≥1 laranja, senão vermelho.
- **Faixa de cor por taxa a.m.**: ≥8% vermelho (`#fa5252`/fundo `#fff0ef`), ≥2,5% laranja (`#e8890c`/`#fff4e6`), senão verde (`#12b886`/`#eafaf1`).
- **Simulação de quitação (mês a mês)**, para avalanche (maior taxa primeiro) e bola de neve (menor saldo primeiro): a cada mês, aplica juros ao saldo (saldo += saldo×taxa, acumula juros), paga as parcelas mínimas, e distribui o orçamento livre (soma das parcelas das dívidas quitadas + extra) na ordem do método até zerar. Retorna meses até quitar, juros totais, mês da 1ª quitação, e trata o caso **"não quita"** (parcela mínima < juros → nunca amortiza; exibir "não quita" em vez de número estourado; usar teto de meses de segurança). **Taxa média** exibida é **ponderada pelo saldo**.
- **Portabilidade** (sistema Price): para cada dívida com taxa acima da taxa-alvo, nova parcela = PMT(saldo, taxaAlvo, nRestantes) usando fórmula Price numericamente estável (`i/(1−(1+i)^−n)`, com `expm1/log1p`). Economia mensal = parcelaAtual − parcelaNova; economia total = economiaMensal × n. Ordenar por maior economia total; somar para o total.
- **Narrativa da IA**: texto **determinístico** montado a partir dos números reais (diagnóstico + dívida mais cara; caminho pela avalanche com meses/economia, ou alerta de "gerar sobra primeiro" se fluxo ≤ 0; alavancas condicionais: portabilidade, reserva, FGTS). Filosofia do projeto: o determinístico manda nos números, a IA só interpreta.

## Design Tokens

### Cores — claro
- Fundo externo `#d9d4c9`; app `#f4f1ea`; superfícies/cards `#fff`; texto base `#2a2435`; texto suave `#6f687b`; muted `#8a8394`; muted claro `#a59db0`.
- Bordas: `#ece7dd` (cards), `#e2dccf` (inputs), `#f1ece3` (divisórias), tracejado `#e6e0d5`.
- Input fundo `#fbfaf6`; foco borda `#8a7cf0`, sombra `0 0 0 3px rgba(106,91,240,.15)`.
- **Marca/primária**: violeta `#5343e0` (hover `#4535d6`), acento `#6a5bf0`, gradiente marca `#6a5bf0→#4a38d8`; superfícies violeta `#efecfe`/`#f4f1fb`.
- **Semânticas**: verde `#12b886` (e `#0e9f6e`), laranja `#e8890c`, vermelho `#fa5252` (e `#e03131`). Fundos tint: verde `#eafaf1`/`#e7f8f0`, laranja `#fff4e6`, vermelho `#fff0ef`/`#ffecec`.
- Avatar gradiente `#ff9a76→#ff7a59`.

### Cores — escuro (aplicadas sob `.app.dark`)
- App `#15131e`; topbar `#1c1929`; cards/superfícies `#201c2e`; inputs `#191622`; bordas `#2c2642`/`#2a2540`/`#332c48`.
- Texto forte `#f2eff8`; corpo `#c3bdd0`; muted `#948da5`.
- Nav ativo `#2c2547`/`#c3b8fb`; hover `#241f36`. Trilhas de barra `#2a2540`.
- aibox `linear-gradient(135deg,#221c38,#2a1d34)`; scard.win `linear-gradient(135deg,#16281f,#182c24)` borda `#255140`; scard.alt `#231d3a`.
- As cores semânticas (verde/laranja/vermelho/violeta) permanecem as mesmas para preservar o diagnóstico.

### Tipografia
- Família: **Plus Jakarta Sans** (pesos 400/500/600/700/800), fallback `system-ui, sans-serif`.
- H1 22px/800 (-.5px); título de card 16px/800 (-.3px); rótulo hero 32px/800 (-.6px); métricas 20–23px/800; corpo 13px; meta/labels 11–12.5px. Números com `font-variant-numeric: tabular-nums`.

### Radius
- Janela 16; cards 18–20; tiles/inputs 11–14; chips/ícones 9–12; pills/tags 999; selo 7.

### Sombras
- Card: `0 10px 26px -20px rgba(90,70,20,.25)`. Janela: `0 30px 80px -30px rgba(60,45,20,.45)`. Hover card dívida: `0 8px 20px -14px rgba(90,70,20,.3)`.

### Espaçamento & grids
- Conteúdo `padding:24px 30px 30px`; gaps de card 14–16px. Grids: métricas `repeat(4,1fr)`; colunas de conteúdo `1.12fr 1fr` (dashboard) / `1.25fr 1fr` (dívidas) / `1fr 1fr`; perfil 2×2; resumo `repeat(3,1fr)`.

### Ícones
- Ícones de linha (stroke 1.8–2, sem preenchimento), estilo consistente com Lucide/Feather. Substituir pelos ícones do design system do codebase. Sem emoji além do 👋 da saudação (opcional).

## Assets
Nenhum bitmap. Ícones são SVGs inline (linha). Fonte via Google Fonts (Plus Jakarta Sans). Nenhum logo externo — a marca é o quadrado com cifrão desenhado em SVG. Se o codebase já tem sistema de marca/ícones, use o dele.

## Files
- `Helper Financeiro App.dc.html` — protótipo hi-fi completo das 6 telas + modo escuro (referência de layout, tokens e comportamento). Abra num navegador para inspecionar interações. O código-fonte da lógica de negócio original (Python) deve ser tratado como fonte de verdade dos cálculos.
- `screenshots/` — capturas de referência de cada tela (1280px):
  - `01-visao-geral.png`, `02-perfil.png`, `03-dividas.png`, `04-contrato-pdf.png`, `05-analise.png`, `06-carta-ao-credor.png`, `07-modo-escuro.png`.
