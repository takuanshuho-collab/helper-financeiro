"""
Endpoints do gestor de modelos GGUF (T-1702, ADR-0016 §F, REQ-F-028).

Reusa o fixture `_sessao_sem_cofre` (janela de onboarding, sem cofre) e o
cabeçalho de token de `tests/test_sidecar.py` — mesmo padrão dos demais
módulos de endpoint. NENHUM teste aqui bate na rede real: o download passa
por um servidor HTTP LOCAL fake (loopback + porta efêmera).
"""
from __future__ import annotations

import hashlib
import http.server
import os
import threading
import time

from fastapi.testclient import TestClient

from sidecar import gestor_modelos as gm
from sidecar.app import app
from sidecar.security import VAR_TOKEN
from tests.test_sidecar import CABECALHO, TOKEN, _sessao_sem_cofre  # noqa: F401 — fixture reusada

cliente = TestClient(app)

CONTEUDO = b"GGUF" + bytes(range(256)) * 40
SHA_CONTEUDO = hashlib.sha256(CONTEUDO).hexdigest()


def setup_module(_module):
    os.environ[VAR_TOKEN] = TOKEN


# --------------------------------------------------------------- /llm/status
def test_llm_status_sem_token_401():
    assert cliente.get("/llm/status").status_code == 401


def test_llm_status_sem_binario_sem_modelo(monkeypatch):
    monkeypatch.delenv("HF_BASE_URL", raising=False)
    monkeypatch.setenv("HF_LLAMA_SERVER", "C:/caminho/inexistente/llama-server.exe")
    monkeypatch.delenv("HF_LLM_MODELO", raising=False)
    resp = cliente.get("/llm/status", headers=CABECALHO)
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["servidor_usuario"] is False
    assert dados["binario_presente"] is False
    assert dados["modelo_ativo"] is None
    assert dados["runtime_ativo"] is False
    assert dados["motivo_indisponivel"] == "BINARIO_AUSENTE"


