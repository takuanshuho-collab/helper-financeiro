# ADR-0015 — OCR de documento escaneado/imagem, pré-marcação por tipo e citação normalizada

- **Status:** Aceita (2026-07-08)
- **Contexto de processo:** primeira mudança pós-freeze v2.6.0. Esta ADR é a
  autorização formal exigida pela ata: abre o ciclo **v2.7.0** (milestones
  **M14** e **M15**); nova ata será lavrada no fechamento. Escopo decidido pelo
  mantenedor: levar o OCR de documento escaneado/imagem até a aba Contrato
  (M14) e ligá-lo na importação do v2.6 para comprovantes escaneados (M15).
  Code signing segue adiado (depende de certificado do mantenedor).

## Contexto

Desde a v1, `core/extrator_pdf.py` lê o texto do PDF e avisa quando o documento
"parece não conter texto selecionável (provavelmente é uma imagem)" — mas para
por aí: o usuário digita tudo à mão. Contrato fotografado, boleto escaneado e
fatura em imagem são comuns e hoje ficam de fora do funil de extração
(ADR-0010) e da importação (ADR-0014).

O motor de OCR reconhece **texto + caixas + confiança** — ele não sabe que
"R$ 600,00" é a prestação. Quem dá semântica é a LLM sob o verificador
determinístico (ADR-0007/0010). E o texto de OCR traz ruído de glifo
(`0`↔`O`, `1`↔`l`↔`I`, `5`↔`S`, `8`↔`B`) que quebra a trave de citação literal
atual: o número `6OO,OO` (com a letra O) sequer é reconhecido como número.

Decisões do mantenedor (brainstorm do planejamento, com pesquisa de mercado):

- **Motor:** RapidOCR + **PP-OCRv6 medium** via ONNX Runtime. RapidOCR *é* o
  PaddleOCR — os mesmos modelos neurais convertidos para ONNX —, sem a
  dependência de ~500 MB+ do `paddlepaddle`. A qualidade em original ruim é
  função do **calibre** do modelo (medium/"server"), não da biblioteca; o
  PP-OCRv6 medium supera o antigo PP-OCRv5_server em documento degradado.
- **Escopo:** PDF escaneado + imagem (JPG/PNG) na aba Contrato **e** comprovante
  escaneado desembocando na importação do v2.6.
- **Pré-marcação:** o código envolve candidatos por **tipo** (`<valor>`,
  `<data>`, `<percentual>`), preservando a ordem de leitura; a LLM só aponta
  qual candidato é cada campo.
- **Citação:** **casamento normalizado** — a comparação colapsa as confusões
  clássicas de glifo do OCR, sem afrouxar o anti-alucinação.

## Decisão

### A. Detecção determinística da fonte do documento (a bifurcação)

`core/documento.py` decide, **sem LLM e sem OCR**, se um documento já traz
texto selecionável (`FonteDocumento.TEXTO`), é um PDF escaneado
(`ESCANEADO`) ou uma imagem (`IMAGEM`). PDF: mede a densidade de texto por
página (abaixo do limiar ⇒ escaneado); imagem: decidida pela extensão. O
"agente sinalizador" que bifurca o fluxo é **código determinístico e testável
offline**, não um modelo. `precisa_ocr(fonte)` é o sinal que o orquestrador usa
para chamar (ou não) o motor de OCR.

### B. Motor de OCR local (`agent/ocr.py`)

Envolve o **RapidOCR (ONNX Runtime) + PP-OCRv6 medium**, rodando **100% na
máquina** (H2/H7 — imagem/PDF com PII nunca sai do computador; sem rede, os
modelos são empacotados). Páginas de PDF escaneado são rasterizadas com o
**PyMuPDF já presente** (sem dependência nova para isso). A saída é texto
ordenado pela leitura do layout. Sem o motor disponível, o fluxo **degrada**
(P8): o chamador cai no aviso "preencha manualmente" que já existe. O texto de
OCR é **entrada não-confiável** (P5): segue tabulado/delimitado como no
ADR-0010, nunca vira comando.

### C. Pré-marcação por TIPO (`core.documento.anotar_por_tipo`)

Sobre o texto (venha do PDF ou do OCR), o código envolve os **candidatos** a
valor monetário, data e percentual em marcações por tipo —
`<valor>R$ 600,00</valor>`, `<data>01/06/2026</data>`,
`<percentual>2,50%</percentual>` —, preservando a ordem. **São tags de tipo,
nunca semânticas:** o código não decide qual `<valor>` é a prestação; isso
continua sendo a fusão LLM + verificador (ADR-0007/0010). A LLM cita mais fácil
e o verificador confere melhor sobre texto anotado.

