"""
Persistência visível da última análise sênior (T-2602, ADR-0023).

Reusa o fixture `_sessao_sem_cofre` (janela de onboarding, sem cofre) e o
cabeçalho de token de `tests/test_sidecar.py` — mesmo padrão dos demais
módulos de endpoint (ver `tests/test_sidecar_llm.py`). Os testes de cofre
BLOQUEADO montam sua própria sessão cadastrada-mas-não-logada, no mesmo
racional de `tests/test_sessao.py`.
"""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from agent.agente import montar_fatos
from agent.config import ConfigAgente
from agent.grafo import thread_id_analise
from agent.provider import FakeProvider
from contracts import SecaoIA
from core.models import ComposicaoRenda, DespesasFixas, DespesasVariaveis, Divida, PerfilFinanceiro
from sidecar.app import _para_perfil, app, contexto_analise, sessao_dependencia
from sidecar.auth import Cofre
from sidecar.schemas import PerfilIn
from sidecar.security import VAR_TOKEN
from sidecar.sessao import SessaoCofre
from tests.test_auth import KDF_RAPIDO, RelogioFake
from tests.test_sidecar import (
    CABECALHO,
    PERFIL_ANALISE,
    TOKEN,
    ProviderEspiao,
    _esperar_job,
    _sessao_sem_cofre,  # noqa: F401 — fixture autouse reusada
)

cliente = TestClient(app)


def setup_module(_module):
    os.environ[VAR_TOKEN] = TOKEN


def _sessao_atual() -> SessaoCofre:
    """A `SessaoCofre` da fixture autouse `_sessao_sem_cofre` de `test_sidecar`
    (janela de onboarding, sem cofre). Lida direto do override de dependência
    em vez de pedir a fixture por nome como parâmetro — evita colidir (F811)
    com o import acima que a torna autouse neste módulo."""
    return app.dependency_overrides[sessao_dependencia]()


def _perfil_teste() -> PerfilFinanceiro:
    return PerfilFinanceiro.com_orcamento(
        renda=ComposicaoRenda(salario_liquido=6000.0),
        fixas=DespesasFixas(moradia=1500.0),
        variaveis=DespesasVariaveis(),
        dividas=[Divida(credor="Banco Alfa", tipo="Cartão de crédito",
                        saldo_devedor=1000.0, taxa_mensal=0.05, parcela=200.0,
                        parcelas_restantes=6)],
    )


def _secao_minima(modo: str = "completo") -> dict:
    return SecaoIA(modo=modo, sumario="sumário", diagnostico="diagnóstico").model_dump()


# --- job: ordem persistir-ANTES-de-apagar + degradado não persiste ----------


def test_job_completo_persiste_e_apaga_o_checkpoint_depois(monkeypatch):
    """Ordem "persistir-antes-de-apagar" (ADR-0023): quando o espião de
    `apagar_thread_analise` roda, a última análise JÁ deve estar no banco."""
    from sidecar import app as app_mod

    original_apagar = app_mod.apagar_thread_analise
    chamadas: list[str] = []

    def _apagar_espiao(thread_id: str) -> None:
        salva = _sessao_atual().repositorio_ativo().ultima_analise()
        assert salva is not None, "apagou o checkpoint ANTES de persistir"
        chamadas.append(thread_id)
        original_apagar(thread_id)

    monkeypatch.setattr(app_mod, "apagar_thread_analise", _apagar_espiao)

    espiao = ProviderEspiao()
    cfg = ConfigAgente(provider="fake", cache=False)
    cliente.app.dependency_overrides[contexto_analise] = lambda: (cfg, espiao)
    try:
        resp = cliente.post("/analise/ia",
                            json={"perfil": PERFIL_ANALISE, "extra": 100.0},
                            headers=CABECALHO)
        dados = _esperar_job(resp.json()["job_id"])
        assert dados["status"] == "pronto"
        assert dados["secao"]["modo"] == "completo"
        assert len(chamadas) == 1  # apagou exatamente uma vez, depois de persistir

        salva = _sessao_atual().repositorio_ativo().ultima_analise()
        assert salva is not None
        assert salva["secao"]["modo"] == "completo"
        assert salva["modelo"] == cfg.model
        assert salva["assinatura"]
        assert salva["carimbo"]
    finally:
        cliente.app.dependency_overrides.clear()


def test_job_degradado_nao_persiste_e_preserva_a_salva_anterior():
    """Análise degradada não vale os 2-4 min de espera: a antiga salva permanece."""
    repo = _sessao_atual().repositorio_ativo()
    anterior = {"secao": _secao_minima(), "assinatura": "analise:antiga",
               "carimbo": "2026-01-01T00:00:00-03:00", "modelo": "modelo-antigo"}
    repo.salvar_ultima_analise(anterior)

    espiao = ProviderEspiao(erro=ValueError("llm fora do ar"))
    cfg = ConfigAgente(provider="fake", cache=False)
    cliente.app.dependency_overrides[contexto_analise] = lambda: (cfg, espiao)
    try:
        resp = cliente.post("/analise/ia", json={"perfil": PERFIL_ANALISE},
                            headers=CABECALHO)
        dados = _esperar_job(resp.json()["job_id"])
        assert dados["status"] == "pronto"
        assert dados["secao"]["modo"] == "degradado"
        assert repo.ultima_analise() == anterior  # intocada
    finally:
        cliente.app.dependency_overrides.clear()


