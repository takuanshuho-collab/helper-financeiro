# Paridade funcional — GUI tkinter (`gui/`) ↔ GUI web (`gui_web/`)

> Checklist do T-905 (M9, ciclo v2.3 / ADR-0009). A GUI web é a candidata a
> entrypoint no M10 (T-1004); este documento prova que nada do tkinter se
> perdeu na migração. Cobertura automatizada: **E2E Playwright**
> (`gui_web/e2e/app.spec.ts`, roda o Electron + sidecar REAIS — portão local,
> `npm run e2e`) + testes de contrato do sidecar (`tests/test_sidecar.py`).
>
> **Atualização v2.4 (ADR-0012):** o ciclo v2.4 adicionou recursos **só na
> GUI web** — ver §7. A tkinter permanece como fallback congelado do v2.3,
> sem rubricas e sem persistência (decisão consciente: nenhum recurso novo
> no fallback).

Legenda: ✅ paridade plena · ✨ web supera o tkinter · Δ mudou de lugar (sem perda).

## 1. Perfil / orçamento (REQ-F-012)

| Recurso no tkinter | Na GUI web | Status | Coberto por |
|---|---|---|---|
| Renda em 3 campos (salário, extra, outras) | Tela Perfil, seção "Renda líquida mensal" | ✅ | E2E "perfil" |
| Despesas fixas (7 categorias) e variáveis (5) | Seções com subtotais do core ao vivo | ✅ | E2E "perfil" + `test_diagnostico_roundtrip` |
| Reserva de emergência + FGTS | Tela Perfil (cobertura em meses do core) | ✅ | `test_meses_reserva_nulo_sem_despesas` |
| Resumo do orçamento (texto) | Barra de alocação animada + barra-resumo | ✨ | E2E "perfil" |
| Nome / CPF do usuário | Movidos para a tela **Carta** (assinatura) | Δ | E2E "carta" |

## 2. Dívidas (REQ-F-013)

| Recurso no tkinter | Na GUI web | Status | Coberto por |
|---|---|---|---|
| Lista (Treeview) das dívidas | Cards editáveis **inline** | ✨ | E2E "dívidas" |
| Adicionar / editar (diálogo) / remover | Adicionar/remover + edição direta no card | ✅ | E2E "dívidas" |
| Estatísticas (saldo, parcelas, taxa média ponderada, custo até quitar) | Faixa de stats, tudo do core | ✅ | E2E "dívidas" + `test_diagnostico_roundtrip` |
| Sinalização da dívida mais cara | Selo "Mais cara" | ✅ | E2E "visão geral" |

## 3. Contrato PDF (REQ-F-014)

| Recurso no tkinter | Na GUI web | Status | Coberto por |
|---|---|---|---|
| Escolher PDF (file dialog) | Drop-zone (arrastar ou clicar) | ✨ | `test_contrato_extrair_ia_com_citacao_e_confirma` |
| Extração clássica (regex) | Fallback automático com diagnóstico do motivo | ✅ | `test_contrato_extrair_fallback_classico` |
| Extração IA local + diálogo de confirmação (interrupt→resume) | Painel de revisão com citação por campo | ✅ | `test_contrato_extrair_ia_com_citacao_e_confirma` |
| Aviso de PDF sem texto (escaneado) | Mensagem equivalente | ✅ | `test_contrato_pdf_sem_texto` |
| — | Fusão determinística clássico+IA (ADR-0010) | ✨ | `test_fusao_classica_completa_campos_da_ia` |

*Nota:* o fluxo com a LLM real fica fora do E2E (depende do LM Studio);
é validado manualmente com `scripts/diag_llm.py` (T-901).

## 4. Análise (REQ-F-015)

