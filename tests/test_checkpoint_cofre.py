"""
Checkpoint durável do grafo no cofre cifrado (ADR-0023, T-2601).

Cobre os critérios de fechamento do T-2601: proxy chaveável (delega/troca),
saver durável real num `dados.db` SQLCipher, **varredura anti-PII do checkpoint
INTEIRO por super-step** (incl. estado pós-`gerar` pré-`sanear`), retomada só de
thread inacabado, poda de órfãos, escrita não-fatal sob falha de lock, toggle
tolerante + Plano C na sessão, e WAL (liga no armar, consolida no desarmar). Tudo
offline com `FakeProvider`/derivados (sem rede).
"""
from __future__ import annotations

import logging
import secrets
import sqlite3
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent.agente import montar_fatos
from agent.config import ConfigAgente
from agent.grafo import (
    armar_checkpointer_duravel,
    criar_checkpointer,
    desarmar_checkpointer_duravel,
    executar_analise,
    grafo_analise,
    serde_checkpoint,
    thread_id_analise,
)
from agent.provider import FakeProvider
from core.models import Divida, PerfilFinanceiro
from sidecar.checkpoint_cofre import abrir_saver_cofre, fechar_saver_cofre
from sidecar.gestor_modelos import retomar_analises_configurado
from sidecar.persistencia import ChaveInvalida, Repositorio, migrar_para_cofre
from sidecar.sessao import SessaoCofre

# Nome de credor SENTINELA: é a PII que jamais pode aparecer no checkpoint. Os
# VALORES (saldo, taxa) não são sentinela — eles viajam anonimizados nos fatos
# por construção; só o NOME é substituído por CREDOR_n (guardrails/pii.py).
CREDOR_SENTINELA = "BANCO-SENTINELA-SECRETO-ZZZ"
CFG_FAKE = ConfigAgente(provider="fake", cache=False)


@pytest.fixture(autouse=True)
def _reset_proxy():
    """Cada teste começa e termina com o proxy em memória — o proxy é um
    singleton de processo, então isolamos a troca de delegate entre testes."""
    desarmar_checkpointer_duravel()
    yield
    desarmar_checkpointer_duravel()


def _perfil(credor: str = CREDOR_SENTINELA, saldo: float = 8000.0) -> PerfilFinanceiro:
    return PerfilFinanceiro(
        renda_liquida=5000, despesas_fixas=2200, despesas_variaveis=800,
        reserva_emergencia=0, saldo_fgts=3000,
        dividas=[Divida(credor, "Cartão de crédito", saldo, 0.12, 900, 12)],
    )


def _cofre_tmp(tmp_path: Path) -> tuple[Path, bytes]:
    """Cria um `dados.db` SQLCipher com DEK aleatória (via migração do claro)."""
    db = tmp_path / "dados.db"
    dek = secrets.token_bytes(32)
    repo = Repositorio(db)
    repo.salvar_estado("perfil", {"renda": {"salario_liquido": 5000.0}})
    repo.fechar()
    migrar_para_cofre(db, dek)
    return db, dek


def _texto_de_todos_os_blobs(saver) -> str:
    """Decodifica e concatena TODOS os blobs de checkpoint/write de TODAS as
    linhas (todos os super-steps): `checkpoint` e `metadata` de `checkpoints` e
    `value` de `writes`. É o material sobre o qual a varredura anti-PII incide."""
    serde = saver.serde
    partes: list[str] = []
    for tipo, blob, meta in saver.conn.execute(
            "SELECT type, checkpoint, metadata FROM checkpoints"):
        partes.append(repr(serde.loads_typed((tipo, bytes(blob)))))
        partes.append(bytes(meta).decode("utf-8", "ignore"))  # metadata é JSON UTF-8
    for tipo, val in saver.conn.execute("SELECT type, value FROM writes"):
        partes.append(repr(serde.loads_typed((tipo, bytes(val)))))
    return "\n".join(partes)


# --------------------------------------------------------------- (1) proxy
class _DelegateEspiao(InMemorySaver):
    """InMemorySaver que conta os `put` — prova a delegação do proxy."""

    def __init__(self) -> None:
        super().__init__(serde=serde_checkpoint())
        self.puts = 0

    def put(self, *a, **k):
        self.puts += 1
        return super().put(*a, **k)


def test_proxy_delega_e_troca_de_delegate():
    espiao = _DelegateEspiao()
    armar_checkpointer_duravel(espiao)
    proxy = criar_checkpointer()
    assert proxy._atual() is espiao

    executar_analise(*montar_fatos(_perfil()), CFG_FAKE, FakeProvider())
    assert espiao.puts > 0  # o grafo gravou ATRAVÉS do proxy no delegate armado

    # Desarmar volta a um InMemorySaver NOVO (nada vaza) — não o espião, e um
    # objeto diferente a cada desarme.
    desarmar_checkpointer_duravel()
    novo1 = proxy._atual()
    assert isinstance(novo1, InMemorySaver) and novo1 is not espiao
    desarmar_checkpointer_duravel()
    assert proxy._atual() is not novo1


