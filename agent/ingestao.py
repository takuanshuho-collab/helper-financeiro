"""
Ingestão local de documentos financeiros (ADR-0007, T-255).

LlamaIndex entra APENAS como camada de leitura/chunking/retrieval — a síntese
é sempre do nosso pipeline (guardrails H1/H2). Tudo local: leitura via
readers-file, embeddings via Ollama (`nomic-embed-text`), índice em memória.

Documento pequeno nem passa por embeddings: vai inteiro para a extração.
Retrieval só quando o texto estouraria o contexto do modelo (num_ctx 8192).
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import ConfigAgente

log = logging.getLogger("helper_financeiro.ingestao")

# ~6k chars ≈ 1,5k tokens: cabe com folga no num_ctx 8192 junto com o prompt.
LIMITE_DIRETO_CHARS = 6_000
# Consulta fixa: queremos os trechos com as condições financeiras do contrato.
CONSULTA_PADRAO = (
    "condições financeiras: valor do empréstimo, saldo devedor, taxa de juros, "
    "valor da parcela, quantidade de parcelas, credor"
)
MODELO_EMBEDDINGS = "nomic-embed-text"


def carregar_documento(caminho: str | Path) -> str:
    """Lê um documento (.pdf/.txt/.docx) e devolve o texto plano.

    O texto resultante é ENTRADA NÃO CONFIÁVEL (H5): vai para o prompt sempre
    delimitado (`montar_prompt_extracao`) e nunca vira instrução.
    """
    from llama_index.core import SimpleDirectoryReader

    docs = SimpleDirectoryReader(input_files=[str(caminho)]).load_data()
    return "\n".join(d.text for d in docs if d.text)


def _raiz_ollama(cfg: ConfigAgente) -> str:
    return cfg.base_url.rstrip("/").removesuffix("/v1")


def preparar_contexto(texto: str, cfg: ConfigAgente,
                      consulta: str = CONSULTA_PADRAO, k: int = 4) -> str:
    """Devolve o texto a enviar ao extrator, respeitando a janela de contexto.

    - Texto curto → vai inteiro (zero mágica, zero embeddings).
    - Texto longo → SentenceSplitter + VectorStoreIndex em memória +
      retriever top-k (ADR-0007: `as_retriever`, NUNCA `as_query_engine`).
    """
    if len(texto) <= LIMITE_DIRETO_CHARS:
        return texto

    from llama_index.core import Document, VectorStoreIndex
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.embeddings.ollama import OllamaEmbedding

    indice = VectorStoreIndex.from_documents(
        [Document(text=texto)],
        transformations=[SentenceSplitter(chunk_size=512, chunk_overlap=64)],
        embed_model=OllamaEmbedding(model_name=MODELO_EMBEDDINGS,
                                    base_url=_raiz_ollama(cfg)),
    )
    nos = indice.as_retriever(similarity_top_k=k).retrieve(consulta)
    log.info("Retrieval: %d chunks selecionados de um documento de %d chars.",
             len(nos), len(texto))
    return "\n---\n".join(n.get_content() for n in nos)
