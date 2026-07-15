# ADR-0021 — Ciclo v2.13: code signing (C-15) em duas fases — cert de teste + SignPath

- **Status:** Aceita (design validado em brainstorming com o mantenedor) ·
  **Data:** 2026-07-15
- **Relacionada a:** achado **C-15** da auditoria v2.9 (code signing pendente
  desde o v2.3 — SmartScreen alerta; auto-update de produção exige assinatura;
  instalação real do update não testável, registrado nas atas v2.10..v2.12);
  regras herdadas: ADR-0017 §E (zero regressão), ADR-0018 §5 (auditoria de
  deps), ADR-0020 hotfix (CI remoto verde antes de congelar)
- **Ciclo:** v2.13.0 · **Milestone:** M24 (T-2401..T-2405)

## Contexto

C-15 é o último achado aberto da auditoria v2.9. O mantenedor **inscreveu o
projeto no SignPath.org** (SignPath Foundation — code signing gratuito para
OSS), aprovação pendente. O modelo do SignPath dita a arquitetura: a chave
privada **nunca sai da plataforma** deles; o certificado é emitido à
**"SignPath Foundation"** (é ela o publisher, não o projeto); o artefato
precisa nascer de **build verificável em CI**; cada release exige aprovação
manual de um Approver (o mantenedor); o projeto precisa de **licença
OSI-approved** (o repo é público mas NÃO tinha licença — bloqueador) e de
uma política de assinatura publicada no README. Enquanto a aprovação não
sai, um **certificado de teste gerado no PowerShell**
(`New-SelfSignedCertificate -Type CodeSigningCert`) destrava toda a parte
reprodutível: pipeline de assinatura, verificação do electron-updater e o
degrau final do smoke de auto-update (instalação real), que ficou de fora do
v2.12 por falta de assinatura.

## Decisão

### M24 — Code signing em duas fases (tasks por entregável)

- **T-2401 (elegibilidade SignPath, orquestrador):** `LICENSE` **MIT**
  (decisão do mantenedor; titular = mantenedor) + seção "Política de
  assinatura de código" no README com a atribuição exigida ("Free code
  signing provided by SignPath.io, certificate by SignPath Foundation"),
  papéis da equipe e privacidade. Só docs/metadados.
- **T-2402 (pipeline de assinatura local, Opus):**
  - `scripts/preparar_cert_teste.ps1`: gera o cert
    (`New-SelfSignedCertificate -Type CodeSigningCert`, validade **30
    dias**), exporta PFX **fora do repo**, imprime instruções de uso,
    confiança e remoção (por thumbprint). `.gitignore` ganha `*.pfx`.
  - `scripts/build_assinado.ps1`: embrulha o `npm run dist` com overrides
    `-c.win.signtoolOptions.*` (certificateFile/certificatePassword/
    publisherName) lidos de envs `HF_CSC_*`; assina o `sidecar-hf.exe` com
    `signtool` ANTES do empacotamento. **Sem as envs, o build permanece
    byte-idêntico ao atual** (config inerte — zero impacto no dia a dia).
  - Aceite: `Get-AuthenticodeSignature` = `Valid` (com o cert confiado) no
    instalador E no sidecar embarcado.
- **T-2403 (degrau final do smoke de auto-update, Sonnet):** estende
  `e2e/empacotado-update.spec.ts`:
  - O feed passa a servir um **instalador NSIS real re-versionado**
    (`-c.extraMetadata.version=99.0.0`) e assinado — exigência da
    verificação do updater (`publisherName`).
  - **Confiança do cert é portão manual do mantenedor:** o teste NUNCA
    importa o cert sozinho; verifica `CurrentUser\Root` + `TrustedPublisher`
    e, ausente, PULA com a instrução impressa.
  - **Instalação real** gated por DUAS envs (`HF_E2E_PACOTE=1` +
    `HF_E2E_UPDATE_INSTALL=1`): `quitAndInstall` → assevera 99.0.0
    instalado. Salvaguardas: **aborta se o Helper Financeiro real estiver
    instalado na máquina**; cleanup obrigatório no `finally` (uninstall
    silencioso `/S` + verificação de remoção).
  - **Verificação negativa:** update assinado com OUTRO cert (ou sem
    assinatura) é recusado pelo updater — prova que a verificação morde.
