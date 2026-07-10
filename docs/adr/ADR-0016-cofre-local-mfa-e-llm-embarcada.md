# ADR-0016 — Cofre local (login + MFA + criptografia em repouso) e LLM embarcada autogerida

- **Status:** Aceita (2026-07-10)
- **Contexto de processo:** primeira mudança pós-freeze v2.7.0. Esta ADR é a
  autorização formal exigida pela ata: abre o ciclo **v2.8.0** (milestones
  **M16** e **M17**); nova ata será lavrada no fechamento. Escopo decidido pelo
  mantenedor: transformar o app num **cofre** — login com senha mestra + MFA
  (TOTP) e dados **cifrados em repouso** (M16) — e eliminar a dependência de
  ferramenta de terceiros (Ollama/LM Studio) para a LLM local, com **runtime
  embarcado gerido pelo próprio programa** (M17). Code signing segue adiado
  (depende de certificado do mantenedor).

## Contexto

Desde o v2.4 o estado do usuário (perfil, dívidas, rubricas, histórico) vive em
`%APPDATA%\HelperFinanceiro\dados.db` — um SQLite **em claro**: qualquer pessoa
com acesso ao disco (notebook roubado, backup exposto, outra conta na máquina)
lê tudo. A única autenticação existente é o token de sessão do sidecar
(REQ-SEC-004), que protege a fronteira HTTP local, não os dados em repouso, e
não pergunta *quem* está usando o app.

Na frente da LLM, o provider é agnóstico (ADR-0002/0010), mas todo caminho
local depende de um **servidor de terceiros** que o usuário instala e opera à
parte (Ollama ou LM Studio na porta 1234). Para o usuário final do instalador,
"funcionar de fábrica" hoje significa modo degradado (P8): sem Ollama, sem IA.

Decisões do mantenedor (brainstorm do planejamento, 2026-07-10):

- **Runtime:** **llama.cpp embarcado** (`llama-server`) gerido pelo sidecar —
  iniciar, parar, carregar modelo GGUF. É OpenAI-compatible: o
  `OpenAICompatProvider` atual funciona contra ele **sem mudança de contrato**.
- **Modelo:** **download gerenciado no 1º uso** — catálogo curado com URL fixa
  e **SHA-256 travado**; o instalador não incha (~2 GB de pesos ficam fora).
  Apontar um `.gguf` local já existente também é aceito.
- **Cofre:** **SQLCipher (AES-256) + Argon2id** — o banco inteiro é cifrado;
  a chave deriva da senha mestra do usuário.
- **MFA:** **TOTP + códigos de recuperação** — 100% offline (app autenticador),
  sem serviço de terceiros, coerente com H2/H7.

## Decisão

### A. Modelo de chaves do cofre (M16)

Envelope clássico **DEK/KEK**, todo em `sidecar/auth.py`:

- Uma **DEK** (data encryption key, 32 bytes aleatórios de `secrets`) cifra o
  banco — é ela que vai no `PRAGMA key` do SQLCipher.
- A **KEK** deriva da senha mestra via **Argon2id** (`argon2-cffi`, parâmetros
  registrados nos metadados para permitir recalibrar no futuro). A DEK é
  guardada **envelopada** pela KEK (AES-GCM, lib `cryptography`).
- Cada **código de recuperação** (10, de uso único, exibidos apenas no
  cadastro) também envelopa uma cópia da DEK; o código em si é guardado só
  como hash. Perder a senha **não** perde os dados enquanto restar um código;
  perder senha **e** códigos perde os dados — **não há backdoor**, por design.
- Os metadados de autenticação (sal e parâmetros do Argon2id, DEK envelopada,
  hashes dos códigos, segredo TOTP **cifrado pela DEK**, contador de
  tentativas) vivem num arquivo próprio fora do cofre
  (`%APPDATA%\HelperFinanceiro\auth.json`) — nada ali é utilizável sem a senha.