### D. Trave de citação com casamento normalizado

`agent/extracao.py` já tolera ruído de **formatação** (acentos, Markdown,
pontuação). A ADR estende `_normalizar` para colapsar também as **confusões de
glifo do OCR** (`0`↔`O`, `1`↔`l`↔`I`, `5`↔`S`, `8`↔`B`) — nas **duas** vias: o
casamento do trecho citado **e** a extração do número (`_numeros_do_trecho`),
para que um valor lido como `6OO,OO` volte a parsear e a conferir. **H1
preservado:** número sem citação verificável continua descartado; o valor
extraído ainda precisa aparecer, após normalização, no trecho cru e bater com o
número.

### E. Comprovante escaneado → importação (M15)

O texto OCRizado de um comprovante/extrato é reconstruído em linhas por layout
e vira uma lista de `Lancamento`, **reusando** a classificação
(`agent/classificacao.py`) e os endpoints `/importar/*` do v2.6 — mesma revisão
humana, mesmo destino (vivo/competência), mesma regra de acréscimo. A entrada
muda (OCR em vez de CSV); o pipeline a jusante é o mesmo.

## Alternativas rejeitadas

- **PaddleOCR completo (`paddlepaddle`)**: mesma qualidade de modelo, mas
  ~500 MB a 1 GB, notoriamente problemático no PyInstaller e incharia o
  instalador (hoje 172 MB) 2–3×. Só valeria pelos módulos extras
  (desentortamento UVDoc, layout/tabelas) — que resolvemos, se preciso, com
  pré-processamento leve.
- **PP-OCRv4 (o "PaddleOCR 4")**: geração superada; o v5 e agora o v6 o batem
  em scan de baixa qualidade e manuscrito.
- **Detector de "é OCRizado?" com LLM**: saber se há camada de texto é
  determinístico (densidade de texto) — não gasta modelo nem introduz não
  determinismo.
- **Tags semânticas por regex** (o código adivinhar `<valor_prestacao>`): o
  layout de scan embaralha rótulo e valor; a semântica fica com a LLM +
  verificador. O código só marca o **tipo**.
- **OCR na nuvem**: documento com PII é o dado mais sensível; H2 por endpoint,
  como no ADR-0010. Sem exceções.
- **Similaridade com limiar (fuzzy) na trave**: limiar é calibração delicada e
  arrisca aceitar citação que não corresponde ao número; a normalização
  determinística de glifos é auditável e não afrouxa H1.

## Consequências

- **Dependências novas** (entram no `PLAN §Stack`, adicionadas no T-1402 com o
  código que as usa): `rapidocr-onnxruntime` + modelos PP-OCRv6 medium
  (det+rec), ~+100 MB no instalador; `opencv-python-headless` **opcional**, só
  ligado se os testes em original ruim exigirem pré-processamento. Rasterização
  reusa o PyMuPDF existente.
- **Empacotamento** é o risco real: os modelos ONNX são *data files* e o
  `onnxruntime` traz binários nativos — o `SidecarHF.spec` precisa de
  `--collect-data`/`--collect-all` (task T-1404, com smoke que OCRiza de
  verdade).
- **Constituição permanece 2.0.0**: nenhum princípio muda. O número segue do
  determinístico (P1); o texto de OCR é entrada não-confiável (P5); OCR roda
  local e offline (H2/H7); texto OCRizado com PII nunca é persistido em claro
  nem logado (REQ-SEC-001/003) — fica só em memória do processo, como o texto
  de PDF hoje.
- Sem migração de schema (`VERSAO_ESQUEMA` permanece 1).

## Requisitos derivados

`REQ-F-024` (OCR de PDF escaneado/imagem na aba Contrato), `REQ-F-025`
(pré-marcação por tipo + citação normalizada) e `REQ-F-026` (comprovante
escaneado → importação) no `SPEC.md` §1; `REQ-NF-006` (OCR local-only, modelos
empacotados, zero rede) no §5. Harness em `tests/test_documento.py` (detector +
pré-marcação), `tests/test_ocr.py` (motor, com fixtures de imagem),
`tests/test_extracao.py` (citação normalizada) e `tests/test_sidecar.py`
(contratos de importação por OCR); E2E em `gui_web/e2e/`.