# --------------------------------------------------- (2) saver durável real
def test_saver_duravel_grava_e_le_no_cofre(tmp_path):
    db, dek = _cofre_tmp(tmp_path)
    saver = abrir_saver_cofre(db, dek)
    try:
        armar_checkpointer_duravel(saver)
        fatos, mapa = montar_fatos(_perfil())
        tid = "analise:teste-durabilidade"
        cfg_thread = {"configurable": {"thread_id": tid}}
        res = executar_analise(fatos, mapa, CFG_FAKE, FakeProvider(), thread_id=tid)
        assert res.modo == "completo"

        # Lê de volta o estado final DO COFRE (nova consulta ao grafo).
        snap = grafo_analise().get_state(cfg_thread)
        assert snap.values["analise"] is not None
        # A serde do saver durável é a MESMA allowlist do modo memória: um tipo
        # de `contracts` fora dela nem seria desserializado (round-trip acima
        # prova que os tipos permitidos voltam intactos do cofre).
        from agent.grafo import _TIPOS_PERMITIDOS_CHECKPOINT
        assert ("contracts.schemas", "AnaliseAgente") in _TIPOS_PERMITIDOS_CHECKPOINT
        # Prova física: há linhas cifradas de checkpoint no dados.db.
        n = saver.conn.execute("SELECT count(*) FROM checkpoints").fetchone()[0]
        assert n > 0
    finally:
        desarmar_checkpointer_duravel()
        fechar_saver_cofre(saver)


# ------------------------------------------------------------ (3) anti-PII
class _ProviderExemploFabricado:
    """Análise fundamentada + UMA frase acessória com número órfão (persistente)
    ⇒ dispara retry e depois `sanear`, materializando o estado pós-`gerar`
    pré-`sanear` (saída crua do LLM) como checkpoint a ser varrido."""

    def __init__(self) -> None:
        self._bom = FakeProvider()

    def analisar(self, fatos):
        analise = self._bom.analisar(fatos)
        analise.diagnostico_interpretado += (
            " Considere renegociar (ex.: R$ 77.777,00 por mês).")
        return analise


def test_checkpoint_nunca_contem_pii_do_perfil(tmp_path):
    db, dek = _cofre_tmp(tmp_path)
    saver = abrir_saver_cofre(db, dek)
    try:
        armar_checkpointer_duravel(saver)
        fatos, mapa = montar_fatos(_perfil())
        # retomar=False + thread_id fixo ⇒ SEM higiene: os checkpoints de TODOS
        # os super-steps ficam no cofre para a varredura (incl. pós-`gerar`).
        res = executar_analise(fatos, mapa, CFG_FAKE, _ProviderExemploFabricado(),
                               thread_id="analise:anti-pii")
        assert res.modo == "completo"

        texto = _texto_de_todos_os_blobs(saver)
        assert CREDOR_SENTINELA not in texto  # o NOME real jamais aparece
        assert "CREDOR_1" in texto            # mas o token aparece (gravou mesmo)
    finally:
        desarmar_checkpointer_duravel()
        fechar_saver_cofre(saver)


# ----------------------------------------------------------- (4) retomada
class _ProviderInterrompeUmaVez:
    """1ª chamada mata o nó `chamar_llm` com `KeyboardInterrupt` (fora do catch
    do grafo, que só engole `Exception`); 2ª em diante responde bem."""

    def __init__(self) -> None:
        self.chamadas = 0
        self._bom = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        if self.chamadas == 1:
            raise KeyboardInterrupt("processo morto no meio da geração")
        return self._bom.analisar(fatos)


def test_retomada_de_thread_inacabado_nao_reexecuta_tudo(tmp_path):
    db, dek = _cofre_tmp(tmp_path)
    saver = abrir_saver_cofre(db, dek)
    try:
        armar_checkpointer_duravel(saver)
        fatos, mapa = montar_fatos(_perfil())
        tid = thread_id_analise(CFG_FAKE, fatos)
        cfg_thread = {"configurable": {"thread_id": tid}}
        prov = _ProviderInterrompeUmaVez()

        with pytest.raises(KeyboardInterrupt):
            executar_analise(fatos, mapa, CFG_FAKE, prov, retomar=True)
        # Thread ficou INACABADO com o nó pendente registrado.
        assert grafo_analise().get_state(cfg_thread).next == ("chamar_llm",)

        # Retomar: completa SÓ porque continua do checkpoint (o input é `None`;
        # um restart do zero com input `None` quebraria — não há fatos no input).
        res = executar_analise(fatos, mapa, CFG_FAKE, prov, retomar=True)
        assert res.modo == "completo"
        assert prov.chamadas == 2  # a geração rodou uma vez na retomada
        # Higiene: sucesso apaga o thread.
        assert grafo_analise().get_state(cfg_thread).created_at is None
    finally:
        desarmar_checkpointer_duravel()
        fechar_saver_cofre(saver)