**Honestidade do modelo de ameaça:** a *cifra* deriva da senha; o TOTP protege
a *autenticação* (uso do app), não adiciona entropia à chave. O cofre protege
contra acesso ao **disco** (roubo, backup, outra conta); malware rodando na
sessão do usuário com o cofre aberto está fora do escopo — como em qualquer
gerenciador de senhas desktop.

### B. Banco cifrado com migração (M16)

`sidecar/persistencia.py` passa a abrir o banco via **SQLCipher**
(`sqlcipher3`), com a DEK aplicada por `PRAGMA key` antes de qualquer consulta.
No primeiro desbloqueio pós-atualização, se existir um `dados.db` em claro, a
migração é automática: `ATTACH` + `sqlcipher_export()` para o cofre novo,
verificação de integridade e remoção do arquivo em claro. O schema lógico não
muda (`VERSAO_ESQUEMA` permanece 1) — muda o **contêiner**.

### C. Sessão de cofre no sidecar (M16)

O token por execução (REQ-SEC-004) continua — ele autentica o *processo*
Electron. A novidade é o estado **bloqueado/desbloqueado**: endpoints de
negócio respondem `423 Locked` até o login (senha + TOTP) abrir o cofre.
Anti-brute-force com atraso exponencial persistido nos metadados;
**auto-lock** por inatividade (configurável) e bloqueio manual na GUI.
A DEK vive **apenas em memória** do sidecar enquanto o cofre está aberto
(mesmo racional do mapa de anonimização, REQ-SEC-003).

### D. Onboarding e login na GUI (M16)

Primeiro uso (ou primeira execução pós-atualização com dados em claro):
assistente de cadastro — senha mestra (política mínima verificada no sidecar),
QR code do TOTP (`pyotp` + `qrcode`, renderizado localmente) conferido com um
código válido, e os 10 códigos de recuperação para o usuário guardar. Depois:
tela de desbloqueio (senha + TOTP) antes de qualquer tela de negócio, e fluxo
"esqueci a senha" via código de recuperação (que redefine a senha reenvelopando
a DEK — os dados não são recifrados).

### E. Runtime LLM embarcado (M17)