def test_upsert_segunda_analise_substitui_a_primeira():
    """`salvar_ultima_analise` é upsert: só a ÚLTIMA sobrevive (YAGNI, sem
    histórico por competência)."""
    repo = _sessao_atual().repositorio_ativo()
    repo.salvar_ultima_analise({"secao": _secao_minima(), "assinatura": "analise:a",
                                "carimbo": "2026-01-01T00:00:00-03:00", "modelo": "m1"})
    repo.salvar_ultima_analise({"secao": _secao_minima(), "assinatura": "analise:b",
                                "carimbo": "2026-01-02T00:00:00-03:00", "modelo": "m2"})
    salva = repo.ultima_analise()
    assert salva["assinatura"] == "analise:b"
    assert salva["modelo"] == "m2"


def test_bloqueio_no_meio_do_job_nao_persiste():
    """C-04 (espelha `test_job_ia_descartado_no_meio_nao_ressuscita_pii`): se o
    cofre bloqueia ENQUANTO o job roda, a entrada some de `_JOBS_IA` e o
    worker não pode persistir a análise (mesmo critério do estado do job)."""
    from sidecar import app as app_mod

    perfil = _perfil_teste()
    cfg = ConfigAgente(provider="fake", cache=False)
    with app_mod._JOBS_IA_LOCK:
        app_mod._JOBS_IA["jx"] = {"status": "rodando", "secao": None, "erro": ""}
    app_mod._descartar_jobs_ia()  # cofre bloqueou no meio do job
    app_mod._rodar_job_ia("jx", perfil, 0.0, cfg, FakeProvider(), _sessao_atual())

    assert _sessao_atual().repositorio_ativo().ultima_analise() is None
    with app_mod._JOBS_IA_LOCK:
        assert "jx" not in app_mod._JOBS_IA


# --- POST /analise/ultima ----------------------------------------------------


def test_analise_ultima_sem_salva():
    cfg = ConfigAgente(provider="fake", cache=False)
    cliente.app.dependency_overrides[contexto_analise] = lambda: (cfg, None)
    try:
        resp = cliente.post("/analise/ultima",
                            json={"perfil": PERFIL_ANALISE, "extra": 0.0},
                            headers=CABECALHO)
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["analise_salva"] is None
        assert dados["assinatura_atual"]
    finally:
        cliente.app.dependency_overrides.clear()


def test_analise_ultima_mesmos_dados_assinaturas_iguais():
    cfg = ConfigAgente(provider="fake", cache=False)
    perfil = _para_perfil(PerfilIn(**PERFIL_ANALISE))
    fatos, _ = montar_fatos(perfil, 0.0)
    assinatura = thread_id_analise(cfg, fatos)
    repo = _sessao_atual().repositorio_ativo()
    repo.salvar_ultima_analise({"secao": _secao_minima(), "assinatura": assinatura,
                                "carimbo": "2026-07-17T21:34:00-03:00", "modelo": cfg.model})

    cliente.app.dependency_overrides[contexto_analise] = lambda: (cfg, None)
    try:
        resp = cliente.post("/analise/ultima",
                            json={"perfil": PERFIL_ANALISE, "extra": 0.0},
                            headers=CABECALHO)
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["analise_salva"] is not None
        assert dados["analise_salva"]["assinatura"] == dados["assinatura_atual"]
    finally:
        cliente.app.dependency_overrides.clear()


def test_analise_ultima_dados_alterados_assinaturas_diferentes():
    cfg = ConfigAgente(provider="fake", cache=False)
    perfil = _para_perfil(PerfilIn(**PERFIL_ANALISE))
    fatos, _ = montar_fatos(perfil, 0.0)
    assinatura = thread_id_analise(cfg, fatos)
    repo = _sessao_atual().repositorio_ativo()
    repo.salvar_ultima_analise({"secao": _secao_minima(), "assinatura": assinatura,
                                "carimbo": "2026-07-17T21:34:00-03:00", "modelo": cfg.model})

    cliente.app.dependency_overrides[contexto_analise] = lambda: (cfg, None)
    try:
        # extra diferente ⇒ fatos diferentes (estratégias recalculadas) ⇒
        # assinatura diferente.
        resp = cliente.post("/analise/ultima",
                            json={"perfil": PERFIL_ANALISE, "extra": 500.0},
                            headers=CABECALHO)
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["analise_salva"] is not None
        assert dados["analise_salva"]["assinatura"] != dados["assinatura_atual"]
    finally:
        cliente.app.dependency_overrides.clear()


# --- cofre bloqueado ⇒ 423 (herda do gate `exigir_cofre`) --------------------


def test_analise_ultima_cofre_bloqueado_423(tmp_path):
    """Cofre CADASTRADO mas sem login: `POST /analise/ultima` herda o `423
    Locked` do gate `exigir_cofre`, como qualquer endpoint de negócio."""
    relogio = RelogioFake()
    sess = SessaoCofre(
        cofre=Cofre(tmp_path / "auth.json", agora=relogio, parametros_kdf=KDF_RAPIDO),
        caminho_db=tmp_path / "dados.db",
        agora=relogio,
    )
    app.dependency_overrides[sessao_dependencia] = lambda: sess
    try:
        resp = cliente.post("/auth/cadastrar", json={"senha": "senha-super-secreta"},
                            headers=CABECALHO)
        assert resp.status_code == 200
        resp = cliente.post("/analise/ultima",
                            json={"perfil": PERFIL_ANALISE, "extra": 0.0},
                            headers=CABECALHO)
        assert resp.status_code == 423
    finally:
        del app.dependency_overrides[sessao_dependencia]
        sess.fechar()
