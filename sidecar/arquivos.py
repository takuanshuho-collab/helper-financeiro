"""
Escrita atômica de JSON compartilhada pelo sidecar (C-27).

`auth.json` (cofre) e `llm.json` (modelo ativo) usavam a mesma receita
temp+`os.replace` copiada byte a byte em dois módulos — um `fsync` ou uma
troca de encoding futura teria de lembrar de aplicar nos dois lugares.
Extraído aqui para os dois chamarem a mesma função.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path


def gravar_json_atomico(caminho: Path, dados: dict) -> None:
    """Grava `dados` em `caminho` sem deixar o arquivo truncado a meio.

    Escreve num temporário (nome único por processo+aleatório, no mesmo
    diretório do destino) e promove com `os.replace` — atômico no mesmo
    volume. Se o processo morrer no meio da escrita, o arquivo final nunca
    fica corrompido: ou é o conteúdo antigo, ou o novo completo.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    temporario = caminho.with_name(
        f"{caminho.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )
    temporario.write_text(texto, encoding="utf-8")
    os.replace(temporario, caminho)
