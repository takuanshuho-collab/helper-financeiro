"""
Primitivas do cofre local — login com senha mestra + MFA e cifra em repouso
(ADR-0016 §A/C/D; REQ-SEC-005/006/007) — T-1601.

Este módulo é **puro**: nada de FastAPI, nada de SQLCipher. Só a criptografia do
cofre e os metadados de autenticação. Quem abre o banco cifrado com a DEK é o
`sidecar/persistencia.py` (T-1602); quem expõe o estado 423/desbloqueado por
HTTP é o `sidecar/app.py` (T-1603); quem desenha o QR é a GUI (T-1604).

## Modelo de chaves (envelope DEK/KEK)

- A **DEK** (data encryption key, 32 bytes de `secrets`) é a chave que um dia vai
  no `PRAGMA key` do SQLCipher. Ela **nunca** vai a disco em claro: é guardada
  sempre **envelopada** (AES-GCM).
- A **KEK** deriva da senha mestra via **Argon2id** (`argon2-cffi`). Os
  parâmetros do KDF (`ParametrosKdf`) são **registrados nos metadados** — assim
  dá para recalibrar o custo no futuro sem quebrar cofres antigos — e são
  **injetáveis** (os testes usam custo baixo para rodar rápido). A KEK envelopa
  a DEK. Trocar a senha só re-envelopa a DEK; **não** recifra os dados.
- Cada **código de recuperação** (10, de uso único, exibidos só no cadastro)
  também envelopa uma cópia da DEK, com chave derivada do próprio código via
  **HKDF-SHA256**. O código em si é guardado apenas como **SHA-256** (verificação
  em tempo constante). Consumir um código mantém o hash e **invalida o envelope**.
  Perder a senha não perde os dados enquanto restar um código; perder senha
  **e** códigos perde os dados — **não há backdoor**, por design (REQ-SEC-007).

## Honestidade do modelo de ameaça

A *cifra* deriva exclusivamente da **senha** (via KEK). O **TOTP** protege a
*autenticação* (o uso do app), não adiciona entropia à chave — por isso o
segredo TOTP é guardado **cifrado pela DEK** e só se confere DEPOIS que a senha
abre a DEK. Consequência aceita e explícita na ADR: a senha é o 1º fator (de
cifra); o TOTP é o 2º fator (de autenticação, um gate). O cofre protege contra
acesso ao **disco** (roubo, backup, outra conta na máquina); malware rodando na
sessão do usuário com o cofre aberto está fora do escopo — como em qualquer
gerenciador de senhas desktop.

Comparações sensíveis usam `hmac.compare_digest`/`secrets.compare_digest` (tempo
constante — mesmo racional do token de sessão em `security.py`, T-1003).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pyotp
from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Versão do formato do auth.json — sobe se o layout dos metadados mudar.
FORMATO_AUTH = 1

# Emissor exibido no app autenticador (o `name` do provisioning URI é a conta).
EMISSOR_TOTP = "Helper Financeiro"

# Política de senha: mínimo de caracteres (sem exigir classes — decisão da ADR).
TAMANHO_MINIMO_SENHA = 10

# Envelope AES-GCM: nonce de 12 bytes, aleatório e novo a cada cifragem, guardado
# junto ao ciphertext. Nunca reusar nonce (repetição quebra a garantia do GCM).
_TAM_NONCE = 12
# Sais aleatórios (Argon2id e HKDF dos códigos): 16 bytes.
_TAM_SAL = 16
# Entropia de cada código de recuperação: 16 bytes (alta o bastante para o hash
# bastar como verificação — sem KDF lento no caminho da recuperação).
_TAM_CODIGO = 16
# Quantidade de códigos de recuperação emitidos no cadastro.
_QTD_CODIGOS = 10
# Anti-brute-force: só a partir da 3ª falha começa o atraso; teto de 5 min.
_FALHAS_ANTES_DO_ATRASO = 3
_ATRASO_MAXIMO_S = 300


# --------------------------------------------------------------- exceções
class ErroCofre(Exception):
    """Base de todas as falhas tipadas do cofre."""


class CofreJaCadastrado(ErroCofre):
    """Tentativa de cadastrar sobre um cofre que já existe."""


class CofreNaoCadastrado(ErroCofre):
    """Operação de cofre sem cadastro prévio (auth.json ausente)."""


class SenhaFraca(ErroCofre):
    """A senha nova não cumpre a política — a mensagem é exibível ao usuário."""


class SenhaIncorreta(ErroCofre):
    """A senha mestra não abre a DEK (1º fator)."""


class TotpIncorreto(ErroCofre):
    """O código TOTP não confere ou já foi usado no passo (2º fator)."""


class CodigoRecuperacaoInvalido(ErroCofre):
    """O código de recuperação não confere, é desconhecido ou já foi usado."""


class AguardeCofre(ErroCofre):
    """Anti-brute-force ativo: há `segundos` de espera até a próxima tentativa.

    O T-1603 lê `segundos` para devolver o "aguarde N s" ao cliente.
    """

    def __init__(self, segundos: float) -> None:
        self.segundos = segundos
        super().__init__(f"aguarde {segundos:.0f} s antes de tentar de novo")


# ------------------------------------------------------------- parâmetros
@dataclass(frozen=True)
class ParametrosKdf:
    """Parâmetros do Argon2id da KEK — registrados nos metadados e injetáveis.

    Padrões: `time_cost=3`, `memory_cost=65536` (64 MiB), `parallelism=4`, KEK de
    32 bytes. Os testes injetam valores baixos para rodar rápido; o cofre real
    guarda os valores usados, então recalibrar no futuro não quebra cofres antigos.
    """

    time_cost: int = 3
    memory_cost: int = 65536  # KiB → 64 MiB
    parallelism: int = 4
    tamanho: int = 32  # bytes da KEK

    def para_dict(self) -> dict:
        return {"time_cost": self.time_cost, "memory_cost": self.memory_cost,
                "parallelism": self.parallelism, "tamanho": self.tamanho}

    @classmethod
    def de_dict(cls, dados: Mapping[str, int]) -> ParametrosKdf:
        return cls(time_cost=int(dados["time_cost"]),
                   memory_cost=int(dados["memory_cost"]),
                   parallelism=int(dados["parallelism"]),
                   tamanho=int(dados["tamanho"]))


@dataclass(frozen=True)
class ResultadoCadastro:
    """Retorno do cadastro — os segredos que só existem em claro AQUI.

    A DEK vai para a memória do sidecar (T-1603); os códigos de recuperação e o
    URI do TOTP são mostrados uma única vez ao usuário e nunca mais (a GUI gera o
    QR a partir do URI, T-1604).
    """

    dek: bytes
    totp_uri: str
    codigos_recuperacao: list[str] = field(default_factory=list)


# ------------------------------------------------------------- caminho
def caminho_auth(ambiente: Mapping[str, str] | None = None) -> Path:
    """Resolve o caminho do `auth.json`: `HF_AUTH_PATH` (testes) > perfil do usuário.

    Espelha `caminho_banco()` do `persistencia.py`: o arquivo fica na MESMA pasta
    do banco (`%APPDATA%\\HelperFinanceiro\\auth.json`), fora do cofre — nada ali
    é utilizável sem a senha ou um código de recuperação.
    """
    env = os.environ if ambiente is None else ambiente
    forcado = env.get("HF_AUTH_PATH", "").strip()
    if forcado:
        return Path(forcado)
    appdata = env.get("APPDATA", "").strip()
    base = Path(appdata) / "HelperFinanceiro" if appdata else Path.home() / ".helper_financeiro"
    return base / "auth.json"


# ------------------------------------------------------- política de senha
def validar_senha(senha: str) -> str | None:
    """Valida a política mínima; devolve o motivo em pt-BR (ou `None` se ok).

    Só exige comprimento mínimo — sem classes de caracteres obrigatórias (a GUI
    exibe o motivo). É a fonte única da política, usada no cadastro, na troca de
    senha e na recuperação.
    """
    if len(senha) < TAMANHO_MINIMO_SENHA:
        return f"A senha precisa de pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
    return None


# ------------------------------------------------------- helpers de cifra
def _b64e(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


def _b64d(texto: str) -> bytes:
    return base64.b64decode(texto.encode("ascii"))


def _derivar_kek(senha: str, sal: bytes, params: ParametrosKdf) -> bytes:
    """KEK = Argon2id(senha, sal) com os parâmetros registrados (REQ-SEC-006)."""
    return hash_secret_raw(
        secret=senha.encode("utf-8"),
        salt=sal,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost,
        parallelism=params.parallelism,
        hash_len=params.tamanho,
        type=Type.ID,
    )


def _derivar_chave_codigo(codigo_bruto: bytes, sal: bytes) -> bytes:
    """Chave de envelope de um código de recuperação via HKDF-SHA256.

    O código já tem 16 bytes de entropia, então HKDF (rápido) basta — não é
    preciso um KDF lento como no caminho da senha.
    """
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sal,
                info=b"hf-recuperacao").derive(codigo_bruto)


def _envelopar(chave: bytes, dados: bytes) -> bytes:
    """AES-GCM: nonce novo por cifragem, prefixado ao ciphertext."""
    nonce = secrets.token_bytes(_TAM_NONCE)
    return nonce + AESGCM(chave).encrypt(nonce, dados, None)


def _desenvelopar(chave: bytes, blob: bytes) -> bytes:
    """Inverso de `_envelopar`; levanta `InvalidTag` se a chave estiver errada."""
    nonce, ciphertext = blob[:_TAM_NONCE], blob[_TAM_NONCE:]
    return AESGCM(chave).decrypt(nonce, ciphertext, None)


# ---------------------------------------------------- códigos de recuperação
def _formatar_codigo(codigo_bruto: bytes) -> str:
    """Bytes → base32 sem padding, agrupado em blocos de 4 para legibilidade."""
    texto = base64.b32encode(codigo_bruto).decode("ascii").rstrip("=")
    return "-".join(texto[i:i + 4] for i in range(0, len(texto), 4))


def _normalizar_codigo(codigo: str) -> bytes | None:
    """Normaliza (caixa e hífens ignorados) e decodifica; `None` se malformado."""
    limpo = re.sub(r"[\s-]", "", codigo).upper()
    resto = len(limpo) % 8
    if resto:  # base32 exige múltiplo de 8 — repõe o padding que tiramos
        limpo += "=" * (8 - resto)
    try:
        return base64.b32decode(limpo)
    except (binascii.Error, ValueError):
        return None


# --------------------------------------------------------------- TOTP
def _passo_totp(agora: float) -> int:
    """Índice do passo TOTP (janela de 30 s) para o instante dado."""
    return int(agora // 30)


def _verificar_totp(segredo: str, codigo: str, agora: float,
                    ultimo_passo: int | None) -> int | None:
    """Confere o TOTP em janela ±1 e devolve o passo aceito (ou `None`).

    Anti-replay: recusa qualquer passo <= ao último aceito — assim o mesmo código
    não pode ser reusado no mesmo passo (nem um passo já consumido volta a valer).
    """
    totp = pyotp.TOTP(segredo)
    codigo = re.sub(r"\s", "", codigo)
    passo_atual = _passo_totp(agora)
    for delta in (-1, 0, 1):
        passo = passo_atual + delta
        # compare_digest: não vaza pelo relógio quantos dígitos batem.
        if hmac.compare_digest(totp.generate_otp(passo), codigo):
            if ultimo_passo is not None and passo <= ultimo_passo:
                return None  # replay do mesmo (ou de um passo já usado)
            return passo
    return None


# --------------------------------------------------------------- cofre
class Cofre:
    """Fachada das primitivas do cofre sobre um `auth.json`.

    Relógio (`agora`) e parâmetros do KDF são injetáveis para os testes rodarem
    sem `sleep` e sem pagar o custo do Argon2id de produção.
    """

    def __init__(self, caminho: Path | None = None, *,
                 agora: Callable[[], float] = time.time,
                 parametros_kdf: ParametrosKdf | None = None) -> None:
        self._caminho = caminho if caminho is not None else caminho_auth()
        self._agora = agora
        # Parâmetros usados em NOVAS derivações (cadastro, troca, recuperação).
        # O desbloqueio sempre lê os parâmetros gravados no próprio cofre.
        self._params = parametros_kdf if parametros_kdf is not None else ParametrosKdf()

    @property
    def caminho(self) -> Path:
        return self._caminho

    # ---------------------------------------------------- metadados (I/O)
    def esta_cadastrado(self) -> bool:
        return self._caminho.exists()

    def _carregar(self) -> dict:
        if not self._caminho.exists():
            raise CofreNaoCadastrado("Cofre ainda não cadastrado.")
        dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        if int(dados.get("versao", 0)) != FORMATO_AUTH:
            raise ErroCofre(
                f"auth.json em formato desconhecido (versão {dados.get('versao')})."
            )
        return dados

    def _salvar(self, dados: dict) -> None:
        """Escrita atômica: grava num temporário e faz `os.replace` (nunca deixa
        um auth.json truncado se o processo morrer no meio)."""
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        texto = json.dumps(dados, ensure_ascii=False, indent=2)
        temporario = self._caminho.with_name(
            f"{self._caminho.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        )
        temporario.write_text(texto, encoding="utf-8")
        os.replace(temporario, self._caminho)

    # ---------------------------------------------------- anti-brute-force
    def _espera_pendente(self, dados: dict) -> float:
        """Segundos que faltam para a próxima tentativa ser aceita (0 = livre).

        A partir da 3ª falha consecutiva: atraso `min(2**(falhas-3), 300)` s a
        contar da última falha. Sucesso zera o contador (ver `_zerar_falhas`).
        """
        falhas = int(dados.get("falhas", 0))
        if falhas < _FALHAS_ANTES_DO_ATRASO:
            return 0.0
        ultima = dados.get("ultima_falha")
        if ultima is None:
            return 0.0
        atraso = min(2 ** (falhas - _FALHAS_ANTES_DO_ATRASO), _ATRASO_MAXIMO_S)
        restante = (float(ultima) + atraso) - self._agora()
        return max(0.0, restante)

    def segundos_de_espera(self) -> float:
        """Consulta pública do atraso pendente (0 se cofre livre ou sem cadastro)."""
        try:
            dados = self._carregar()
        except CofreNaoCadastrado:
            return 0.0
        return self._espera_pendente(dados)

    def _registrar_falha(self, dados: dict) -> None:
        dados["falhas"] = int(dados.get("falhas", 0)) + 1
        dados["ultima_falha"] = self._agora()
        self._salvar(dados)

    @staticmethod
    def _zerar_falhas(dados: dict) -> None:
        dados["falhas"] = 0
        dados["ultima_falha"] = None

    def _exigir_sem_espera(self, dados: dict) -> None:
        espera = self._espera_pendente(dados)
        if espera > 0:
            raise AguardeCofre(espera)

    # --------------------------------------------------------- cadastro
    def cadastrar(self, senha: str, *, nome_conta: str = "cofre local") -> ResultadoCadastro:
        """Cria o cofre: gera DEK, envelopa pela KEK, emite TOTP e 10 códigos.

        Levanta `CofreJaCadastrado` se já houver cofre e `SenhaFraca` se a senha
        não cumprir a política. Os segredos em claro (DEK, URI do TOTP, códigos)
        saem SÓ neste retorno.
        """
        if self.esta_cadastrado():
            raise CofreJaCadastrado("Já existe um cofre neste perfil.")
        if motivo := validar_senha(senha):
            raise SenhaFraca(motivo)

        dek = secrets.token_bytes(32)
        sal = secrets.token_bytes(_TAM_SAL)
        kek = _derivar_kek(senha, sal, self._params)

        segredo_totp = pyotp.random_base32()
        codigos, recuperacao = self._gerar_codigos(dek)

        dados = {
            "versao": FORMATO_AUTH,
            "kdf": {**self._params.para_dict(), "sal": _b64e(sal)},
            "dek_envelope": _b64e(_envelopar(kek, dek)),
            # Segredo TOTP cifrado PELA DEK (não pela KEK): só se lê após a senha
            # abrir a DEK — o TOTP autentica, não cifra (ver docstring do módulo).
            "totp_envelope": _b64e(_envelopar(dek, segredo_totp.encode("ascii"))),
            "totp_ultimo_passo": None,
            "recuperacao": recuperacao,
            "falhas": 0,
            "ultima_falha": None,
        }
        self._salvar(dados)

        uri = pyotp.TOTP(segredo_totp).provisioning_uri(
            name=nome_conta, issuer_name=EMISSOR_TOTP)
        return ResultadoCadastro(dek=dek, totp_uri=uri, codigos_recuperacao=codigos)

    def _gerar_codigos(self, dek: bytes) -> tuple[list[str], list[dict]]:
        """Emite os códigos em claro e os registros a persistir (hash + envelope)."""
        codigos: list[str] = []
        registros: list[dict] = []
        for _ in range(_QTD_CODIGOS):
            bruto = secrets.token_bytes(_TAM_CODIGO)
            sal = secrets.token_bytes(_TAM_SAL)
            chave = _derivar_chave_codigo(bruto, sal)
            registros.append({
                "sal": _b64e(sal),
                "hash": _b64e(hashlib.sha256(bruto).digest()),
                "envelope": _b64e(_envelopar(chave, dek)),
                "usado": False,
            })
            codigos.append(_formatar_codigo(bruto))
        return codigos, registros

    # ------------------------------------------------------- desbloqueio
    def desbloquear(self, senha: str, codigo_totp: str) -> bytes:
        """Abre o cofre com senha + TOTP e devolve a DEK.

        Sujeito ao anti-brute-force (`AguardeCofre`). Levanta `SenhaIncorreta`
        (1º fator) ou `TotpIncorreto` (2º fator); ambos contam como falha. Sucesso
        zera o contador e registra o passo TOTP aceito (anti-replay).
        """
        dados = self._carregar()
        self._exigir_sem_espera(dados)

        params = ParametrosKdf.de_dict(dados["kdf"])
        kek = _derivar_kek(senha, _b64d(dados["kdf"]["sal"]), params)
        try:
            dek = _desenvelopar(kek, _b64d(dados["dek_envelope"]))
        except InvalidTag as e:
            self._registrar_falha(dados)
            raise SenhaIncorreta("Senha mestra incorreta.") from e

        segredo_totp = _desenvelopar(dek, _b64d(dados["totp_envelope"])).decode("ascii")
        passo = _verificar_totp(segredo_totp, codigo_totp, self._agora(),
                                dados.get("totp_ultimo_passo"))
        if passo is None:
            self._registrar_falha(dados)
            raise TotpIncorreto("Código TOTP inválido ou já utilizado.")

        dados["totp_ultimo_passo"] = passo
        self._zerar_falhas(dados)
        self._salvar(dados)
        return dek

    # -------------------------------------------------------- recuperação
    def recuperar(self, codigo_recuperacao: str, nova_senha: str) -> bytes:
        """Abre o cofre por um código de recuperação e redefine a senha.

        Devolve a DEK, **consome** o código (uso único: mantém o hash, invalida o
        envelope) e re-envelopa a DEK com a KEK da nova senha — os dados NÃO são
        recifrados. Sujeito ao anti-brute-force. `SenhaFraca` se a nova senha não
        cumprir a política; `CodigoRecuperacaoInvalido` se o código não servir.
        """
        if motivo := validar_senha(nova_senha):
            raise SenhaFraca(motivo)
        dados = self._carregar()
        self._exigir_sem_espera(dados)

        bruto = _normalizar_codigo(codigo_recuperacao)
        entrada, dek = (None, None) if bruto is None else self._resgatar_dek(dados, bruto)
        if dek is None or entrada is None:
            self._registrar_falha(dados)
            raise CodigoRecuperacaoInvalido("Código de recuperação inválido ou já usado.")

        # Consome o código: uso único (mantém o hash para o log, some com a DEK).
        entrada["usado"] = True
        entrada["envelope"] = None

        # Re-envelopa a DEK com a KEK da nova senha (sal e parâmetros novos).
        sal = secrets.token_bytes(_TAM_SAL)
        kek = _derivar_kek(nova_senha, sal, self._params)
        dados["kdf"] = {**self._params.para_dict(), "sal": _b64e(sal)}
        dados["dek_envelope"] = _b64e(_envelopar(kek, dek))
        self._zerar_falhas(dados)
        self._salvar(dados)
        return dek

    @staticmethod
    def _resgatar_dek(dados: dict, bruto: bytes) -> tuple[dict | None, bytes | None]:
        """Acha o código não-usado cujo hash bate e desenvelopa a DEK por ele."""
        alvo = hashlib.sha256(bruto).digest()
        for entrada in dados.get("recuperacao", []):
            if entrada.get("usado") or not entrada.get("envelope"):
                continue
            if not hmac.compare_digest(_b64d(entrada["hash"]), alvo):
                continue
            chave = _derivar_chave_codigo(bruto, _b64d(entrada["sal"]))
            try:
                return entrada, _desenvelopar(chave, _b64d(entrada["envelope"]))
            except InvalidTag:
                return None, None
        return None, None

    # -------------------------------------------------------- troca de senha
    def trocar_senha(self, senha_atual: str, codigo_totp: str, nova_senha: str) -> None:
        """Troca a senha mantendo a MESMA DEK (só re-envelopa; não recifra dados).

        Exige os dois fatores atuais (via `desbloquear`, que também aplica o
        anti-brute-force e o anti-replay do TOTP). `SenhaFraca` se a nova senha
        não cumprir a política.
        """
        if motivo := validar_senha(nova_senha):
            raise SenhaFraca(motivo)
        dek = self.desbloquear(senha_atual, codigo_totp)

        dados = self._carregar()  # recarrega: desbloquear já salvou (passo/falhas)
        sal = secrets.token_bytes(_TAM_SAL)
        kek = _derivar_kek(nova_senha, sal, self._params)
        dados["kdf"] = {**self._params.para_dict(), "sal": _b64e(sal)}
        dados["dek_envelope"] = _b64e(_envelopar(kek, dek))
        self._salvar(dados)
