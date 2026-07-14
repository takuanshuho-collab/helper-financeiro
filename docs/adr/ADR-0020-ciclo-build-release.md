# ADR-0020 — Ciclo v2.12: build/release com bumps dirigidos e smoke do auto-update

- **Status:** Aceita (design validado em brainstorming com o mantenedor) ·
  **Data:** 2026-07-14
- **Relacionada a:** risco aceito da ata v2.11.0 (`setuptools` 82.0.1,
  PYSEC-2026-3447) e riscos residuais registrados nas atas v2.10.0/v2.11.0
  (electron-updater 6.8 verificado só por changelog; flake candidato do
  `cofre.spec.ts`); regras herdadas da ADR-0017 §E (zero regressão; §E.4:
  bump de dependência ⇒ smoke do pacote repetido) e ADR-0018 §5 (auditoria
  de deps no fechamento)
- **Ciclo:** v2.12.0 · **Milestone:** M23 (T-2301..T-2304)

## Contexto

Os binários publicados são os da ata v2.10.0 e **não contêm o código v2.11**
(endurecimento POSIX dormente e refatorações sob golden-master) — a ata
v2.11.0 registrou isso explicitamente, junto com o risco aceito do
`setuptools` vulnerável na árvore de build (transitiva do PyInstaller; fix
83.0.0 agendado "para o próximo ciclo que reconstruir binários"). Este é
esse ciclo. De carona, dois riscos residuais de harness: o auto-update nunca
foi testado de fato contra o Electron 43, e o cenário E2E "recuperação por
código de uso único" falhou 1× no fechamento do v2.11 (não reproduziu; flake
candidato).

## Decisão

### M23 — Build/release (sequência rígida)

- **T-2301 (bumps dirigidos, Sonnet):** `setuptools` → 83.0.0
  (`uv lock --upgrade-package`, fecha PYSEC-2026-3447), Electron → **43.1.1**
  (patch dentro do range), `langgraph` → 1.2.9 e `uvicorn` → 0.51
  (patches/minors de runtime). **Nenhum major** (React 19, TS 7, undici 8
  ficam intocados — §E). Aceite: gates completos + E2E dev completo sobre o
  Electron novo.
- **T-2302 (caronas de harness, Sonnet):**
  1. **Smoke do auto-update** — `e2e/empacotado-update.spec.ts` (gated por
     `HF_E2E_PACOTE=1`): servidor local servindo `latest.yml` (versão
     fictícia maior + `sha512`) e instalador-isca; app empacotado lançado
     com `HF_AUTO_UPDATE=1` + `HF_UPDATE_URL` no feed; asserção em escada —
     mínimo `update-available`, ideal `update-downloaded` (a instalação fica
     fora: sem code signing o Windows recusa a troca — limitação do T-1002,
     não do teste). **Escada do HTTPS** (o `HF_UPDATE_URL` exige HTTPS):
     degrau 1 = HTTPS local com cert self-signed e CA injetada só no
     processo do teste (`NODE_EXTRA_CA_CERTS`), zero mudança de produção;
     degrau 2 (fallback documentado) = aceitar `http://` **exclusivamente
     para 127.0.0.1** na validação do `main.ts` — precedente da invariante
     H2 (exceção por endpoint loopback, imune a MITM fora do host).
  2. **Blindagem do flake do cofre** — investigar a corrida real do
     `.auth-overlay` (5 s) e aplicar o padrão T-1907 (asserção da condição
     intermediária real; PROIBIDO timeout maior). Aceite: `cofre.spec.ts`
     completo, rodadas limpas repetidas.
- **T-2303 (build oficial + smokes, orquestrador):**
  `preparar_llama.py` E `preparar_ocr.py` → PyInstaller (`SidecarHF.spec`)
  → versão do `gui_web/package.json` conferida (lição v2.5) → `npm run
  dist`. Bateria contra o pacote real: smoke NSIS (`empacotado.spec.ts` +
  `empacotado-llm.spec.ts`), smoke do órfão (kill duro com GGUF real,
  ambiente isolado incl. `HF_LLM_CONFIG_PATH` — lição v2.9) e o smoke do
  auto-update novo contra o instalador recém-buildado (§E.4 satisfeito).
- **T-2304 (fechamento, orquestrador):** auditoria ADR-0018 §5 com critério
  endurecido — **pip-audit tem que zerar** (se não zerar, o bump do
  setuptools falhou); ata `FREEZE.md` v2.12.0 com os hashes dos binários
  NOVOS (primeira ata desde a v2.10.0 com binário contendo o código
  corrente), registrando o fim do risco aceito e o desfecho dos dois riscos
  residuais; docs sincronizados.

### Critérios de fechamento

Gates verdes; E2E dev completo verde; os **3 smokes do pacote** verdes
(NSIS, órfão, auto-update); `pip-audit` = **0**; `npm audit` = 0; Electron
na janela de suporte; ata v2.12.0.

### Fora do ciclo

**C-15 (code signing)** — segue aguardando a decisão de custo do certificado
(OV/EV ou Azure Trusted Signing); quando decidido, ganha ciclo próprio (e
destrava a instalação real no smoke do auto-update).

## Riscos aceitos

| Risco | Mitigação |
|---|---|
| Patch do Electron (43.1.1) esconder surpresa | patch dentro do range; E2E dev completo no T-2301 antes de qualquer build |
| `langgraph` 1.2.9 mudar comportamento do grafo | suíte cobre os nós; regressão P8 aparece no Gate A |
| Smoke do auto-update parar no degrau 1 (CA ignorada pelo stack do updater) | degrau 2 aprovado e cercado (loopback-only) |
| Updater exigir assinatura para `update-downloaded` | régua mínima `update-available` já fecha o risco documental |
| Flake do cofre não reproduzir para diagnóstico | T-1907 aplica-se pela leitura da corrida, não exige reprodução |

## Alternativas rejeitadas (Decision Log do brainstorming)

- **Escopo de deps "mínimo absoluto" (só setuptools) ou com majors:** o
  mantenedor escolheu o meio-termo — patches/minors dirigidos de runtime;
  majors continuam proibidos pelo §E.
- **Code signing neste ciclo:** adiado — decisão de custo pendente; o ciclo
  de release não depende dele.
- **Dois milestones (deps+harness / release):** cerimônia sem ganho — as
  tasks já são sequenciais e o ciclo é curto (YAGNI de processo).
- **Build antes das caronas:** obrigaria segundo build para o smoke do §E.4
  validar o estado final. Descartada.
- **Relaxar o HTTPS do `HF_UPDATE_URL` direto (sem tentar a CA de teste):**
  mudança de produção em validação de segurança só como fallback provado
  necessário — por isso a escada 1→2, não o degrau 2 direto.
- **Testar a instalação real do update:** impossível sem assinatura
  (Windows recusa); a régua para em `update-downloaded` por decisão, com o
  degrau final destravado pelo futuro C-15.