# --------------------------------------------- (5) thread completo nunca retoma
class _ProviderContado:
    def __init__(self) -> None:
        self.chamadas = 0
        self._bom = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        return self._bom.analisar(fatos)


def test_thread_completo_nunca_e_retomado(tmp_path):
    db, dek = _cofre_tmp(tmp_path)
    saver = abrir_saver_cofre(db, dek)
    try:
        armar_checkpointer_duravel(saver)
        fatos, mapa = montar_fatos(_perfil())
        tid = thread_id_analise(CFG_FAKE, fatos)

        # Semeia um thread COMPLETO (sem higiene: retomar=False + thread_id fixo).
        executar_analise(fatos, mapa, CFG_FAKE, FakeProvider(), thread_id=tid)
        assert grafo_analise().get_state({"configurable": {"thread_id": tid}}).next == ()

        # retomar=True sobre thread completo: apaga e RODA DO ZERO (não serve o
        # resultado velho) ⇒ o provider novo é chamado.
        prov = _ProviderContado()
        res = executar_analise(fatos, mapa, CFG_FAKE, prov, retomar=True)
        assert res.modo == "completo"
        assert prov.chamadas == 1  # rodou fresco; não serviu resultado antigo
    finally:
        desarmar_checkpointer_duravel()
        fechar_saver_cofre(saver)


# ------------------------------------------------------------------- (6) poda
def test_poda_apaga_inacabado_de_assinatura_antiga(tmp_path):
    db, dek = _cofre_tmp(tmp_path)
    saver = abrir_saver_cofre(db, dek)
    try:
        armar_checkpointer_duravel(saver)
        # Assinatura A: deixa um thread INACABADO (kill no meio).
        fatos_a, mapa_a = montar_fatos(_perfil(credor="CREDOR-ANTIGO-A"))
        tid_a = thread_id_analise(CFG_FAKE, fatos_a)
        with pytest.raises(KeyboardInterrupt):
            executar_analise(fatos_a, mapa_a, CFG_FAKE,
                             _ProviderInterrompeUmaVez(), retomar=True)
        assert grafo_analise().get_state(
            {"configurable": {"thread_id": tid_a}}).created_at is not None

        # Iniciar a análise de dados DIFERENTES (assinatura B) poda o A órfão.
        fatos_b, mapa_b = montar_fatos(_perfil(credor="CREDOR-NOVO-B", saldo=9999.0))
        res = executar_analise(fatos_b, mapa_b, CFG_FAKE, FakeProvider(), retomar=True)
        assert res.modo == "completo"
        assert grafo_analise().get_state(
            {"configurable": {"thread_id": tid_a}}).created_at is None  # A foi podado
    finally:
        desarmar_checkpointer_duravel()
        fechar_saver_cofre(saver)


# ------------------------------------------------------ (7) escrita não-fatal
class _DelegatePutFalha(InMemorySaver):
    """Delegate durável cujo `put`/`put_writes` estoura `OperationalError`
    (lock) — simula a concorrência de escrita perdendo o lock."""

    def put(self, *a, **k):
        raise sqlite3.OperationalError("database is locked")

    def put_writes(self, *a, **k):
        raise sqlite3.OperationalError("database is locked")


def test_escrita_de_checkpoint_nao_fatal(caplog):
    armar_checkpointer_duravel(_DelegatePutFalha())
    with caplog.at_level(logging.WARNING, logger="helper_financeiro.grafo"):
        res = executar_analise(*montar_fatos(_perfil()), CFG_FAKE, FakeProvider())
    assert res.modo == "completo"  # a análise NUNCA aborta pelo checkpoint (G2)
    assert any("put" in r.message and "checkpoint" in r.message.lower()
               for r in caplog.records)


# ------------------------------------------------------------------ (8) toggle
def test_toggle_retomar_analises_tolerante(tmp_path):
    caminho = tmp_path / "llm.json"
    amb = {"HF_LLM_CONFIG_PATH": str(caminho)}
    # Ausente ⇒ default LIGADO.
    assert retomar_analises_configurado(amb) is True
    # Lixo/tipo errado ⇒ LIGADO (só o booleano `false` desliga).
    for valor in ('{"retomar_analises": "sim"}', '{"retomar_analises": 0}',
                  '{"outra": 1}'):
        caminho.write_text(valor, encoding="utf-8")
        assert retomar_analises_configurado(amb) is True
    # `false` explícito DESLIGA.
    caminho.write_text('{"retomar_analises": false}', encoding="utf-8")
    assert retomar_analises_configurado(amb) is False


