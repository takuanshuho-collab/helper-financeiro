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


# -------------------------------------------------- rubricas (CRUD, T-1103)
def test_rubrica_crud_roundtrip(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    criada = repo.criar_rubrica("fixas", "contas_casa", "Conta de luz", 180.0)
    assert criada["id"] is not None

    listadas = repo.listar_rubricas()
    assert listadas == [criada]

    editada = repo.atualizar_rubrica(criada["id"], "Luz + taxa", 195.5)
    assert editada is not None
    assert editada["valor"] == 195.5
    # A ancoragem não muda numa edição.
    assert editada["categoria"] == "fixas"
    assert editada["campo_pai"] == "contas_casa"

    assert repo.remover_rubrica(criada["id"]) is True
    assert repo.listar_rubricas() == []
    repo.fechar()


def test_rubrica_ordenacao_por_grupo_e_ordem(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("variaveis", "mercado", "Feira", 100.0, ordem=1)
    repo.criar_rubrica("fixas", "contas_casa", "Internet", 120.0, ordem=2)
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0, ordem=1)
    nomes = [r["nome"] for r in repo.listar_rubricas()]
    assert nomes == ["Luz", "Internet", "Feira"]
    repo.fechar()


def test_rubrica_id_desconhecido(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    assert repo.atualizar_rubrica(999, "X", 1.0) is None
    assert repo.remover_rubrica(999) is False
    repo.fechar()


def test_rubrica_com_mes_fica_fora_do_orcamento_vivo(tmp_path):
    # A coluna `mes` existe para o histórico mensal futuro (ADR-0012): o
    # orçamento vivo lista só as linhas com mes NULL.
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0)
    with repo._conn:  # simula uma linha de snapshot mensal (v2.5)
        repo._conn.execute(
            "INSERT INTO rubrica (categoria, campo_pai, nome, valor, mes) "
            "VALUES ('fixas', 'contas_casa', 'Luz de julho', 170.0, '2026-07')"
        )
    assert [r["nome"] for r in repo.listar_rubricas()] == ["Luz"]
    repo.fechar()


# ---------------------------------------- histórico mensal (T-1201, ADR-0013)
def test_arquivar_mes_grava_perfil_e_copia_rubricas(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0)
    perfil = {"fixas": {"contas_casa": 180.0}}

    repo.arquivar_mes("2026-07", perfil)

    assert repo.listar_meses() == ["2026-07"]
    assert repo.carregar_mes("2026-07") == perfil
    snapshot = repo.rubricas_do_mes("2026-07")
    assert [r["nome"] for r in snapshot] == ["Luz"]
    # As rubricas VIVAS continuam lá (o snapshot é cópia, não movimentação).
    assert [r["nome"] for r in repo.listar_rubricas()] == ["Luz"]
    repo.fechar()


def test_arquivar_de_novo_substitui_o_snapshot(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0)
    repo.arquivar_mes("2026-07", {"v": 1})

    # O orçamento vivo muda e o mês é arquivado de novo.
    repo.criar_rubrica("fixas", "contas_casa", "Internet", 120.0)
    repo.arquivar_mes("2026-07", {"v": 2})

    assert repo.carregar_mes("2026-07") == {"v": 2}
    assert [r["nome"] for r in repo.rubricas_do_mes("2026-07")] == [
        "Luz", "Internet"]
    assert repo.listar_meses() == ["2026-07"]  # sem duplicar a competência
    repo.fechar()


def test_snapshot_nao_vaza_para_o_orcamento_vivo(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0)
    repo.arquivar_mes("2026-06", {})
    # Editar o vivo depois do arquivamento não toca o snapshot...
    rid = repo.listar_rubricas()[0]["id"]
    repo.atualizar_rubrica(rid, "Luz", 200.0)
    assert repo.rubricas_do_mes("2026-06")[0]["valor"] == 180.0
    # ...e o snapshot não aparece no vivo.
    assert len(repo.listar_rubricas()) == 1
    repo.fechar()


def test_mes_sem_snapshot(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    assert repo.listar_meses() == []
    assert repo.carregar_mes("2026-01") is None
    assert repo.rubricas_do_mes("2026-01") == []
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
