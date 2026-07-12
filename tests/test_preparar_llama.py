"""Preparação do binário `llama-server` para o empacotamento (T-1703, ADR-0016 §E).

Gate A (offline): SEM baixar nada da internet. Um zip FALSO (montado em memória,
com o mesmo formato do release do llama.cpp: `llama-server.exe` + DLLs + lixo a
ignorar) é servido por um `abrir_url` injetado. Cobre extração seletiva,
verificação de tamanho/SHA-256, idempotência e os erros que abortam o build.
"""
from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from scripts import preparar_llama as pl
from scripts.preparar_llama import (
    ASSETS,
    NOME_BINARIO,
    AssetLlama,
    ErroPrepararLlama,
    diretorio_llama,
    preparar,
)


def _montar_zip_falso() -> bytes:
    """Zip com o formato do release: o binário do servidor, DLLs de runtime e
    arquivos que NÃO devem ser extraídos (outro exe + licença)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("llama-server.exe", b"MZ binario servidor falso")
        z.writestr("ggml.dll", b"dll ggml")
        z.writestr("ggml-vulkan.dll", b"dll vulkan")
        z.writestr("llama-server-impl.dll", b"dll impl do servidor")
        z.writestr("llama-cli.exe", b"outro exe que NAO entra")
        z.writestr("LICENSE.txt", b"texto de licenca que NAO entra")
    return buf.getvalue()


def _asset_para(bytes_zip: bytes, *, variante: str = "vulkan") -> AssetLlama:
    return AssetLlama(
        variante=variante,
        nome_zip="fake.zip",
        url="http://local.invalido/fake.zip",
        sha256=hashlib.sha256(bytes_zip).hexdigest(),
        tamanho_bytes=len(bytes_zip),
    )


def _abrir_url_de(bytes_zip: bytes, contador: list[int] | None = None):
    """`abrir_url` falso: devolve o zip como um stream (BytesIO é context
    manager e tem `.read(n)`)."""
    def abrir(_req, timeout=None):
        if contador is not None:
            contador[0] += 1
        return io.BytesIO(bytes_zip)
    return abrir


# ------------------------------------------------------------- extração
def test_preparar_extrai_binario_e_dlls_ignora_o_resto(tmp_path):
    z = _montar_zip_falso()
    asset = _asset_para(z)
    binario = preparar(destino=tmp_path, asset=asset, abrir_url=_abrir_url_de(z))

    assert binario == tmp_path / NOME_BINARIO
    assert binario.is_file()
    # DLLs vieram junto (runtime do servidor).
    assert (tmp_path / "ggml.dll").is_file()
    assert (tmp_path / "ggml-vulkan.dll").is_file()
    assert (tmp_path / "llama-server-impl.dll").is_file()
    # Outro executável e a licença NÃO foram extraídos.
    assert not (tmp_path / "llama-cli.exe").exists()
    assert not (tmp_path / "LICENSE.txt").exists()
    # O zip baixado é limpo após a extração.
    assert not (tmp_path / asset.nome_zip).exists()


def test_marcador_de_origem_registra_variante_e_sha(tmp_path):
    import json

    z = _montar_zip_falso()
    asset = _asset_para(z, variante="cpu")
    preparar(destino=tmp_path, asset=asset, abrir_url=_abrir_url_de(z))

    marcador = json.loads((tmp_path / ".origem.json").read_text(encoding="utf-8"))
    assert marcador["variante"] == "cpu"
    assert marcador["sha256"] == asset.sha256
    assert "llama-server.exe" in marcador["arquivos"]
    assert "llama-cli.exe" not in marcador["arquivos"]


# ------------------------------------------------------------- verificação
def test_sha_invalido_aborta_e_nao_extrai(tmp_path):
    z = _montar_zip_falso()
    asset = AssetLlama("vulkan", "fake.zip", "http://x/fake.zip",
                       sha256="0" * 64, tamanho_bytes=len(z))
    with pytest.raises(ErroPrepararLlama, match="SHA-256"):
        preparar(destino=tmp_path, asset=asset, abrir_url=_abrir_url_de(z))
    assert not (tmp_path / NOME_BINARIO).exists()
    assert not (tmp_path / "fake.zip.parcial").exists()  # parcial descartado


def test_tamanho_invalido_aborta(tmp_path):
    z = _montar_zip_falso()
    asset = AssetLlama("vulkan", "fake.zip", "http://x/fake.zip",
                       sha256=hashlib.sha256(z).hexdigest(), tamanho_bytes=len(z) + 1)
    with pytest.raises(ErroPrepararLlama, match="Tamanho"):
        preparar(destino=tmp_path, asset=asset, abrir_url=_abrir_url_de(z))
    assert not (tmp_path / NOME_BINARIO).exists()


def test_verificar_false_pula_a_checagem(tmp_path):
    """Válvula de dev: com `verificar=False`, um SHA errado não impede a
    extração (usado só localmente, nunca no build oficial)."""
    z = _montar_zip_falso()
    asset = AssetLlama("vulkan", "fake.zip", "http://x/fake.zip",
                       sha256="0" * 64, tamanho_bytes=0)
    binario = preparar(destino=tmp_path, asset=asset,
                       abrir_url=_abrir_url_de(z), verificar=False)
    assert binario.is_file()


# ------------------------------------------------------------- idempotência
def test_idempotente_nao_rebaixa(tmp_path):
    z = _montar_zip_falso()
    asset = _asset_para(z)
    contador = [0]
    abrir = _abrir_url_de(z, contador)

    preparar(destino=tmp_path, asset=asset, abrir_url=abrir)
    preparar(destino=tmp_path, asset=asset, abrir_url=abrir)  # 2ª vez: pula
    assert contador[0] == 1  # baixou uma vez só


def test_forcar_rebaixa(tmp_path):
    z = _montar_zip_falso()
    asset = _asset_para(z)
    contador = [0]
    abrir = _abrir_url_de(z, contador)

    preparar(destino=tmp_path, asset=asset, abrir_url=abrir)
    preparar(destino=tmp_path, asset=asset, abrir_url=abrir, forcar=True)
    assert contador[0] == 2


def test_origem_diferente_rebaixa(tmp_path):
    """Trocar de variante (sha diferente) invalida o marcador e rebaixa."""
    z = _montar_zip_falso()
    contador = [0]
    abrir = _abrir_url_de(z, contador)
    preparar(destino=tmp_path, asset=_asset_para(z, variante="vulkan"), abrir_url=abrir)
    # Mesmos bytes, mas outra variante ⇒ marcador não bate ⇒ rebaixa.
    preparar(destino=tmp_path, asset=_asset_para(z, variante="cpu"), abrir_url=abrir)
    assert contador[0] == 2


# ------------------------------------------------------------- validações
def test_variante_desconhecida_erro(tmp_path):
    with pytest.raises(ErroPrepararLlama, match="Variante desconhecida"):
        preparar(variante="tpu", destino=tmp_path)


def test_binario_ausente_no_zip_aborta(tmp_path):
    """Zip sem `llama-server.exe` ⇒ erro (build não segue sem o servidor)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ggml.dll", b"so dll, sem servidor")
    bytes_zip = buf.getvalue()
    asset = _asset_para(bytes_zip)
    with pytest.raises(ErroPrepararLlama, match="não foi encontrado"):
        preparar(destino=tmp_path, asset=asset, abrir_url=_abrir_url_de(bytes_zip))


# ------------------------------------------------------------- metadados reais
def test_assets_reais_pinados():
    """Sanidade das constantes travadas (as que o build oficial usa)."""
    assert set(ASSETS) == {"vulkan", "cpu"}
    assert ASSETS["vulkan"].tamanho_bytes == 32898388
    assert ASSETS["cpu"].tamanho_bytes == 18211851
    for asset in ASSETS.values():
        assert len(asset.sha256) == 64
        assert asset.url.endswith(asset.nome_zip)


def test_diretorio_llama_convencao():
    d = diretorio_llama()
    assert d.name == "llama"
    assert d.parent.name == "resources"


def test_deve_manter_seletividade():
    assert pl._deve_manter("ggml.dll")
    assert pl._deve_manter("llama-server.exe")
    assert not pl._deve_manter("llama-cli.exe")
    assert not pl._deve_manter("LICENSE.txt")
