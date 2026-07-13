"""
Ingestão local de documentos financeiros (ADR-0007, T-255).

Documento pequeno vai inteiro para a extração. Documento maior que o teto de
caracteres é truncado — decisão consciente do portão M19 (C-19): o ramo de
retrieval por embeddings (LlamaIndex + `VectorStoreIndex` + `OllamaEmbedding`,
que existiu aqui até a T-1909) era código quase-morto no produto embarcado —
o runtime local (llama-server, ADR-0016) não expõe `/api/embed`, então o
sidecar (`sidecar/app.py::_contexto_seguro`) já truncava SEMPRE para qualquer
provider fora de Ollama, e mesmo com Ollama externo o ramo não tinha teste
offline (54,2% de cobertura). Quem usa Ollama externo com documento longo não
perde a EXTRAÇÃO (o texto sempre chega, truncado nas primeiras páginas — onde
ficam os dados do contrato) — perde só o retrieval por relevância, que nunca
foi exercitado fora de produção.
"""
from __future__ import annotations

from .config import ConfigAgente

# ~6k chars ≈ 1,5k tokens: cabe com folga no num_ctx 8192 junto com o prompt.
LIMITE_DIRETO_CHARS = 6_000


def preparar_contexto(texto: str, cfg: ConfigAgente) -> str:
    """Devolve o texto a enviar ao extrator, respeitando a janela de contexto.

    Texto curto vai inteiro; texto longo é truncado em `LIMITE_DIRETO_CHARS`
    (C-19: sem retrieval, ver docstring do módulo). `cfg` fica no parâmetro
    por compatibilidade de assinatura com os chamadores (`sidecar/app.py`,
    `gui/app.py`) — não é usado.
    """
    del cfg
    return texto[:LIMITE_DIRETO_CHARS]
