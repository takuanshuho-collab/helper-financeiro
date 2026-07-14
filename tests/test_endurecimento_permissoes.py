"""
Endurecimento de permissões do cofre no fallback POSIX (C-23, T-2101).

No POSIX (`~/.helper_financeiro`) os arquivos do cofre nasceriam com a umask
padrão (0644) e as pastas com 0755 — legíveis por outra conta local, o que
abriria força-bruta offline do Argon2id sobre o `auth.json`. Fechamos arquivos
para 0o600 e pastas para 0o700. No Windows (`%APPDATA%`, ACL herdada) tudo é
no-op: NENHUM `os.chmod`/`os.open(mode=...)` é chamado.

A suíte roda no Windows, então o ramo POSIX é simulado monkeypatchando o guard
único (`os.name`); as chamadas `os.open`/`os.chmod` são espionadas (registram o
`mode` e delegam à função real, para os arquivos existirem de fato) e o `mode`
pedido é conferido contra `0o600`/`0o700`. Revertendo a mudança de produção,
cada teste do ramo POSIX falha (o `os.open` sem mode / o chmod ausente).
"""
from __future__ import annotations

import json
import os

from sidecar.arquivos import (
    _e_posix,
    endurecer_arquivo,
    endurecer_pasta,
    gravar_json_atomico,
)
from sidecar.persistencia import Repositorio


def _espioes(monkeypatch):
    """Envolve `os.open`/`os.chmod` para registrar `(caminho, mode)` e delegar.

    Delega às funções reais para os arquivos serem criados/movidos de verdade
    (o `os.replace` precisa do temporário existir); devolve as duas listas de
    chamadas para os asserts.
    """
    chamadas_open: list[tuple[str, int]] = []
    chamadas_chmod: list[tuple[str, int]] = []
    real_open = os.open
    real_chmod = os.chmod

    def fake_open(caminho, flags, mode=0o777, *a, **k):
        chamadas_open.append((str(caminho), mode))
        return real_open(caminho, flags, mode, *a, **k)

    def fake_chmod(caminho, mode, *a, **k):
        chamadas_chmod.append((str(caminho), mode))
        return real_chmod(caminho, mode, *a, **k)

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "chmod", fake_chmod)
    return chamadas_open, chamadas_chmod


# ------------------------------------------------------------- guard único
def test_guard_posix_distingue_de_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    assert _e_posix() is True
    monkeypatch.setattr(os, "name", "nt")
    assert _e_posix() is False


# ----------------------------------------------- helpers de endurecimento
def test_endurecer_arquivo_e_pasta_no_posix_usam_chmod(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    _open, chmod = _espioes(monkeypatch)

    arquivo = tmp_path / "auth.json"
    arquivo.write_text("{}", encoding="utf-8")
    pasta = tmp_path / "cofre"
    pasta.mkdir()

    endurecer_arquivo(arquivo)
    endurecer_pasta(pasta)

    assert (str(arquivo), 0o600) in chmod
    assert (str(pasta), 0o700) in chmod


def test_endurecer_no_windows_e_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    _open, chmod = _espioes(monkeypatch)

    arquivo = tmp_path / "auth.json"
    arquivo.write_text("{}", encoding="utf-8")
    pasta = tmp_path / "cofre"
    pasta.mkdir()

    endurecer_arquivo(arquivo)
    endurecer_pasta(pasta)

    assert chmod == []  # nenhuma alteração de modo no Windows


# ------------------------------------------------ gravar_json_atomico (C-23)  # noqa: ERA001 — cabeçalho de seção, não código comentado
def test_gravar_json_atomico_no_posix_cria_0600_e_reforca(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    chamadas_open, chamadas_chmod = _espioes(monkeypatch)

    destino = tmp_path / "sub" / "auth.json"
    gravar_json_atomico(destino, {"segredo": "x", "acento": "São João"})

    # 1) O temporário nasce via os.open com mode 0o600 (sem janela de 0644).
    temporarios = [(c, m) for c, m in chamadas_open if c.endswith(".tmp")]
    assert temporarios, "o temporário deveria ser criado via os.open"
    assert all(m == 0o600 for _c, m in temporarios)

    # 2) O destino final é reforçado para 0o600 após o os.replace (defensivo).
    assert (str(destino), 0o600) in chamadas_chmod

    # 2b) A pasta criada pelo próprio helper também é do cofre → 0o700.
    assert (str(destino.parent), 0o700) in chamadas_chmod

    # 3) O conteúdo continua correto (a escrita não regrediu).
    assert json.loads(destino.read_text(encoding="utf-8")) == {
        "segredo": "x", "acento": "São João",
    }


def test_gravar_json_atomico_no_windows_escreve_sem_chmod(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    chamadas_open, chamadas_chmod = _espioes(monkeypatch)

    destino = tmp_path / "sub" / "llm.json"
    gravar_json_atomico(destino, {"modelo": "ministral-3b"})

    # No Windows: escrita comum (write_text) — nenhum os.open com mode, nenhum
    # chmod. Comportamento observável idêntico ao anterior à T-2101.
    assert not [c for c, _m in chamadas_open if c.endswith(".tmp")]
    assert chamadas_chmod == []
    assert json.loads(destino.read_text(encoding="utf-8")) == {"modelo": "ministral-3b"}


# ------------------------------------------------- criação do banco (C-23)
def test_repositorio_endurece_pasta_e_banco_no_posix(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    _open, chmod = _espioes(monkeypatch)

    pasta = tmp_path / "HelperFinanceiro"
    caminho = pasta / "dados.db"
    repo = Repositorio(caminho, dek=None)  # em claro: exercita a criação do arquivo
    repo.fechar()

    assert (str(pasta), 0o700) in chmod    # pasta de dados fechada
    assert (str(caminho), 0o600) in chmod  # arquivo do banco fechado


def test_repositorio_no_windows_nao_endurece(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    _open, chmod = _espioes(monkeypatch)

    pasta = tmp_path / "HelperFinanceiro"
    caminho = pasta / "dados.db"
    repo = Repositorio(caminho, dek=None)
    repo.fechar()

    # Nada de chmod sobre a pasta/arquivo do banco — comportamento intocado.
    nossos = [(c, m) for c, m in chmod if c in (str(pasta), str(caminho))]
    assert nossos == []
    assert caminho.exists()  # o banco foi criado normalmente