- **T-2404 (workflow de release, Sonnet):** `.github/workflows/release.yml`
  disparado por tag `v*`, runner `windows-latest` (PyInstaller/NSIS):
  preparadores → PyInstaller → `npm run dist` → artefatos anexados como
  **draft** de GitHub Release (nada publica sozinho). Submissão ao SignPath
  atrás de secret-flag **`SIGNPATH_ATIVO`** (desligado até a aprovação):
  ligado, usa `signpath/github-action-submit-signing-request` e espera a
  aprovação manual do mantenedor na plataforma. **Escada do sidecar
  embarcado:** degrau 1 = assinatura profunda do NSIS (SignPath assina os
  aninhados numa submissão); degrau 2 (se a policy não cobrir) = dois
  estágios (submete o sidecar → rebuild do instalador com o exe assinado →
  submete o instalador). Segredos só em GitHub Secrets
  (`SIGNPATH_API_TOKEN`, slugs de org/projeto/policy).
- **T-2405 (fechamento, orquestrador):** gates locais + **CI remoto verde**
  + auditoria de deps + ensaio do `release.yml` (tag `v2.13.0-rc`, flag
  desligada) + ata `FREEZE.md` v2.13.0 **sem rebuild oficial** — a
  assinatura de teste não vai a público (publisher fake não melhora nada
  para o usuário) e sem envs a config é inerte; binários públicos seguem os
  do build 2.12.0, registrado na ata.

### publisherName por fase

Fase 1 (teste): subject do cert de teste (ex.: `CN=Helper Financeiro
(Teste)`). Fase 2 (produção): **"SignPath Foundation"** — documentado no
README/política para não confundir usuários.

### Critérios de fechamento

Gates verdes; CI remoto verde; smoke do auto-update completo (assinatura
verificada + instalação real + verificação negativa) verde com o cert de
teste; ensaio do release.yml concluído; ata v2.13.0.

### Ativação da fase 2 (fora deste ciclo, quando a aprovação sair)

Ligar `SIGNPATH_ATIVO` + secrets reais + `publisherName` de produção e rodar
uma release por tag — se nada além disso for preciso, é hotfix/patch com
registro em ata, não ciclo novo.

## Riscos aceitos

| Risco | Mitigação |
|---|---|
| Instalação de teste tocar a máquina real | trava "aborta se instalado" + uninstall no `finally` + duplo gating de env |
| Cert de teste confiado esquecido no host | validade 30 dias + remoção por thumbprint documentada + registro na ata |
| Inscrição do SignPath recusada/atrasada | fase 1 e o workflow desativado independem dela; plano B: Azure Trusted Signing (electron-builder 26 suporta `win.azureSignOptions`) |
| Publisher "SignPath Foundation" confundir usuários | política de assinatura no README explica o modelo |
| Workflow de release nunca ensaiado | ensaio com tag `v2.13.0-rc` e flag desligada é critério de aceite |

## Alternativas rejeitadas (Decision Log do brainstorming)

- **Apache-2.0 / GPL-3.0:** o mantenedor escolheu **MIT** (permissiva,
  fricção mínima na aprovação OSS).
- **Migrar TODOS os builds para CI:** o SignPath só exige CI para o
  artefato assinado; builds locais continuam para dev/smokes (**híbrido**) —
  o smoke do órfão precisa do exe local de qualquer forma.
- **Parar na verificação de assinatura (sem instalação real):** o mantenedor
  escolheu ir **até a instalação real** — é o único degrau que nunca foi
  testado e a fase 1 existe exatamente para isso.
- **Esperar a aprovação do SignPath antes de qualquer coisa:** desperdiça a
  janela; tudo da fase 1 independe deles.
- **Teste importar o cert na máquina automaticamente:** mexer no Trusted
  Root é mudança de segurança do host — SEMPRE portão manual do mantenedor.
- **Publicar build oficial assinado com o cert de teste:** publisher fake
  não melhora nada para usuários e suja a ata — binários públicos só voltam
  a mudar com assinatura real (ou ciclo próprio).
- **Dois milestones (fase 1 / fase 2):** as fases compartilham config,
  publisherName e smoke — separar duplicaria contexto (YAGNI de processo).
