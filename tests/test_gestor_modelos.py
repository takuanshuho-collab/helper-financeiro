"""
Gestor de modelos GGUF (T-1702, ADR-0016 §F, REQ-F-028).

Cobre o catálogo curado (estrutura/licenças), o download com retomada via
`Range` e verificação de SHA-256 (servidor HTTP LOCAL fake — nada de rede
externa), e a persistência do `llm.json`. A resolução `env > llm.json >
ausente` do runtime é coberta em `tests/test_runtime_llm.py`.
"""
from __future__ import annotations

import hashlib
import http.server
import threading

import pytest

from sidecar import gestor_modelos as gm

CONTEUDO = b"GGUF" + bytes(range(256)) * 40  # determinístico, alguns KB
SHA_CONTEUDO = hashlib.sha256(CONTEUDO).hexdigest()


def _fabrica_handler(recebidos: list[str | None]) -> type[http.server.BaseHTTPRequestHandler]:
    """Handler que serve `CONTEUDO`, honra `Range` (206) e registra o header
    recebido em cada request — o teste de retomada confere que a 2ª chamada
    pediu só o restante (prova de que não recomeçou do zero)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — nome exigido pela stdlib
            faixa = self.headers.get("Range")
            recebidos.append(faixa)
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
            self.wfile.write(corpo)

        def log_message(self, *_a: object) -> None:
            pass

    return Handler


@pytest.fixture
def servidor_modelo():
    """Servidor HTTP local (loopback + porta efêmera) servindo `CONTEUDO`."""
    recebidos: list[str | None] = []
    servidor = http.server.HTTPServer(("127.0.0.1", 0), _fabrica_handler(recebidos))
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{porta}/modelo.gguf", recebidos
    finally:
        servidor.shutdown()
        thread.join()


def _item(url: str, *, sha256: str = SHA_CONTEUDO,
         tamanho: int = len(CONTEUDO)) -> gm.ModeloCatalogo:
    return gm.ModeloCatalogo(
        id="teste", nome="Teste", descricao="descricao teste", licenca="MIT",
        url=url, sha256=sha256, tamanho_bytes=tamanho, arquivo="teste.gguf")


# ------------------------------------------------------------------ catálogo
def test_catalogo_tem_entre_1_e_3_itens_com_licenca_comercial():
    assert 1 <= len(gm.CATALOGO) <= 3
    licencas_comerciais = {"MIT", "Apache-2.0"}
    for item in gm.CATALOGO:
        assert item.licenca in licencas_comerciais, item.id


def test_catalogo_ids_unicos_e_campos_bem_formados():
    ids = [item.id for item in gm.CATALOGO]
    assert len(ids) == len(set(ids))
    for item in gm.CATALOGO:
        assert item.url.startswith("https://")
        assert item.arquivo.endswith(".gguf")
        assert len(item.sha256) == 64
        int(item.sha256, 16)  # hex válido
        assert item.tamanho_bytes > 0


def test_item_do_catalogo_desconhecido_levanta():
    with pytest.raises(gm.CatalogoIdDesconhecido):
        gm.item_do_catalogo("modelo-que-nao-existe")


def test_hf_catalogo_teste_sobrescreve_o_catalogo_real(tmp_path):
    """`HF_CATALOGO_TESTE` é o mecanismo do E2E para baixar de um servidor
    HTTP local fake em vez do Hugging Face de verdade (REQ-NF-007: nada de
    rede externa nos testes)."""
    import json

    item_fake = {
        "id": "fake-e2e", "nome": "Fake E2E", "descricao": "só para teste",
        "licenca": "MIT", "url": "http://127.0.0.1:9/fake.gguf",
        "sha256": "0" * 64, "tamanho_bytes": 10, "arquivo": "fake.gguf",
    }
    caminho = tmp_path / "catalogo-teste.json"
    caminho.write_text(json.dumps([item_fake]), encoding="utf-8")
    ambiente = {gm.VAR_CATALOGO_TESTE: str(caminho)}

    catalogo = gm.catalogo_efetivo(ambiente)
    assert len(catalogo) == 1
    assert catalogo[0].id == "fake-e2e"
    assert gm.item_do_catalogo("fake-e2e", ambiente).nome == "Fake E2E"

    # Sem a env, o catálogo real de sempre.
    assert gm.catalogo_efetivo({}) == gm.CATALOGO


def test_listar_catalogo_com_estado_marca_ausente_sem_arquivo(tmp_path):
    ambiente = {gm.VAR_MODELOS_DIR: str(tmp_path)}
    estados = gm.listar_catalogo_com_estado(ambiente)
    assert len(estados) == len(gm.CATALOGO)
    assert all(e["estado"] == "ausente" for e in estados)


# --------------------------------------------------------------- llm.json
def test_llm_config_roundtrip(tmp_path):
    gguf = tmp_path / "modelo.gguf"
    gguf.write_bytes(b"GGUF fake")
    ambiente = {gm.VAR_LLM_CONFIG_PATH: str(tmp_path / "llm.json")}

    assert gm.modelo_ativo(ambiente) is None  # ainda sem escolha

    caminho = gm.definir_modelo_ativo(gguf, ambiente)
    assert caminho == gguf
    assert gm.modelo_ativo(ambiente) == str(gguf)
    assert (tmp_path / "llm.json").is_file()  # escrita atômica concluída


def test_definir_modelo_ativo_gguf_inexistente_levanta(tmp_path):
    ambiente = {gm.VAR_LLM_CONFIG_PATH: str(tmp_path / "llm.json")}
    with pytest.raises(gm.ModeloLocalInvalido):
        gm.definir_modelo_ativo(tmp_path / "sumido.gguf", ambiente)


def test_definir_modelo_ativo_extensao_errada_levanta(tmp_path):
    arquivo = tmp_path / "nao-e-gguf.txt"
    arquivo.write_text("oi")
    ambiente = {gm.VAR_LLM_CONFIG_PATH: str(tmp_path / "llm.json")}
    with pytest.raises(gm.ModeloLocalInvalido):
        gm.definir_modelo_ativo(arquivo, ambiente)


def test_llm_config_corrompido_vira_ausente(tmp_path):
    caminho = tmp_path / "llm.json"
    caminho.write_text("{ isso nao eh json", encoding="utf-8")
    ambiente = {gm.VAR_LLM_CONFIG_PATH: str(caminho)}
    assert gm.ler_llm_config(ambiente) == {}
    assert gm.modelo_ativo(ambiente) is None


# ---------------------------------------------------------------- download
def test_baixar_modelo_sucesso_e_idempotente(tmp_path, servidor_modelo):
    url, recebidos = servidor_modelo
    item = _item(url)
    progresso: list[tuple[int, int]] = []

    caminho = gm.baixar_modelo(item, destino_dir=tmp_path,
                               progresso=lambda b, t: progresso.append((b, t)))
    assert caminho.is_file()
    assert caminho.read_bytes() == CONTEUDO
    assert progresso[-1] == (len(CONTEUDO), len(CONTEUDO))
    assert not (tmp_path / "teste.gguf.parcial").exists()

    # 2ª chamada: já baixado e íntegro ⇒ não bate na rede de novo.
    recebidos.clear()
    caminho2 = gm.baixar_modelo(item, destino_dir=tmp_path)
    assert caminho2 == caminho
    assert recebidos == []


def test_baixar_modelo_hash_invalido_apaga_parcial(tmp_path, servidor_modelo):
    url, _ = servidor_modelo
    item = _item(url, sha256="0" * 64)
    with pytest.raises(gm.ModeloHashInvalido):
        gm.baixar_modelo(item, destino_dir=tmp_path)
    assert not (tmp_path / "teste.gguf").exists()
    assert not (tmp_path / "teste.gguf.parcial").exists()


def test_baixar_modelo_cancelado_mantem_parcial_e_retoma_via_range(
    tmp_path, servidor_modelo, monkeypatch,
):
    url, recebidos = servidor_modelo
    monkeypatch.setattr(gm, "_TAMANHO_BLOCO", 16)  # força vários blocos
    item = _item(url)

    chamadas = {"n": 0}

    def cancelar_apos_2_blocos() -> bool:
        chamadas["n"] += 1
        return chamadas["n"] > 2

    with pytest.raises(gm.ModeloDownloadCancelado):
        gm.baixar_modelo(item, destino_dir=tmp_path, cancelado=cancelar_apos_2_blocos)

    parcial = tmp_path / "teste.gguf.parcial"
    assert parcial.is_file()
    tamanho_parcial = parcial.stat().st_size
    assert 0 < tamanho_parcial < len(CONTEUDO)
    assert recebidos[0] is None  # 1ª tentativa: sem Range (do zero)

    recebidos.clear()
    caminho = gm.baixar_modelo(item, destino_dir=tmp_path)
    assert caminho.read_bytes() == CONTEUDO
    assert not parcial.exists()
    # A retomada pediu Range a partir de onde parou (prova de que não
    # recomeçou do zero).
    assert recebidos[0] == f"bytes={tamanho_parcial}-"
