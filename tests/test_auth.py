"""
Cofre local: envelope DEK/KEK, TOTP, códigos de recuperação e anti-brute-force
(ADR-0016, REQ-SEC-005/006/007) — T-1601.

Tudo offline e sem `sleep`: o relógio é injetado (`Callable[[], float]`) e o KDF
roda com parâmetros baixos (`ParametrosKdf` mínimo) só para velocidade. O
`auth.json` mora sempre em `tmp_path` via `HF_AUTH_PATH` — nunca no %APPDATA% real.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest

from sidecar.auth import (
    AguardeCofre,
    CodigoRecuperacaoInvalido,
    Cofre,
    CofreJaCadastrado,
    CofreNaoCadastrado,
    ParametrosKdf,
    SenhaFraca,
    SenhaIncorreta,
    TotpIncorreto,
    caminho_auth,
    validar_senha,
)

SENHA = "senha-super-secreta"
NOVA_SENHA = "outra-senha-igualmente-forte"

# Argon2id de custo baixo: os testes não medem segurança, só comportamento.
KDF_RAPIDO = ParametrosKdf(time_cost=1, memory_cost=8, parallelism=1, tamanho=32)


class RelogioFake:
    """Relógio manual — avança só quando o teste mandar (sem sleep real)."""

    def __init__(self, agora: float = 1_000_000.0) -> None:
        self.t = agora

    def __call__(self) -> float:
        return self.t

    def avancar(self, segundos: float) -> None:
        self.t += segundos


def _cofre(tmp_path: Path, relogio: RelogioFake | None = None) -> Cofre:
    return Cofre(tmp_path / "auth.json", agora=relogio or RelogioFake(),
                 parametros_kdf=KDF_RAPIDO)


def _totp_valido(uri: str, agora: float) -> str:
    """Gera o código TOTP correto para o instante dado a partir do provisioning URI."""
    segredo = parse_qs(urlparse(uri).query)["secret"][0]
    return pyotp.TOTP(segredo).at(int(agora))  # .at() recebe o timestamp, não o passo


# ------------------------------------------------------- caminho do auth.json
def test_hf_auth_path_tem_precedencia():
    env = {"HF_AUTH_PATH": r"C:\tmp\auth.json", "APPDATA": r"C:\Users\x\AppData\Roaming"}
    assert caminho_auth(env) == Path(r"C:\tmp\auth.json")


def test_appdata_e_o_padrao_e_espelha_o_banco():
    env = {"APPDATA": r"C:\Users\x\AppData\Roaming"}
    esperado = Path(r"C:\Users\x\AppData\Roaming") / "HelperFinanceiro" / "auth.json"
    assert caminho_auth(env) == esperado


# --------------------------------------------------------- política de senha
def test_validar_senha_curta_devolve_motivo_ptbr():
    motivo = validar_senha("curta")
    assert motivo is not None
    assert "10 caracteres" in motivo


def test_validar_senha_ok_devolve_none():
    assert validar_senha("dez-caracteres-ok") is None


def test_cadastro_recusa_senha_fraca(tmp_path):
    with pytest.raises(SenhaFraca):
        _cofre(tmp_path).cadastrar("123")


# ------------------------------------------------------------- cadastro/estado
def test_cadastro_cria_arquivo_e_emite_segredos(tmp_path):
    cofre = _cofre(tmp_path)
    assert cofre.esta_cadastrado() is False

    res = cofre.cadastrar(SENHA)
    assert cofre.esta_cadastrado() is True
    assert len(res.dek) == 32
    assert len(res.codigos_recuperacao) == 10
    assert res.totp_uri.startswith("otpauth://totp/")
    assert "Helper%20Financeiro" in res.totp_uri or "Helper Financeiro" in res.totp_uri


def test_cadastro_duplicado_e_recusado(tmp_path):
    cofre = _cofre(tmp_path)
    cofre.cadastrar(SENHA)
    with pytest.raises(CofreJaCadastrado):
        cofre.cadastrar(SENHA)


def test_operacoes_sem_cadastro(tmp_path):
    cofre = _cofre(tmp_path)
    with pytest.raises(CofreNaoCadastrado):
        cofre.desbloquear(SENHA, "000000")
    assert cofre.segundos_de_espera() == 0.0


# ------------------------------------------------- roundtrip cadastro→desbloqueio
def test_roundtrip_devolve_a_mesma_dek(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)
    dek = cofre.desbloquear(SENHA, _totp_valido(res.totp_uri, relogio.t))
    assert dek == res.dek


def test_desbloqueio_sobrevive_a_nova_instancia(tmp_path):
    # Uma "nova sessão" (outra instância sobre o mesmo arquivo) abre o cofre.
    relogio = RelogioFake()
    res = _cofre(tmp_path, relogio).cadastrar(SENHA)
    outra = _cofre(tmp_path, relogio)
    dek = outra.desbloquear(SENHA, _totp_valido(res.totp_uri, relogio.t))
    assert dek == res.dek


def test_senha_errada_falha(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)
    with pytest.raises(SenhaIncorreta):
        cofre.desbloquear("senha-errada-porem-longa", _totp_valido(res.totp_uri, relogio.t))


def test_totp_errado_falha(tmp_path):
    cofre = _cofre(tmp_path)
    cofre.cadastrar(SENHA)
    with pytest.raises(TotpIncorreto):
        cofre.desbloquear(SENHA, "000000")


# --------------------------------------------------------- TOTP anti-replay
def test_totp_nao_pode_ser_reusado_no_mesmo_passo(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)
    codigo = _totp_valido(res.totp_uri, relogio.t)

    cofre.desbloquear(SENHA, codigo)  # 1º uso: ok
    with pytest.raises(TotpIncorreto):
        cofre.desbloquear(SENHA, codigo)  # replay no mesmo passo: recusado


def test_totp_do_proximo_passo_volta_a_valer(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)
    cofre.desbloquear(SENHA, _totp_valido(res.totp_uri, relogio.t))

    relogio.avancar(60)  # dois passos adiante: novo código é aceito
    dek = cofre.desbloquear(SENHA, _totp_valido(res.totp_uri, relogio.t))
    assert dek == res.dek


# ----------------------------------------------------- códigos de recuperação
def test_recuperacao_devolve_a_mesma_dek_e_consome_o_codigo(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)
    codigo = res.codigos_recuperacao[0]

    dek = cofre.recuperar(codigo, NOVA_SENHA)
    assert dek == res.dek

    # Uso único: o mesmo código não serve de novo.
    with pytest.raises(CodigoRecuperacaoInvalido):
        cofre.recuperar(codigo, "mais-uma-senha-longa")


def test_recuperacao_redefine_a_senha(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)
    cofre.recuperar(res.codigos_recuperacao[0], NOVA_SENHA)

    # A nova senha abre; a antiga não.
    dek = cofre.desbloquear(NOVA_SENHA, _totp_valido(res.totp_uri, relogio.t))
    assert dek == res.dek
    with pytest.raises(SenhaIncorreta):
        cofre.desbloquear(SENHA, _totp_valido(res.totp_uri, relogio.t + 60))


def test_recuperacao_normaliza_caixa_e_hifens(tmp_path):
    cofre = _cofre(tmp_path)
    res = cofre.cadastrar(SENHA)
    baguncado = res.codigos_recuperacao[0].lower().replace("-", " ")
    dek = cofre.recuperar(baguncado, NOVA_SENHA)
    assert dek == res.dek


def test_recuperacao_com_codigo_desconhecido_falha(tmp_path):
    cofre = _cofre(tmp_path)
    cofre.cadastrar(SENHA)
    with pytest.raises(CodigoRecuperacaoInvalido):
        cofre.recuperar("AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GG", NOVA_SENHA)


def test_recuperacao_recusa_senha_fraca(tmp_path):
    cofre = _cofre(tmp_path)
    res = cofre.cadastrar(SENHA)
    with pytest.raises(SenhaFraca):
        cofre.recuperar(res.codigos_recuperacao[0], "123")


def test_recuperacao_nao_invalida_os_outros_codigos(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)
    cofre.recuperar(res.codigos_recuperacao[0], NOVA_SENHA)
    # Um código diferente ainda abre (e devolve a mesma DEK).
    dek = cofre.recuperar(res.codigos_recuperacao[1], "terceira-senha-longa")
    assert dek == res.dek


# ------------------------------------------------------------- troca de senha
def test_trocar_senha_mantem_a_dek(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)

    cofre.trocar_senha(SENHA, _totp_valido(res.totp_uri, relogio.t), NOVA_SENHA)

    relogio.avancar(60)  # novo passo TOTP p/ não bater no anti-replay
    dek = cofre.desbloquear(NOVA_SENHA, _totp_valido(res.totp_uri, relogio.t))
    assert dek == res.dek


def test_trocar_senha_exige_totp_valido(tmp_path):
    cofre = _cofre(tmp_path)
    cofre.cadastrar(SENHA)
    with pytest.raises(TotpIncorreto):
        cofre.trocar_senha(SENHA, "000000", NOVA_SENHA)


def test_trocar_senha_recusa_nova_senha_fraca(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)
    with pytest.raises(SenhaFraca):
        cofre.trocar_senha(SENHA, _totp_valido(res.totp_uri, relogio.t), "123")


# -------------------------------------------------------- anti-brute-force
def test_atraso_exponencial_cresce_e_zera_no_sucesso(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)

    # 3 falhas consecutivas: só a partir da 3ª começa o atraso.
    for _ in range(3):
        with pytest.raises(SenhaIncorreta):
            cofre.desbloquear("senha-errada-porem-longa", "000000")

    # Após a 3ª falha: atraso de 2**0 = 1 s. A tentativa imediata é barrada.
    with pytest.raises(AguardeCofre) as exc:
        cofre.desbloquear(SENHA, _totp_valido(res.totp_uri, relogio.t))
    assert 0 < exc.value.segundos <= 1.0

    # Passado o 1 s, a senha certa abre e ZERA o contador.
    relogio.avancar(1.0)
    dek = cofre.desbloquear(SENHA, _totp_valido(res.totp_uri, relogio.t))
    assert dek == res.dek
    assert cofre.segundos_de_espera() == 0.0


def test_atraso_dobra_a_cada_falha(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    cofre.cadastrar(SENHA)

    for _ in range(3):
        with pytest.raises(SenhaIncorreta):
            cofre.desbloquear("senha-errada-porem-longa", "000000")
    assert cofre.segundos_de_espera() == pytest.approx(1.0, abs=1e-6)  # 2**0

    # A 4ª falha (a AguardeCofre não conta) exige avançar o relógio primeiro.
    relogio.avancar(1.0)
    with pytest.raises(SenhaIncorreta):
        cofre.desbloquear("senha-errada-porem-longa", "000000")
    assert cofre.segundos_de_espera() == pytest.approx(2.0, abs=1e-6)  # 2**1


def test_espera_nao_conta_falha_extra(tmp_path):
    # Bater na porta enquanto o atraso corre não deve aumentar o contador.
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    cofre.cadastrar(SENHA)
    for _ in range(3):
        with pytest.raises(SenhaIncorreta):
            cofre.desbloquear("senha-errada-porem-longa", "000000")

    for _ in range(5):
        with pytest.raises(AguardeCofre):
            cofre.desbloquear(SENHA, "000000")
    # Continua sendo o atraso da 3ª falha (1 s), não cresceu.
    assert cofre.segundos_de_espera() == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------- persistência dos parâmetros KDF
def test_parametros_kdf_sao_persistidos_e_relidos(tmp_path):
    relogio = RelogioFake()
    cofre = _cofre(tmp_path, relogio)
    res = cofre.cadastrar(SENHA)

    dados = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert dados["kdf"]["time_cost"] == KDF_RAPIDO.time_cost
    assert dados["kdf"]["memory_cost"] == KDF_RAPIDO.memory_cost
    assert dados["kdf"]["parallelism"] == KDF_RAPIDO.parallelism

    # Uma instância NOVA (sem os parâmetros injetados no construtor de origem)
    # ainda abre, porque a derivação lê os parâmetros gravados no cofre.
    outra = Cofre(tmp_path / "auth.json", agora=relogio)  # KDF padrão no construtor
    dek = outra.desbloquear(SENHA, _totp_valido(res.totp_uri, relogio.t))
    assert dek == res.dek


# -------------------------------------------- auth.json não vaza segredos
def test_auth_json_nao_contem_dek_nem_segredo_totp_em_claro(tmp_path):
    cofre = _cofre(tmp_path)
    res = cofre.cadastrar(SENHA)

    caminho = tmp_path / "auth.json"
    cru = caminho.read_bytes()
    segredo_totp = parse_qs(urlparse(res.totp_uri).query)["secret"][0]

    # A DEK crua (bytes e base64) e o segredo TOTP (base32) não estão no arquivo.
    assert res.dek not in cru
    assert base64.b64encode(res.dek) not in cru
    assert segredo_totp.encode("ascii") not in cru
    # Nem os códigos de recuperação (só o hash e o envelope moram lá).
    for codigo in res.codigos_recuperacao:
        assert codigo.encode("ascii") not in cru


# --------------------------------------------------------------- escrita atômica
def test_escrita_e_atomica_sem_temporarios_residuais(tmp_path):
    cofre = _cofre(tmp_path)
    cofre.cadastrar(SENHA)
    # Depois de gravar, só o auth.json fica — nenhum ".tmp" sobra.
    arquivos = sorted(p.name for p in tmp_path.iterdir())
    assert arquivos == ["auth.json"]


def test_versao_de_formato_desconhecida_e_recusada(tmp_path):
    cofre = _cofre(tmp_path)
    cofre.cadastrar(SENHA)
    caminho = tmp_path / "auth.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["versao"] = 999
    caminho.write_text(json.dumps(dados), encoding="utf-8")

    with pytest.raises(Exception, match="formato desconhecido"):
        _cofre(tmp_path).desbloquear(SENHA, "000000")