| Recurso no tkinter | Na GUI web | Status | Coberto por |
|---|---|---|---|
| Parâmetros: extra mensal + taxa-alvo | Mesmos campos, com **recálculo ao vivo** (sem botão) | ✨ | E2E "análise" |
| Texto: diagnóstico + estratégias + recomendações | Métricas + cards Avalanche/Bola de neve + recomendações numeradas | ✨ | E2E "análise" + `test_analise_pacote_deterministico` |
| — (portabilidade só nos exports) | Seção "Oportunidades de portabilidade" na tela | ✨ | E2E "análise" |
| IA sênior em thread (janela não congela) | **Job assíncrono** no sidecar + poll | ✅ | E2E "análise" (degradada) + `test_analise_ia_job_completo_e_anonimizacao_da_fronteira` |
| Indicador de modo degradado (P8) | Aviso com os motivos | ✅ | E2E "análise" + `test_analise_ia_provider_falho_degrada_sem_500` |
| Exportar .xlsx / .docx (com a última análise da IA) | Idem, via diálogo nativo (`hf:dialogo-salvar`) | ✅ | `test_exportar_planilha_e_relatorio` |

## 5. Carta ao credor (REQ-F-016)

| Recurso no tkinter | Na GUI web | Status | Coberto por |
|---|---|---|---|
| Seleção da dívida + tipo (combobox) | Select + cards de tipo | ✅ | E2E "carta" |
| Campos: contrato, valor à vista, banco, taxa | Mesmos campos, **contextuais por tipo** | ✨ | E2E "carta" |
| — (gerava direto o .docx, às cegas) | **Pré-visualização ao vivo** = texto exato do .docx | ✨ | E2E "carta" + `test_carta_previa_quitacao_cita_valor_proposto` |
| Gerar .docx | Idem, via diálogo nativo | ✅ | `test_exportar_carta_docx` |

## 6. Geral

| Recurso no tkinter | Na GUI web | Status | Coberto por |
|---|---|---|---|
| Validação numérica visual dos campos | Campos tipados (CampoMoeda/CampoPercent) que interpretam pt-BR | ✅ | E2E "perfil" |
| — | Tela **Visão geral** (hero + anel + métricas) | ✨ | E2E "visão geral" |
| — | **Modo escuro** persistido (`hf_dark`) + segue o SO | ✨ | E2E "tema" |
| Segurança: cálculo 100% no core Python | Sidecar loopback+token; zero aritmética em TS (REQ-NF-005) | ✅ | `tests/test_sidecar.py` (contrato completo) |

## 7. Novidades do ciclo v2.4 (ADR-0012) — só na GUI web

| Recurso | Onde | Status | Coberto por |
|---|---|---|---|
| Persistência local (perfil + dívidas + rubricas em SQLite; hidratação + auto-save) | Sidecar (`/estado`) + `App.tsx` | ✨ | E2E "persistência" + `tests/test_persistencia.py` + `test_estado_*` |
| Rubricas por campo do orçamento (roll-up no core; campo detalhado somente-leitura com selo) | Planilha de orçamento (sub-tela do Perfil) | ✨ | E2E "planilha" + `tests/test_rubricas.py` + `test_rubrica_*` |
| Rubricas no export `.xlsx` (aba "Orçamento detalhado", subtotais =SUM) | `outputs/planilha.py` | ✨ | `test_planilha_com_rubricas_ganha_aba_orcamento` + `test_exportar_planilha_inclui_rubricas_salvas` |

## Limitações conhecidas do E2E

- Os diálogos NATIVOS de salvar não são automatizados (limitação do Playwright
  com `dialog.showSaveDialog`); a geração dos arquivos é coberta pelos testes
  de contrato do sidecar, que escrevem xlsx/docx reais em `tmp_path`.
- O E2E roda com `HF_MODO_DEGRADADO=1`: determinístico e offline. O caminho
  "IA completa" é coberto por `tests/test_recuperacao.py` (FakeProvider) e
  pela validação manual com o LM Studio (ADR-0011).
- O E2E é um portão **local** (exige o binário do Electron); o CI segue com o
  gate-front (lint + tipos + build), inalterado (T-706).
