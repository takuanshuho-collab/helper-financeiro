"""
Persistência local em SQLite (ADR-0012, REQ-F-018) — T-1101.

O banco é um arquivo no perfil do usuário gerido só pelo sidecar; aqui
validamos a resolução do caminho, a migração versionada e o roundtrip do
estado (documentos JSON), incluindo reabertura (dados sobrevivem entre
sessões) e acesso concorrente (o sidecar atende em múltiplas threads).
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from sidecar.persistencia import (
    VERSAO_ESQUEMA,
    Repositorio,
    caminho_banco,
)


# ------------------------------------------------------- caminho do banco
def test_hf_db_path_tem_precedencia():
    env = {"HF_DB_PATH": r"C:\tmp\teste.db", "APPDATA": r"C:\Users\x\AppData\Roaming"}
    assert caminho_banco(env) == Path(r"C:\tmp\teste.db")


def test_appdata_e_o_padrao_no_windows():
    env = {"APPDATA": r"C:\Users\x\AppData\Roaming"}
    esperado = Path(r"C:\Users\x\AppData\Roaming") / "HelperFinanceiro" / "dados.db"
    assert caminho_banco(env) == esperado


def test_sem_appdata_cai_na_home():
    caminho = caminho_banco({})
    assert caminho == Path.home() / ".helper_financeiro" / "dados.db"


# ------------------------------------------------------- migração/schema
def test_banco_novo_fica_na_versao_atual(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    assert repo.versao_esquema() == VERSAO_ESQUEMA
    repo.fechar()


def test_migracao_cria_tabelas_estado_e_rubrica(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.fechar()
    con = sqlite3.connect(tmp_path / "dados.db")
    tabelas = {
        linha[0]
        for linha in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    con.close()
    assert {"esquema", "estado", "rubrica"} <= tabelas


def test_reabrir_banco_e_idempotente(tmp_path):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho)
    repo.salvar_estado("perfil", {"reserva_emergencia": 1000.0})
    repo.fechar()

    repo2 = Repositorio(caminho)  # nova "sessão": migração não pode destruir nada
    assert repo2.versao_esquema() == VERSAO_ESQUEMA
    assert repo2.carregar_estado("perfil") == {"reserva_emergencia": 1000.0}
    repo2.fechar()


def test_banco_de_versao_mais_nova_e_recusado(tmp_path):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho)
    repo.fechar()
    con = sqlite3.connect(caminho)
    with con:
        con.execute("UPDATE esquema SET versao = ?", (VERSAO_ESQUEMA + 1,))
    con.close()

    with pytest.raises(RuntimeError, match="versão mais nova"):
        Repositorio(caminho)


def test_diretorio_do_banco_e_criado(tmp_path):
    caminho = tmp_path / "HelperFinanceiro" / "dados.db"  # pasta não existe ainda
    repo = Repositorio(caminho)
    assert caminho.exists()
    repo.fechar()


# --------------------------------------------------------------- estado
def test_roundtrip_do_estado(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    perfil = {
        "renda": {"salario_liquido": 4200.0},
        "fixas": {"contas_casa": 480.5},
        "dividas": [{"credor": "Banco São João", "saldo_devedor": 12000.0}],
    }
    repo.salvar_estado("perfil", perfil)
    assert repo.carregar_estado("perfil") == perfil
    repo.fechar()


def test_salvar_de_novo_sobrescreve(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.salvar_estado("perfil", {"v": 1})
    repo.salvar_estado("perfil", {"v": 2})
    assert repo.carregar_estado("perfil") == {"v": 2}
    repo.fechar()


def test_estado_inexistente_devolve_none(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    assert repo.carregar_estado("perfil") is None
    repo.fechar()


def test_acentos_sobrevivem_ao_roundtrip(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.salvar_estado("perfil", {"credor": "Crédito & Cia — São Paulo"})
    carregado = repo.carregar_estado("perfil")
    assert carregado is not None
    assert carregado["credor"] == "Crédito & Cia — São Paulo"
    repo.fechar()


def test_escritas_concorrentes_nao_se_corrompem(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")

    def gravar(i: int) -> None:
        repo.salvar_estado(f"chave_{i}", {"i": i})

    threads = [threading.Thread(target=gravar, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(16):
        assert repo.carregar_estado(f"chave_{i}") == {"i": i}
    repo.fechar()
