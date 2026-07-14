"""
Escrita atômica de JSON e endurecimento de permissões compartilhados pelo
sidecar (C-27, C-23).

`auth.json` (cofre) e `llm.json` (modelo ativo) usavam a mesma receita
temp+`os.replace` copiada byte a byte em dois módulos — um `fsync` ou uma
troca de encoding futura teria de lembrar de aplicar nos dois lugares.
Extraído aqui para os dois chamarem a mesma função.

No mesmo espírito ficam aqui os helpers de permissão do fallback POSIX (C-23):
quando o cofre cai em `~/.helper_financeiro`, os arquivos nasceriam com a umask
padrão (tipicamente 0644), legíveis por outra conta local — o que abriria a
porta para força-bruta offline do Argon2id sobre o `auth.json`. Endurecemos os
arquivos para 0o600 e as pastas para 0o700. No Windows a proteção já vem da ACL
herdada de `%APPDATA%`, então todo o endurecimento é inerte (no-op) — ver
`_e_posix`.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

# Permissões restritivas do cofre no POSIX: só o dono lê/escreve o arquivo
# (0o600) e só o dono entra/lista a pasta (0o700).
_MODO_ARQUIVO = 0o600
_MODO_PASTA = 0o700


def _e_posix() -> bool:
    """`True` em POSIX, `False` no Windows (`os.name == 'nt'`).

    É o guard ÚNICO do endurecimento de permissões (C-23) e vale para os dois
    módulos do sidecar que criam arquivos do cofre. Avaliado em tempo de
    CHAMADA (não no import) de propósito: os testes rodam no Windows e simulam
    o ramo POSIX via `monkeypatch.setattr(os, "name", ...)`. No Windows nenhum
    `os.chmod`/`os.open(mode=...)` é executado — a ACL de `%APPDATA%` já protege.
    """
    return os.name != "nt"


def endurecer_arquivo(caminho: Path) -> None:
    """Restringe `caminho` a 0o600 (só o dono lê/escreve) no POSIX; no-op no Windows."""
    if _e_posix():
        os.chmod(caminho, _MODO_ARQUIVO)


def endurecer_pasta(caminho: Path) -> None:
    """Restringe `caminho` a 0o700 (só o dono entra/lista) no POSIX; no-op no Windows."""
    if _e_posix():
        os.chmod(caminho, _MODO_PASTA)


def gravar_json_atomico(caminho: Path, dados: dict) -> None:
    """Grava `dados` em `caminho` sem deixar o arquivo truncado a meio.

    Escreve num temporário (nome único por processo+aleatório, no mesmo
    diretório do destino) e promove com `os.replace` — atômico no mesmo
    volume. Se o processo morrer no meio da escrita, o arquivo final nunca
    fica corrompido: ou é o conteúdo antigo, ou o novo completo.

    No POSIX (C-23) o temporário nasce JÁ com 0o600 via `os.open` — nunca há a
    janela em que ele existiria com a umask padrão (0644) antes de um chmod.
    Como `os.replace` preserva o inode no mesmo volume, o destino herda esse
    modo; reforçamos com `endurecer_arquivo` por garantia (é barato). No Windows
    a escrita é a comum (`write_text`) e a ACL herdada é quem protege.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # A pasta também é do cofre: se este for o primeiro artefato criado (ex.:
    # `auth.json` antes do banco), ela nasceria 0755 no POSIX — fecha p/ 0o700.
    endurecer_pasta(caminho.parent)
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    temporario = caminho.with_name(
        f"{caminho.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )
    _escrever_texto(temporario, texto)
    os.replace(temporario, caminho)
    endurecer_arquivo(caminho)


def _escrever_texto(caminho: Path, texto: str) -> None:
    """Escreve `texto` em UTF-8 no `caminho`.

    No POSIX cria o arquivo já com 0o600 (via `os.open`), fechando a janela em
    que o temporário existiria com a umask padrão (0644) antes de um chmod. No
    Windows usa a escrita comum (`write_text`) — comportamento intocado.
    """
    if _e_posix():
        fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _MODO_ARQUIVO)
        with os.fdopen(fd, "w", encoding="utf-8") as saida:
            saida.write(texto)
    else:
        caminho.write_text(texto, encoding="utf-8")