`sidecar/runtime_llm.py` gerencia um **`llama-server`** (llama.cpp, binário
empacotado como *extraResource*, build CPU + GPU Vulkan — cobre a GPU-alvo de
4 GB sem exigir CUDA): inicia sob demanda em **loopback + porta efêmera**
(mesma disciplina do próprio sidecar), espera o health, encerra no shutdown.
O `OpenAICompatProvider` existente aponta para ele (endpoint local ⇒ H2
preservado por construção; `response_format` json_schema vira gramática GBNF
no servidor — structured output por construção, ADR-0005). **ADR-0002
preservada:** Ollama/LM Studio/nuvem continuam configuráveis; o embarcado é o
**padrão de fábrica**, não o único caminho. Sem modelo instalado, o fluxo
degrada como hoje (P8), com motivo claro na GUI ("instale um modelo em
Configurações").

### F. Gestão de modelo pelo app (M17)

Tela de configuração da IA: **catálogo curado** (modelos GGUF com licença
comercial ok — ex.: Qwen3-4B-Instruct Q4_K_M, Apache-2.0 — com URL fixa e
SHA-256 **travados no código**), download com barra de progresso, retomada e
**verificação de hash obrigatória** antes de ativar; alternativa 100% offline:
apontar um `.gguf` já existente no disco. Pesos ficam em
`%APPDATA%\HelperFinanceiro\modelos\`. O download é a **única exceção
controlada** ao zero-rede: só por ação explícita do usuário, só das URLs do
catálogo, hash conferido — nunca em background, nunca telemetria.

## Alternativas rejeitadas

- **Empacotar o Ollama**: ~1 GB de terceiro rodando invisível, ciclo de
  atualização/licença sob nossa responsabilidade e um serviço a mais para
  auditar. O llama.cpp dá o mesmo resultado com um binário pequeno e
  OpenAI-compat nativo.
- **ONNX Runtime GenAI** (reusar o onnxruntime do OCR): acervo de modelos ONNX
  é ordens de magnitude menor que GGUF, API não é OpenAI-compat (quebraria o
  provider) e o structured output por gramática é mais fraco.
- **Modelo embarcado no instalador**: 330 MB → ~2,5 GB e trocar de modelo
  exigiria novo instalador. Os modelos de OCR (~132 MB) justificaram embarcar;
  ~2 GB de pesos, não.
- **Criptografia em nível de aplicação** (cifrar campo a campo no SQLite puro):
  metadados (estrutura, contagens, datas de atualização) ficariam visíveis e é
  fácil esquecer um campo novo. SQLCipher cifra o contêiner inteiro.
- **Windows Hello / DPAPI como única proteção**: amarra a chave à conta local
  do Windows (backup restaurado em outra máquina perde tudo), não funciona
  como *fator* auditável e complica o empacotamento (WinRT). Pode voltar num
  ciclo futuro como *conveniência* de desbloqueio, nunca como base.
- **MFA por e-mail/SMS/push**: exige serviço de terceiros e rede — viola H2/H7.
  TOTP é offline por construção.
- **"Recuperação pelo suporte"/backdoor de chave**: um cofre com chave mestra
  de terceiro não é cofre. Perda de senha + códigos ⇒ perda dos dados, e isso
  é dito ao usuário no cadastro.

## Consequências

- **Dependências novas** (entram no `PLAN §Stack` com as tasks que as usam):
  `argon2-cffi` (KDF), `cryptography` (AES-GCM do envelope), `sqlcipher3`
  (banco cifrado), `pyotp` + `qrcode` (TOTP) — M16; binário `llama-server`
  (llama.cpp, ~poucos MB + variantes) empacotado como *extraResource* — M17.
- **Empacotamento** volta a ser o risco real: `sqlcipher3` traz binário nativo
  (PyInstaller: `collect_all`/hook, smoke que abre cofre de verdade) e o
  `llama-server` precisa viajar no instalador com os builds CPU/Vulkan
  (smoke que gera análise de verdade com o runtime embarcado).
- **Migração sensível**: o primeiro desbloqueio converte `dados.db` em claro
  para o cofre. Falha no meio não pode corromper: exporta para arquivo novo,
  verifica, só então remove o antigo.
- **UX muda**: o app deixa de abrir direto — há login. O auto-lock é
  configurável para não punir o uso doméstico.
- **Constituição permanece 2.0.0**: nenhum princípio muda. Números seguem do
  determinístico (P1); degradação segue P8; H2/H7 saem **fortalecidos** (o
  caminho local deixa de depender de servidor externo); REQ-SEC-001/003
  ganham a extensão natural (dados em repouso cifrados; DEK só em memória).
- Sem migração de schema lógico (`VERSAO_ESQUEMA` permanece 1); o contêiner
  do banco muda para SQLCipher.

## Requisitos derivados

`REQ-SEC-005` (login senha mestra + TOTP, sessão bloqueada/desbloqueada,
anti-brute-force, auto-lock), `REQ-SEC-006` (criptografia em repouso:
SQLCipher AES-256, Argon2id, envelope DEK/KEK) e `REQ-SEC-007` (códigos de
recuperação de uso único; sem backdoor) no `SPEC.md` §4; `REQ-F-027` (runtime
LLM embarcado gerido pelo app) e `REQ-F-028` (gestão de modelo: catálogo com
hash travado, download opt-in, GGUF local) no §1; `REQ-NF-007` (download de
modelo como única exceção de rede, opt-in e verificada; runtime só em
loopback) no §5. Harness em `tests/test_auth.py` (envelope, TOTP, códigos,
anti-brute-force), `tests/test_persistencia.py` (cofre + migração),
`tests/test_sidecar.py` (contrato 423/login/lock) e `tests/test_runtime_llm.py`
(gerência de processo, catálogo, verificação de hash); E2E em `gui_web/e2e/`.
