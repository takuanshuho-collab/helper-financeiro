"""
Sessão de cofre no sidecar: `423`/login/lock (ADR-0016 §C, REQ-SEC-005) — T-1603.

Cobre o contrato HTTP dos endpoints `/auth/*` e o gate `423 Locked` dos
endpoints de negócio, ponta a ponta via `TestClient` — a mesma técnica do
`tests/test_sidecar.py`, só que aqui a sessão é a protagonista (lá ela é
neutralizada pelo autouse `_sessao_sem_cofre`). `HF_AUTH_PATH`/`HF_DB_PATH`
vivem sempre em `tmp_path`; o relógio (`RelogioFake` de `test_auth.py`) é
injetado nos dois — `Cofre` (TOTP/anti-brute-force) e `SessaoCofre`
(auto-lock) — para os testes avançarem o tempo sem `sleep` real; o
`ParametrosKdf` é o mesmo de baixo custo (`KDF_RAPIDO`).
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sidecar.app import app, sessao_dependencia
from sidecar.auth import Cofre
from sidecar.persistencia import Repositorio, arquivo_em_claro
from sidecar.security import VAR_TOKEN
from sidecar.sessao import SessaoCofre
from tests.test_auth import KDF_RAPIDO, RelogioFake, _totp_valido

TOKEN = "token-de-teste-sessao"
CABECALHO = {"X-HF-Token": TOKEN}
SENHA = "senha-super-secreta"
NOVA_SENHA = "outra-senha-igualmente-forte"
cliente = TestClient(app)


def setup_module(_module):
    os.environ[VAR_TOKEN] = TOKEN


def _nova_sessao(tmp_path, relogio: RelogioFake, auto_lock_min: float = 15.0) -> SessaoCofre:
    return SessaoCofre(
        cofre=Cofre(tmp_path / "auth.json", agora=relogio, parametros_kdf=KDF_RAPIDO),
        caminho_db=tmp_path / "dados.db",
        agora=relogio,
        auto_lock_min=auto_lock_min,
    )


@pytest.fixture()
def cenario(tmp_path):
    """Sessão isolada com relógio manual — instala o override e devolve os 3
    ingredientes que os testes precisam (sessão, relógio, pasta)."""
    relogio = RelogioFake()
    sess = _nova_sessao(tmp_path, relogio)
    app.dependency_overrides[sessao_dependencia] = lambda: sess
    yield sess, relogio, tmp_path
    del app.dependency_overrides[sessao_dependencia]
    sess.fechar()


def _cadastrar(relogio: RelogioFake) -> dict:
    resp = cliente.post("/auth/cadastrar", json={"senha": SENHA}, headers=CABECALHO)
    assert resp.status_code == 200
    return resp.json()


def _login(relogio: RelogioFake, senha: str = SENHA, totp_uri: str | None = None,
          codigo: str | None = None):
    codigo_totp = codigo if codigo is not None else _totp_valido(totp_uri, relogio.t)
    return cliente.post("/auth/login",
                        json={"senha": senha, "codigo_totp": codigo_totp},
                        headers=CABECALHO)


# --- janela de onboarding (sem cofre cadastrado) -----------------------------


def test_sem_cofre_negocio_funciona_e_status_reflete(cenario):
    _sess, _relogio, _tmp = cenario
    status = cliente.get("/auth/status", headers=CABECALHO).json()
    assert status == {"cadastrado": False, "desbloqueado": False, "aguarde_s": 0.0}

    # Endpoint de negócio sem repo — funciona sem login (janela de onboarding).
    resp = cliente.post("/diagnostico", json={}, headers=CABECALHO)
    assert resp.status_code == 200


def test_negocio_sem_token_continua_401(cenario):
    assert cliente.post("/diagnostico", json={}).status_code == 401


# --- cadastro -----------------------------------------------------------------


def test_cadastro_migra_na_hora_e_bloqueia_negocio(cenario):
    _sess, relogio, tmp_path = cenario

    # Simula dados legados em claro (como um usuário do ciclo v2.7 teria).
    legado = Repositorio(tmp_path / "dados.db")
    legado.salvar_estado("perfil", {"renda": {"salario_liquido": 5000.0}})
    legado.fechar()
    assert arquivo_em_claro(tmp_path / "dados.db") is True

    dados = _cadastrar(relogio)
    assert "totp_uri" in dados
    assert len(dados["codigos_recuperacao"]) == 10
    assert len(set(dados["codigos_recuperacao"])) == 10  # todos distintos

    # O banco já saiu do claro NO CADASTRO — não espera o primeiro login.
    assert arquivo_em_claro(tmp_path / "dados.db") is False

    # Sessão continua BLOQUEADA: negócio 423 até o primeiro login.
    status = cliente.get("/auth/status", headers=CABECALHO).json()
    assert status["cadastrado"] is True
    assert status["desbloqueado"] is False
    resp = cliente.post("/diagnostico", json={}, headers=CABECALHO)
    assert resp.status_code == 423
    assert resp.json() == {"detail": "cofre bloqueado"}


def test_cadastro_repetido_409(cenario):
    _sess, relogio, _tmp = cenario
    _cadastrar(relogio)
    resp = cliente.post("/auth/cadastrar", json={"senha": SENHA}, headers=CABECALHO)
    assert resp.status_code == 409


def test_cadastro_senha_fraca_400(cenario):
    resp = cliente.post("/auth/cadastrar", json={"senha": "123"}, headers=CABECALHO)
    assert resp.status_code == 400
    assert "detail" in resp.json()


# --- login ----------------------------------------------------------------


def test_login_desbloqueia_e_le_dados_migrados(cenario):
    _sess, relogio, tmp_path = cenario
    legado = Repositorio(tmp_path / "dados.db")
    legado.salvar_estado("perfil", {"renda": {"salario_liquido": 4321.0}})
    legado.fechar()

    dados = _cadastrar(relogio)
    resp = _login(relogio, totp_uri=dados["totp_uri"])
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    status = cliente.get("/auth/status", headers=CABECALHO).json()
    assert status["desbloqueado"] is True

    # Negócio volta a responder — e lê exatamente o que estava no legado.
    estado = cliente.get("/estado", headers=CABECALHO)
    assert estado.status_code == 200
    assert estado.json()["perfil"]["renda"]["salario_liquido"] == 4321.0


def test_login_senha_errada_401(cenario):
    _sess, relogio, _tmp = cenario
    dados = _cadastrar(relogio)
    resp = _login(relogio, senha="senha-totalmente-errada", totp_uri=dados["totp_uri"])
    assert resp.status_code == 401
    assert set(resp.json().keys()) == {"detail"}


def test_login_totp_errado_401(cenario):
    _sess, relogio, _tmp = cenario
    _cadastrar(relogio)
    resp = _login(relogio, codigo="000000")
    assert resp.status_code == 401


def test_login_anti_brute_force_429(cenario):
    _sess, relogio, _tmp = cenario
    dados = _cadastrar(relogio)
    for _ in range(3):
        resp = _login(relogio, senha="senha-errada-de-novo", totp_uri=dados["totp_uri"])
        assert resp.status_code == 401
    resp = _login(relogio, totp_uri=dados["totp_uri"])  # credenciais certas, tarde demais
    assert resp.status_code == 429
    corpo = resp.json()
    assert set(corpo.keys()) == {"detail", "aguarde_s"}
    assert corpo["aguarde_s"] > 0
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) >= 1


# --- bloqueio manual --------------------------------------------------------


def test_bloqueio_manual_e_login_reabre(cenario):
    _sess, relogio, _tmp = cenario
    dados = _cadastrar(relogio)
    assert _login(relogio, totp_uri=dados["totp_uri"]).status_code == 200
    assert cliente.post("/diagnostico", json={}, headers=CABECALHO).status_code == 200

    resp = cliente.post("/auth/bloquear", headers=CABECALHO)
    assert resp.status_code == 200
    assert cliente.post("/diagnostico", json={}, headers=CABECALHO).status_code == 423

    # Idempotente: bloquear de novo não quebra nada.
    assert cliente.post("/auth/bloquear", headers=CABECALHO).status_code == 200

    relogio.avancar(31.0)  # novo passo TOTP — o anterior já foi consumido (anti-replay)
    resp = _login(relogio, totp_uri=dados["totp_uri"])
    assert resp.status_code == 200
    assert cliente.post("/diagnostico", json={}, headers=CABECALHO).status_code == 200


# --- auto-lock por inatividade ----------------------------------------------


def test_auto_lock_apos_inatividade(tmp_path):
    relogio = RelogioFake()
    sess = _nova_sessao(tmp_path, relogio, auto_lock_min=5.0)  # 5 min = 300 s
    app.dependency_overrides[sessao_dependencia] = lambda: sess
    try:
        dados = _cadastrar(relogio)
        assert _login(relogio, totp_uri=dados["totp_uri"]).status_code == 200
        assert cliente.post("/diagnostico", json={}, headers=CABECALHO).status_code == 200

        relogio.avancar(301.0)  # > 5 min de inatividade
        resp = cliente.post("/diagnostico", json={}, headers=CABECALHO)
        assert resp.status_code == 423

        status = cliente.get("/auth/status", headers=CABECALHO).json()
        assert status["desbloqueado"] is False
    finally:
        del app.dependency_overrides[sessao_dependencia]
        sess.fechar()


def test_auto_lock_desligado_com_zero(tmp_path):
    relogio = RelogioFake()
    sess = _nova_sessao(tmp_path, relogio, auto_lock_min=0.0)  # 0 = desliga
    app.dependency_overrides[sessao_dependencia] = lambda: sess
    try:
        dados = _cadastrar(relogio)
        assert _login(relogio, totp_uri=dados["totp_uri"]).status_code == 200

        relogio.avancar(10_000.0)  # bem além de qualquer limite razoável
        resp = cliente.post("/diagnostico", json={}, headers=CABECALHO)
        assert resp.status_code == 200
    finally:
        del app.dependency_overrides[sessao_dependencia]
        sess.fechar()


def test_auto_lock_nao_conta_consultas_de_status(tmp_path):
    """`/auth/status` não é atividade de negócio — não deve adiar o auto-lock."""
    relogio = RelogioFake()
    sess = _nova_sessao(tmp_path, relogio, auto_lock_min=5.0)
    app.dependency_overrides[sessao_dependencia] = lambda: sess
    try:
        dados = _cadastrar(relogio)
        assert _login(relogio, totp_uri=dados["totp_uri"]).status_code == 200

        # Poll de status ao longo do tempo, sem uso de negócio real.
        for _ in range(3):
            relogio.avancar(120.0)
            cliente.get("/auth/status", headers=CABECALHO)

        # 360 s de INATIVIDADE de negócio (só polls de status) > 300 s do limite.
        resp = cliente.post("/diagnostico", json={}, headers=CABECALHO)
        assert resp.status_code == 423
    finally:
        del app.dependency_overrides[sessao_dependencia]
        sess.fechar()


# --- gancho ao_bloquear: descarte de PII no bloqueio (C-04) ------------------
def _sessao_com_gancho(tmp_path, relogio, disparos, auto_lock_min=15.0) -> SessaoCofre:
    return SessaoCofre(
        cofre=Cofre(tmp_path / "auth.json", agora=relogio, parametros_kdf=KDF_RAPIDO),
        caminho_db=tmp_path / "dados.db",
        agora=relogio,
        auto_lock_min=auto_lock_min,
        ao_bloquear=lambda: disparos.append(1),
    )


def test_gancho_ao_bloquear_dispara_no_bloqueio_manual(tmp_path):
    """O bloqueio manual dispara `ao_bloquear` exatamente uma vez; bloquear já
    bloqueado NÃO redispara (idempotência preservada)."""
    relogio = RelogioFake()
    disparos: list[int] = []
    sess = _sessao_com_gancho(tmp_path, relogio, disparos)
    app.dependency_overrides[sessao_dependencia] = lambda: sess
    try:
        dados = _cadastrar(relogio)
        assert _login(relogio, totp_uri=dados["totp_uri"]).status_code == 200

        assert cliente.post("/auth/bloquear", headers=CABECALHO).status_code == 200
        assert disparos == [1]  # disparou uma vez no bloqueio de sessão aberta
        assert cliente.post("/auth/bloquear", headers=CABECALHO).status_code == 200
        assert disparos == [1]  # já bloqueado: não redispara
    finally:
        del app.dependency_overrides[sessao_dependencia]
        sess.fechar()


def test_gancho_ao_bloquear_dispara_no_auto_lock(tmp_path):
    """O auto-lock por inatividade também passa pelo ponto único de descarte da
    DEK — logo dispara `ao_bloquear` (a PII não pode sobreviver ao auto-lock)."""
    relogio = RelogioFake()
    disparos: list[int] = []
    sess = _sessao_com_gancho(tmp_path, relogio, disparos, auto_lock_min=5.0)
    app.dependency_overrides[sessao_dependencia] = lambda: sess
    try:
        dados = _cadastrar(relogio)
        assert _login(relogio, totp_uri=dados["totp_uri"]).status_code == 200

        relogio.avancar(301.0)  # > 5 min de inatividade
        assert cliente.post("/diagnostico", json={}, headers=CABECALHO).status_code == 423
        assert disparos == [1]  # o auto-lock disparou o gancho
    finally:
        del app.dependency_overrides[sessao_dependencia]
        sess.fechar()


def test_sessao_do_processo_arma_descarte_de_jobs_ia():
    """Fim a fim de produção: `sessao_dependencia` arma `_descartar_jobs_ia`
    como gancho da sessão do processo (C-04)."""
    from sidecar import app as app_mod
    from sidecar.sessao import resetar_sessao

    resetar_sessao()
    try:
        sess = app_mod.sessao_dependencia()
        assert sess.ao_bloquear is app_mod._descartar_jobs_ia
    finally:
        resetar_sessao()


# --- recuperação -------------------------------------------------------------


def test_recuperacao_redefine_senha_desbloqueia_e_codigo_nao_reusa(cenario):
    _sess, relogio, _tmp = cenario
    dados = _cadastrar(relogio)
    codigo = dados["codigos_recuperacao"][0]

    resp = cliente.post("/auth/recuperar",
                        json={"codigo": codigo, "nova_senha": NOVA_SENHA},
                        headers=CABECALHO)
    assert resp.status_code == 200
    assert cliente.get("/auth/status", headers=CABECALHO).json()["desbloqueado"] is True
    assert cliente.post("/diagnostico", json={}, headers=CABECALHO).status_code == 200

    # A senha antiga não abre mais; a nova sim.
    cliente.post("/auth/bloquear", headers=CABECALHO)
    assert _login(relogio, senha=SENHA, totp_uri=dados["totp_uri"]).status_code == 401
    assert _login(relogio, senha=NOVA_SENHA, totp_uri=dados["totp_uri"]).status_code == 200

    # Código de recuperação é de uso único.
    cliente.post("/auth/bloquear", headers=CABECALHO)
    resp2 = cliente.post("/auth/recuperar",
                         json={"codigo": codigo, "nova_senha": "mais-uma-senha-forte"},
                         headers=CABECALHO)
    assert resp2.status_code == 401


def test_recuperacao_senha_fraca_400(cenario):
    _sess, relogio, _tmp = cenario
    dados = _cadastrar(relogio)
    codigo = dados["codigos_recuperacao"][0]
    resp = cliente.post("/auth/recuperar", json={"codigo": codigo, "nova_senha": "123"},
                        headers=CABECALHO)
    assert resp.status_code == 400


# --- troca de senha ----------------------------------------------------------


def test_trocar_senha_exige_desbloqueado(cenario):
    _sess, relogio, _tmp = cenario
    _cadastrar(relogio)
    resp = cliente.post("/auth/trocar-senha",
                        json={"senha_atual": SENHA, "codigo_totp": "000000",
                              "nova_senha": NOVA_SENHA},
                        headers=CABECALHO)
    assert resp.status_code == 423


def test_trocar_senha_com_fatores_validos_e_login_com_a_nova(cenario):
    _sess, relogio, _tmp = cenario
    dados = _cadastrar(relogio)
    assert _login(relogio, totp_uri=dados["totp_uri"]).status_code == 200

    relogio.avancar(31.0)  # novo passo TOTP — o do login já foi consumido
    codigo_totp = _totp_valido(dados["totp_uri"], relogio.t)
    resp = cliente.post("/auth/trocar-senha",
                        json={"senha_atual": SENHA, "codigo_totp": codigo_totp,
                              "nova_senha": NOVA_SENHA},
                        headers=CABECALHO)
    assert resp.status_code == 200

    cliente.post("/auth/bloquear", headers=CABECALHO)
    assert _login(relogio, senha=SENHA, totp_uri=dados["totp_uri"]).status_code == 401
    relogio.avancar(31.0)  # novo passo — o da troca de senha já foi consumido
    assert _login(relogio, senha=NOVA_SENHA, totp_uri=dados["totp_uri"]).status_code == 200


# --- migração fim-a-fim -------------------------------------------------------


def test_migracao_fim_a_fim_dados_iguais_no_cofre(cenario):
    _sess, relogio, tmp_path = cenario
    legado = Repositorio(tmp_path / "dados.db")
    legado.salvar_estado("perfil", {"renda": {"salario_liquido": 9999.0}})
    legado.criar_rubrica("fixas", "moradia", "Aluguel", 1500.0)
    legado.fechar()

    dados = _cadastrar(relogio)
    assert _login(relogio, totp_uri=dados["totp_uri"]).status_code == 200

    estado = cliente.get("/estado", headers=CABECALHO).json()
    assert estado["perfil"]["renda"]["salario_liquido"] == 9999.0
    assert estado["rubricas"][0]["nome"] == "Aluguel"
    assert estado["rubricas"][0]["valor"] == 1500.0


# --- 423/401/429 não vazam segredo -------------------------------------------


def test_respostas_de_erro_nao_vazam_segredo(cenario):
    _sess, relogio, _tmp = cenario
    dados = _cadastrar(relogio)

    bloqueado = cliente.post("/diagnostico", json={}, headers=CABECALHO)
    assert bloqueado.status_code == 423
    assert set(bloqueado.json().keys()) == {"detail"}

    senha_errada = _login(relogio, senha="errada-mesmo", totp_uri=dados["totp_uri"])
    assert senha_errada.status_code == 401
    corpo = senha_errada.json()
    assert set(corpo.keys()) == {"detail"}
    assert "dek" not in corpo["detail"].lower()
    assert dados["totp_uri"].split("secret=")[1].split("&")[0] not in corpo["detail"]

    for _ in range(3):
        _login(relogio, senha="errada-de-novo", totp_uri=dados["totp_uri"])
    aguarde = _login(relogio, totp_uri=dados["totp_uri"])
    assert aguarde.status_code == 429
    assert set(aguarde.json().keys()) == {"detail", "aguarde_s"}