def test_sessao_nao_arma_duravel_com_toggle_desligado(tmp_path):
    db, dek = _cofre_tmp(tmp_path)
    sess = SessaoCofre(caminho_db=db, retomar_analises=lambda: False)
    try:
        sess._abrir_com_dek_sem_lock(dek)  # abre a sessão (repo) sem armar durável
        assert sess._saver_cofre is None
        # O proxy continua em memória (não foi armado).
        assert isinstance(criar_checkpointer()._atual(), InMemorySaver)
    finally:
        sess.fechar()


def test_sessao_arma_duravel_com_toggle_ligado(tmp_path):
    db, dek = _cofre_tmp(tmp_path)
    sess = SessaoCofre(caminho_db=db, retomar_analises=lambda: True)
    try:
        sess._abrir_com_dek_sem_lock(dek)
        assert sess._saver_cofre is not None
        assert criar_checkpointer()._atual() is sess._saver_cofre
        # Bloquear desarma e volta o proxy para memória.
        sess.bloquear()
        assert sess._saver_cofre is None
        assert isinstance(criar_checkpointer()._atual(), InMemorySaver)
    finally:
        sess.fechar()


# --------------------------------------------------------------- (9) Plano C
def test_sessao_plano_c_quando_saver_falha(tmp_path, monkeypatch, caplog):
    db, dek = _cofre_tmp(tmp_path)

    def _explode(*_a, **_k):
        raise ChaveInvalida("falha simulada ao abrir o saver do checkpoint")

    monkeypatch.setattr("sidecar.sessao.abrir_saver_cofre", _explode)
    sess = SessaoCofre(caminho_db=db, retomar_analises=lambda: True)
    try:
        with caplog.at_level(logging.WARNING, logger="helper_financeiro.sessao"):
            sess._abrir_com_dek_sem_lock(dek)
        # Sessão abriu normalmente (repo ativo), só SEM durável (Plano C).
        assert sess._saver_cofre is None
        assert sess.repositorio_ativo() is not None
        assert isinstance(criar_checkpointer()._atual(), InMemorySaver)
        assert any("mem" in r.message.lower() for r in caplog.records)
    finally:
        sess.fechar()


# ------------------------------------------ (extra) chave errada não vaza a DEK
def test_abrir_saver_com_chave_errada_nao_vaza(tmp_path):
    """Anti-vazamento (REQ-SEC-001): DEK errada ⇒ `ChaveInvalida` de mensagem
    fixa, sem o hex da chave em lugar nenhum da exceção nem da cadeia de causa."""
    db, _dek = _cofre_tmp(tmp_path)
    errada = secrets.token_bytes(32)
    with pytest.raises(ChaveInvalida) as exc:
        abrir_saver_cofre(db, errada)
    assert errada.hex() not in str(exc.value)
    assert exc.value.__context__ is None  # vínculo severado (não só suprimido)


# ------------------------------------------------------------------- (10) WAL
def test_wal_liga_no_armar_e_consolida_no_desarmar(tmp_path):
    db, dek = _cofre_tmp(tmp_path)
    saver = abrir_saver_cofre(db, dek)
    armar_checkpointer_duravel(saver)
    # Após armar: o cofre está em WAL (setup força journal_mode=WAL).
    assert saver.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    # Gera checkpoints (garante conteúdo no -wal) e escreve pelo repo em paralelo.
    fatos, mapa = montar_fatos(_perfil())
    executar_analise(fatos, mapa, CFG_FAKE, FakeProvider(), thread_id="analise:wal")
    repo = Repositorio(db, dek=dek)
    repo.salvar_estado("perfil", {"renda": {"salario_liquido": 4242.0}})
    repo.fechar()

    # Desarma: consolida o WAL (TRUNCATE) e fecha a 2ª conexão.
    desarmar_checkpointer_duravel()
    fechar_saver_cofre(saver)
    wal = db.with_name(db.name + "-wal")
    assert (not wal.exists()) or wal.stat().st_size == 0  # -wal esvaziado

    # O cofre segue íntegro e o Repositorio continua lendo/escrevendo.
    repo2 = Repositorio(db, dek=dek)
    try:
        assert repo2._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert repo2.carregar_estado("perfil")["renda"]["salario_liquido"] == 4242.0
        repo2.salvar_estado("perfil", {"renda": {"salario_liquido": 5555.0}})
        assert repo2.carregar_estado("perfil")["renda"]["salario_liquido"] == 5555.0
    finally:
        repo2.fechar()
