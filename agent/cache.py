"""
Cache local de análises (T-205).

Evita repetir custo/latência do LLM quando os MESMOS fatos voltam a ser
analisados (ex.: usuário clica em "Analisar" duas vezes seguidas).

Decisões de projeto:
  - SÓ memória, nunca disco: o conteúdo referencia tokens (CREDOR_1) cujo mapa
    também é só-memória (REQ-SEC-003); nada persiste entre execuções.
  - Guarda JSON, não o objeto: cada acerto devolve uma instância NOVA, imune a
    mutações do pipeline (ex.: `garantir_aviso` edita o sumário in place).
  - Só entra no cache análise que passou pelos guardrails (quem garante isso é
    o orquestrador); uma saída reprovada nunca fica "grudada" na sessão.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict

from contracts import AnaliseAgente, FatosFinanceiros


class CacheAnalises:
    """LRU pequeno e explícito — sem dependências, fácil de raciocinar."""

    def __init__(self, capacidade: int = 32):
        self._capacidade = capacidade
        self._dados: OrderedDict[str, str] = OrderedDict()

    @staticmethod
    def chave(provider: str, model: str, fatos: FatosFinanceiros) -> str:
        """Mesmos fatos + mesmo modelo ⇒ mesma análise pode ser reaproveitada."""
        base = f"{provider}|{model}|{fatos.model_dump_json()}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def obter(self, chave: str) -> AnaliseAgente | None:
        json_analise = self._dados.get(chave)
        if json_analise is None:
            return None
        self._dados.move_to_end(chave)
        return AnaliseAgente.model_validate_json(json_analise)

    def guardar(self, chave: str, analise: AnaliseAgente) -> None:
        self._dados[chave] = analise.model_dump_json()
        self._dados.move_to_end(chave)
        while len(self._dados) > self._capacidade:
            self._dados.popitem(last=False)

    def limpar(self) -> None:
        self._dados.clear()

    def __len__(self) -> int:
        return len(self._dados)


# Instância do processo (a GUI é single-user; testes limpam via fixture).
cache_global = CacheAnalises()