def test_llm_status_modelo_ausente_com_binario_presente(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_BASE_URL", raising=False)
    binario = tmp_path / "llama-server-fake"
    binario.write_text("fake", encoding="utf-8")
    monkeypatch.setenv("HF_LLAMA_SERVER", str(binario))
    monkeypatch.delenv("HF_LLM_MODELO", raising=False)
    monkeypatch.setenv(gm.VAR_LLM_CONFIG_PATH, str(tmp_path / "llm.json"))
    dados = cliente.get("/llm/status", headers=CABECALHO).json()
    assert dados["binario_presente"] is True
    assert dados["modelo_ativo"] is None
    assert dados["motivo_indisponivel"] == "MODELO_AUSENTE"


def test_llm_status_com_hf_base_url_e_servidor_do_usuario(monkeypatch):
    monkeypatch.setenv("HF_BASE_URL", "http://localhost:11434/v1")
    dados = cliente.get("/llm/status", headers=CABECALHO).json()
    assert dados["servidor_usuario"] is True
    assert dados["base_url"] == "http://localhost:11434/v1"
    assert dados["runtime_ativo"] is False
    assert dados["motivo_indisponivel"] is None


# -------------------------------------------------------------- /llm/catalogo
def test_llm_catalogo_sem_token_401():
    assert cliente.get("/llm/catalogo").status_code == 401


def test_llm_catalogo_lista_itens_ausentes(monkeypatch, tmp_path):
    monkeypatch.setenv(gm.VAR_MODELOS_DIR, str(tmp_path))
    resp = cliente.get("/llm/catalogo", headers=CABECALHO)
    assert resp.status_code == 200
    itens = resp.json()["catalogo"]
    assert len(itens) == len(gm.CATALOGO)
    assert all(i["estado"] == "ausente" for i in itens)
    assert all(i["licenca"] in {"MIT", "Apache-2.0"} for i in itens)


# ---------------------------------------------------------------- /llm/baixar
def test_llm_baixar_id_desconhecido_404():
    resp = cliente.post("/llm/baixar", json={"catalogo_id": "nao-existe"},
                        headers=CABECALHO)
    assert resp.status_code == 404


def test_llm_baixar_status_job_desconhecido_404():
    assert cliente.get("/llm/baixar/nao-existe", headers=CABECALHO).status_code == 404


def test_llm_baixar_cancelar_job_desconhecido_404():
    assert cliente.post("/llm/baixar/nao-existe/cancelar",
                        headers=CABECALHO).status_code == 404


# ----------------------------------------- fluxo completo com servidor fake
def _fabrica_handler(atraso_por_bloco_s: float) -> type[http.server.BaseHTTPRequestHandler]:
    """`atraso_por_bloco_s > 0`: escreve a resposta em blocos pequenos com uma
    pausa entre eles — dá tempo real para o teste de cancelamento mandar o
    `POST .../cancelar` antes do download terminar (sem isso, um servidor
    local em loopback serve alguns KB rápido demais para o cliente observar)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            faixa = self.headers.get("Range")
            if faixa:
                inicio = int(faixa.split("=")[1].split("-")[0])
                corpo = CONTEUDO[inicio:]
                self.send_response(206)
                self.send_header(
                    "Content-Range", f"bytes {inicio}-{len(CONTEUDO)-1}/{len(CONTEUDO)}")
            else:
                corpo = CONTEUDO
                self.send_response(200)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            if atraso_por_bloco_s:
                for i in range(0, len(corpo), 16):
                    self.wfile.write(corpo[i:i + 16])
                    self.wfile.flush()
                    time.sleep(atraso_por_bloco_s)
            else:
                self.wfile.write(corpo)

        def log_message(self, *_a: object) -> None:
            pass

    return Handler


def _subir_servidor_fake(atraso_por_bloco_s: float = 0.0) -> tuple[http.server.HTTPServer, str]:
    servidor = http.server.HTTPServer(("127.0.0.1", 0), _fabrica_handler(atraso_por_bloco_s))
    porta = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{porta}/modelo.gguf"


def _esperar_job(job_id: str, timeout_s: float = 5.0) -> dict:
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        resp = cliente.get(f"/llm/baixar/{job_id}", headers=CABECALHO)
        dados = resp.json()
        if dados.get("status") != "baixando":
            return dados
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} não terminou a tempo")


def test_llm_baixar_fluxo_completo_e_define_modelo_ativo(monkeypatch, tmp_path):
    servidor, url = _subir_servidor_fake()
    try:
        item_fake = gm.ModeloCatalogo(
            id="teste-e2e", nome="Teste E2E", descricao="", licenca="MIT",
            url=url, sha256=SHA_CONTEUDO, tamanho_bytes=len(CONTEUDO),
            arquivo="teste-e2e.gguf")
        monkeypatch.setattr(gm, "CATALOGO", (item_fake,))
        monkeypatch.setenv(gm.VAR_MODELOS_DIR, str(tmp_path))
        monkeypatch.setenv(gm.VAR_LLM_CONFIG_PATH, str(tmp_path / "llm.json"))

        resp = cliente.post("/llm/baixar", json={"catalogo_id": item_fake.id},
                            headers=CABECALHO)
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        final = _esperar_job(job_id)
        assert final["status"] == "pronto"

        # 2ª leitura do mesmo job: já foi liberado da memória (404).
        assert cliente.get(f"/llm/baixar/{job_id}", headers=CABECALHO).status_code == 404

        caminho = tmp_path / item_fake.arquivo
        assert caminho.is_file()

        # Define como modelo ativo pelo catalogo_id (arquivo já baixado).
        resp = cliente.post("/llm/modelo", json={"catalogo_id": item_fake.id},
                            headers=CABECALHO)
        assert resp.status_code == 200
        assert resp.json()["modelo_ativo"] == str(caminho)
        assert gm.modelo_ativo({gm.VAR_LLM_CONFIG_PATH: str(tmp_path / "llm.json")}) == str(caminho)
    finally:
        servidor.shutdown()


def test_llm_baixar_cancelar_de_verdade(monkeypatch, tmp_path):
    """Cancelamento pela rota: o job termina como "cancelado", sem 500."""
    servidor, url = _subir_servidor_fake(atraso_por_bloco_s=0.01)
    try:
        item_fake = gm.ModeloCatalogo(
            id="teste-cancelar", nome="Teste Cancelar", descricao="", licenca="MIT",
            url=url, sha256=SHA_CONTEUDO, tamanho_bytes=len(CONTEUDO),
            arquivo="teste-cancelar.gguf")
        monkeypatch.setattr(gm, "CATALOGO", (item_fake,))
        monkeypatch.setattr(gm, "_TAMANHO_BLOCO", 16)  # vários blocos ⇒ dá tempo de cancelar
        monkeypatch.setenv(gm.VAR_MODELOS_DIR, str(tmp_path))

        job_id = cliente.post("/llm/baixar", json={"catalogo_id": item_fake.id},
                              headers=CABECALHO).json()["job_id"]
        resp = cliente.post(f"/llm/baixar/{job_id}/cancelar", headers=CABECALHO)
        assert resp.status_code == 200

        final = _esperar_job(job_id)
        assert final["status"] == "cancelado"
    finally:
        servidor.shutdown()


def _esperar_download_terminal_em_memoria(job_id: str, timeout_s: float = 5.0) -> None:
    """Espera o download virar terminal olhando `_JOBS_DOWNLOAD` DIRETO — sem o
    poll de `/llm/baixar/{id}`, que apagaria o job na leitura final (queremos o
    job terminal ainda preso para exercitar o TTL)."""
    from sidecar import app as app_mod

    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        with app_mod._JOBS_DOWNLOAD_LOCK:
            job = app_mod._JOBS_DOWNLOAD.get(job_id)
            if job is not None and job["status"] != "baixando":
                return
        time.sleep(0.02)
    raise AssertionError("download não virou terminal no tempo do teste")


def test_llm_download_terminal_expira_por_ttl(monkeypatch, tmp_path):
    """C-08: um download concluído mas nunca lido em `/llm/baixar/{id}` (a tela
    só polla o catálogo) é varrido no próximo acesso assim que passa o TTL — o
    `threading.Event` sai junto. Antes: crescia para sempre."""
    from sidecar import app as app_mod

    reloginho = {"t": 5_000.0}
    monkeypatch.setattr(app_mod, "_relogio_jobs", lambda: reloginho["t"])

    servidor, url = _subir_servidor_fake()
    try:
        item_fake = gm.ModeloCatalogo(
            id="teste-ttl", nome="Teste TTL", descricao="", licenca="MIT",
            url=url, sha256=SHA_CONTEUDO, tamanho_bytes=len(CONTEUDO),
            arquivo="teste-ttl.gguf")
        monkeypatch.setattr(gm, "CATALOGO", (item_fake,))
        monkeypatch.setenv(gm.VAR_MODELOS_DIR, str(tmp_path))

        job_id = cliente.post("/llm/baixar", json={"catalogo_id": item_fake.id},
                              headers=CABECALHO).json()["job_id"]
        _esperar_download_terminal_em_memoria(job_id)
        with app_mod._JOBS_DOWNLOAD_LOCK:
            assert job_id in app_mod._JOBS_DOWNLOAD  # terminal, nunca lido no poll

        # Passa o TTL; o poll do catálogo (o que a tela realmente faz) coleta.
        reloginho["t"] += app_mod._TTL_JOBS_S + 1.0
        assert cliente.get("/llm/catalogo", headers=CABECALHO).status_code == 200
        with app_mod._JOBS_DOWNLOAD_LOCK:
            assert job_id not in app_mod._JOBS_DOWNLOAD
            assert job_id not in app_mod._JOBS_DOWNLOAD_FIM
            assert job_id not in app_mod._CANCELAMENTOS_DOWNLOAD
    finally:
        servidor.shutdown()


def test_llm_baixar_duplicado_devolve_o_mesmo_job(monkeypatch, tmp_path):
    """2º POST para o MESMO modelo com job em curso devolve o job existente
    (idempotente): dois jobs concorrentes escreveriam no mesmo `.parcial` e
    corromperiam o download — a GUI desabilita o botão, mas o contrato da API
    não pode depender disso (decisão da revisão do T-1702)."""
    servidor, url = _subir_servidor_fake(atraso_por_bloco_s=0.01)
    try:
        item_fake = gm.ModeloCatalogo(
            id="teste-duplo", nome="Teste Duplo", descricao="", licenca="MIT",
            url=url, sha256=SHA_CONTEUDO, tamanho_bytes=len(CONTEUDO),
            arquivo="teste-duplo.gguf")
        monkeypatch.setattr(gm, "CATALOGO", (item_fake,))
        monkeypatch.setattr(gm, "_TAMANHO_BLOCO", 16)  # janela p/ o 2º POST
        monkeypatch.setenv(gm.VAR_MODELOS_DIR, str(tmp_path))

        job_1 = cliente.post("/llm/baixar", json={"catalogo_id": item_fake.id},
                             headers=CABECALHO).json()["job_id"]
        job_2 = cliente.post("/llm/baixar", json={"catalogo_id": item_fake.id},
                             headers=CABECALHO).json()["job_id"]
        assert job_2 == job_1

        # Prazo maior que o padrão: o servidor fake atrasa DE PROPÓSITO a cada
        # bloco de 16 bytes (é o que abre a janela para o 2º POST acima).
        final = _esperar_job(job_1, timeout_s=30.0)
        assert final["status"] == "pronto"
    finally:
        servidor.shutdown()


def test_llm_modelo_local_gguf_inexistente_422():
    resp = cliente.post("/llm/modelo", json={"caminho": "C:/nao-existe/modelo.gguf"},
                        headers=CABECALHO)
    assert resp.status_code == 422


def test_llm_modelo_sem_nenhum_parametro_422():
    assert cliente.post("/llm/modelo", json={}, headers=CABECALHO).status_code == 422


def test_llm_modelo_ambos_parametros_422():
    resp = cliente.post("/llm/modelo",
                        json={"catalogo_id": "x", "caminho": "y"}, headers=CABECALHO)
    assert resp.status_code == 422


def test_llm_modelo_local_valido_define_ativo(monkeypatch, tmp_path):
    monkeypatch.setenv(gm.VAR_LLM_CONFIG_PATH, str(tmp_path / "llm.json"))
    gguf = tmp_path / "meu-modelo.gguf"
    gguf.write_bytes(b"GGUF fake")
    resp = cliente.post("/llm/modelo", json={"caminho": str(gguf)}, headers=CABECALHO)
    assert resp.status_code == 200
    assert resp.json()["modelo_ativo"] == str(gguf)
