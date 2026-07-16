"""
Runtime LLM embarcado (T-1701, ADR-0016 §E, REQ-F-027/NF-007) — Gate A (offline).

SEM binário real e SEM rede externa: um processo FALSO (um mini HTTP server em
Python que responde `/health`) exercita start/readiness/shutdown/restart em
loopback + porta efêmera. Resolução de caminho e degradação por ausência de
binário/modelo vão por monkeypatch de ambiente; relógio/health são injetáveis
para não dormir. O teste com `llama-server` de verdade é opt-in
(`HF_LLAMA_REAL=1`), no mesmo padrão do `HF_OCR_REAL`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

import pytest

from sidecar import runtime_llm as rt
from sidecar.runtime_llm import (
    ConfigRuntime,
    RuntimeLLM,
    RuntimeLLMIndisponivel,
    RuntimeLLMInvalidado,
    resolver_binario_llama,
    resolver_modelo,
)

# Script do "llama-server" FALSO: sobe um HTTP server na porta passada e responde
# 200 em /health (o suficiente para o ciclo de vida — não precisa completar chat).
_SERVIDOR_FALSO = """
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

porta = int(sys.argv[sys.argv.index("--port") + 1])


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            corpo = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", porta), H).serve_forever()
"""


@pytest.fixture
def binario_e_modelo(tmp_path):
    """Cria arquivos-placeholder para binário e modelo (só precisam existir)."""
    binario = tmp_path / "llama-server-fake"
    binario.write_text("fake", encoding="utf-8")
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"GGUF\x00placeholder")
    return binario, modelo


@pytest.fixture
def script_servidor(tmp_path):
    caminho = tmp_path / "servidor_falso.py"
    caminho.write_text(_SERVIDOR_FALSO, encoding="utf-8")
    return caminho


def _comando_fake(script):
    """montar_comando que roda o servidor FALSO na porta escolhida."""
    return lambda porta: [sys.executable, str(script), "--port", str(porta)]


# ------------------------------------------------------ resolução de caminho
def test_resolver_binario_override_existente(binario_e_modelo):
    binario, _ = binario_e_modelo
    ambiente = {rt.VAR_BINARIO: str(binario)}
    assert resolver_binario_llama(ambiente) == binario


def test_resolver_binario_override_inexistente_vira_none(tmp_path):
    ambiente = {rt.VAR_BINARIO: str(tmp_path / "nao-existe.exe")}
    assert resolver_binario_llama(ambiente) is None


def test_resolver_binario_ausente_sem_pacote(tmp_path, monkeypatch):
    # Sem binário em `<base>/resources/llama/` ⇒ indisponível (None). Aponta a
    # base para um tmp VAZIO: a partir do T-1703, `scripts/preparar_llama.py`
    # pode ter materializado o binário em resources/llama/ no próprio checkout,
    # então não dá para depender da ausência do arquivo real (o teste ficaria
    # acoplado ao estado do build).
    monkeypatch.setattr(rt, "_base_pacote", lambda: tmp_path)
    assert resolver_binario_llama({}) is None


def test_resolver_modelo_por_parametro_e_por_env(binario_e_modelo):
    _, modelo = binario_e_modelo
    assert resolver_modelo({}, modelo=modelo) == modelo
    assert resolver_modelo({rt.VAR_MODELO: str(modelo)}) == modelo


def test_resolver_modelo_ausente_ou_inexistente_vira_none(tmp_path):
    assert resolver_modelo({}) is None
    assert resolver_modelo({rt.VAR_MODELO: str(tmp_path / "sumido.gguf")}) is None


def test_resolver_modelo_cai_no_llm_json_sem_env(binario_e_modelo, tmp_path):
    """Sem `HF_LLM_MODELO`, a escolha feita na tela de Configuração da IA
    (persistida em `llm.json`, T-1702) é quem resolve o modelo."""
    from sidecar import gestor_modelos as gm

    _, modelo = binario_e_modelo
    ambiente = {gm.VAR_LLM_CONFIG_PATH: str(tmp_path / "llm.json")}
    gm.definir_modelo_ativo(modelo, ambiente)
    assert resolver_modelo(ambiente) == modelo


def test_resolver_modelo_env_precede_llm_json(binario_e_modelo, tmp_path):
    """`HF_LLM_MODELO` continua tendo precedência sobre o `llm.json`."""
    from sidecar import gestor_modelos as gm

    binario, modelo = binario_e_modelo
    outro_modelo = tmp_path / "outro.gguf"
    outro_modelo.write_bytes(b"GGUF outro")
    ambiente = {gm.VAR_LLM_CONFIG_PATH: str(tmp_path / "llm.json"),
                rt.VAR_MODELO: str(modelo)}
    gm.definir_modelo_ativo(outro_modelo, ambiente)
    assert resolver_modelo(ambiente) == modelo  # env vence, não o llm.json


# ------------------------------------------- flags/ctx resolvidos (ADR-0022)
def test_flags_padrao_auto_fit_sem_ngl():
    """Sem `HF_LLAMA_FLAGS` e sem `gpu_offload` no llm.json, o default é VAZIO —
    o auto-fit do llama.cpp decide o offload (fix de campo: `-ngl 99` explícito
    abortava no OOM da GPU-alvo)."""
    assert rt.resolver_flags({}) == ()


def test_flags_env_sobrepoe():
    ambiente = {rt.VAR_FLAGS: "-ngl 20 --threads 4"}
    assert rt.resolver_flags(ambiente) == ("-ngl", "20", "--threads", "4")


def test_flags_env_vazia_forca_cpu():
    """`HF_LLAMA_FLAGS=""` definido (mesmo vazio) zera as flags — força CPU."""
    assert rt.resolver_flags({rt.VAR_FLAGS: ""}) == ()
    assert rt.resolver_flags({rt.VAR_FLAGS: "   "}) == ()


def _ambiente_llm(tmp_path, **campos):
    """Escreve um `llm.json` isolado em `tmp_path` e devolve o ambiente-dicionário
    que aponta para ele (NUNCA lê o llm.json real do host)."""
    import json

    from sidecar import gestor_modelos as gm

    caminho = tmp_path / "llm.json"
    caminho.write_text(json.dumps(campos), encoding="utf-8")
    return {gm.VAR_LLM_CONFIG_PATH: str(caminho)}


def test_gpu_offload_cpu_vira_ngl_0(tmp_path):
    """`gpu_offload="cpu"` no llm.json ⇒ `-ngl 0` (CPU puro), inclusive no argv."""
    binario, modelo = tmp_path / "b", tmp_path / "m.gguf"
    ambiente = _ambiente_llm(tmp_path, gpu_offload="cpu")
    assert rt.resolver_flags(ambiente) == ("-ngl", "0")
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, flags_extra=("-ngl", "0")))
    assert runtime._comando_llama_server(8080)[-2:] == ["-ngl", "0"]


def test_gpu_offload_int_vira_ngl_n(tmp_path):
    """`gpu_offload=20` ⇒ `-ngl 20` (fixar 20 camadas na GPU)."""
    assert rt.resolver_flags(_ambiente_llm(tmp_path, gpu_offload=20)) == ("-ngl", "20")


def test_gpu_offload_auto_sem_ngl(tmp_path):
    """`gpu_offload="auto"` ⇒ SEM `-ngl` (auto-fit), como o default."""
    assert rt.resolver_flags(_ambiente_llm(tmp_path, gpu_offload="auto")) == ()


def test_gpu_offload_invalido_cai_no_auto(tmp_path):
    """Valores inválidos (0, texto, tipo errado) ⇒ auto-fit (sem `-ngl`)."""
    assert rt.resolver_flags(_ambiente_llm(tmp_path, gpu_offload=0)) == ()
    assert rt.resolver_flags(_ambiente_llm(tmp_path, gpu_offload="xyz")) == ()
    assert rt.resolver_flags(_ambiente_llm(tmp_path, gpu_offload=True)) == ()


def test_env_flags_vence_llm_json(tmp_path):
    """`HF_LLAMA_FLAGS` definida vence o `gpu_offload` do llm.json (contrato de
    override intacto)."""
    ambiente = _ambiente_llm(tmp_path, gpu_offload="cpu")
    ambiente[rt.VAR_FLAGS] = "-ngl 40"
    assert rt.resolver_flags(ambiente) == ("-ngl", "40")


def test_ctx_size_default_4096(tmp_path):
    """Sem `ctx_size` no llm.json ⇒ default 4096 (ADR-0022)."""
    assert rt.resolver_ctx_size({}) == 4096
    assert rt.resolver_ctx_size(_ambiente_llm(tmp_path)) == 4096


def test_ctx_size_llm_json_substitui_default(tmp_path):
    """`ctx_size` do llm.json substitui o `-c` default."""
    assert rt.resolver_ctx_size(_ambiente_llm(tmp_path, ctx_size=2048)) == 2048


def test_ctx_size_invalido_cai_no_default(tmp_path):
    """`ctx_size` inválido (texto, ≤0, tipo errado) ⇒ default 4096."""
    assert rt.resolver_ctx_size(_ambiente_llm(tmp_path, ctx_size="abc")) == 4096
    assert rt.resolver_ctx_size(_ambiente_llm(tmp_path, ctx_size=0)) == 4096
    assert rt.resolver_ctx_size(_ambiente_llm(tmp_path, ctx_size=-5)) == 4096
    assert rt.resolver_ctx_size(_ambiente_llm(tmp_path, ctx_size=True)) == 4096


def test_flags_entram_no_comando_do_servidor(binario_e_modelo):
    """As flags resolvidas viram argumentos do `llama-server` (após `-c ctx`)."""
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, flags_extra=("-ngl", "20")))
    comando = runtime._comando_llama_server(8080)
    assert comando[-2:] == ["-ngl", "20"]
    assert str(modelo) in comando


def test_comando_auto_fit_nao_tem_ngl(binario_e_modelo):
    """Com flags vazias (auto-fit), o argv NÃO carrega `-ngl` algum."""
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(ConfigRuntime(binario=binario, modelo=modelo))
    assert "-ngl" not in runtime._comando_llama_server(8080)


# ------------------------------------------------- degradação por ausência
def test_base_url_sem_binario_levanta_indisponivel(binario_e_modelo):
    _, modelo = binario_e_modelo
    runtime = RuntimeLLM(ConfigRuntime(binario=None, modelo=modelo))
    with pytest.raises(RuntimeLLMIndisponivel, match="BINARIO_AUSENTE"):
        runtime.base_url()


def test_base_url_sem_modelo_levanta_indisponivel(binario_e_modelo):
    binario, _ = binario_e_modelo
    runtime = RuntimeLLM(ConfigRuntime(binario=binario, modelo=None))
    with pytest.raises(RuntimeLLMIndisponivel, match="MODELO_AUSENTE"):
        runtime.base_url()


# --------------------------------------------- ciclo de vida (processo falso)
def test_start_readiness_e_endpoint(binario_e_modelo, script_servidor):
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=10.0),
        montar_comando=_comando_fake(script_servidor),
    )
    try:
        base = runtime.base_url()
        assert base.startswith("http://127.0.0.1:")
        assert base.endswith("/v1")
        assert runtime.ativo()
        # Idempotente: já ativo, não sobe outro processo (mesmo endpoint).
        assert runtime.base_url() == base
    finally:
        runtime.encerrar()


def test_shutdown_encerra_processo(binario_e_modelo, script_servidor):
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=10.0),
        montar_comando=_comando_fake(script_servidor),
    )
    runtime.base_url()
    assert runtime.ativo()
    runtime.encerrar()
    assert not runtime.ativo()
    runtime.encerrar()  # idempotente


def test_restart_sob_demanda_apos_morte(binario_e_modelo, script_servidor):
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=10.0),
        montar_comando=_comando_fake(script_servidor),
    )
    try:
        primeira = runtime.base_url()
        # Simula morte do processo por fora (crash do servidor).
        assert runtime._proc is not None
        runtime._proc.kill()
        runtime._proc.wait()
        assert not runtime.ativo()
        # A próxima necessidade reinicia sob demanda.
        segunda = runtime.base_url()
        assert runtime.ativo()
        assert segunda.startswith("http://127.0.0.1:")
        # Portas efêmeras: reinício quase sempre pega outra porta (não exigimos igual).
        assert isinstance(primeira, str)
    finally:
        runtime.encerrar()


def test_health_timeout_encerra_e_degrada(binario_e_modelo):
    """Servidor que nunca fica saudável ⇒ RuntimeLLMIndisponivel, sem dormir de
    verdade (relógio/health injetados)."""
    binario, modelo = binario_e_modelo
    relogio = {"t": 0.0}

    def agora() -> float:
        relogio["t"] += 0.5
        return relogio["t"]

    # Processo vivo, mas que NÃO abre porta nenhuma (dorme): /health nunca sobe.
    def comando_sem_health(porta):
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=1.0),
        montar_comando=comando_sem_health,
        agora=agora,
        dormir=lambda _s: None,
        verificar_saude=lambda _url: False,
    )
    with pytest.raises(RuntimeLLMIndisponivel, match="HEALTH_TIMEOUT"):
        runtime.base_url()
    # Falha limpa: o processo não fica pendurado.
    assert not runtime.ativo()


# ------------------------------------- kill forçado no shutdown (C-18)
class _PopenQueIgnoraTerminate:
    """Fake de `Popen` que NÃO morre no `terminate()` — força o ramo
    `TimeoutExpired → kill()` de `_matar_direto` (descoberto por
    teste antes desta task, C-18). Cross-platform: no Windows `terminate()` real
    é TerminateProcess (mata na hora) e não exercitaria este caminho."""

    def __init__(self) -> None:
        self.terminado = False
        self.morto = False

    def poll(self) -> int | None:
        return 0 if self.morto else None

    def terminate(self) -> None:
        self.terminado = True  # de propósito: ignora o pedido gentil

    def kill(self) -> None:
        self.morto = True

    def wait(self, timeout: float | None = None) -> int:
        if not self.morto:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout or 0.0)
        return 0


def test_encerrar_forca_kill_quando_terminate_nao_encerra(binario_e_modelo):
    """terminate() não encerra ⇒ estoura o prazo ⇒ kill() (C-18: cobre
    `runtime_llm.py` :344-347, onde nascia o órfão sem rede de teste)."""
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(ConfigRuntime(binario=binario, modelo=modelo))
    fake = _PopenQueIgnoraTerminate()
    runtime._proc = fake  # type: ignore[assignment]
    runtime._porta = 5000
    runtime.encerrar(prazo_s=0.01)
    assert fake.terminado and fake.morto  # tentou gentil, depois matou
    assert runtime._proc is None and not runtime.ativo()


# --------------------------------- ancoragem ao Job Object no start (C-02)
def test_start_ancora_processo_ao_job(binario_e_modelo, script_servidor):
    """Ao subir o `llama-server`, o runtime o anexa à âncora (Job Object no
    Windows). Verifica a integração em qualquer SO com uma âncora-espiã; a
    eficácia real do KILL_ON_JOB_CLOSE é testada em `test_job_windows.py`."""
    binario, modelo = binario_e_modelo

    class AncoraEspia:
        def __init__(self) -> None:
            self.anexados: list[object] = []

        def anexar(self, proc: object) -> bool:
            self.anexados.append(proc)
            return True

        def fechar(self) -> None:
            pass

    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=10.0),
        montar_comando=_comando_fake(script_servidor),
    )
    espia = AncoraEspia()
    runtime._ancora = espia  # type: ignore[assignment]
    try:
        runtime.base_url()
        assert espia.anexados == [runtime._proc]  # anexou o processo que subiu
    finally:
        runtime.encerrar()


# ---------------------------------------------- integração com a fábrica
def test_obter_provider_ollama_quando_hf_base_url(monkeypatch):
    """HF_BASE_URL definido ⇒ servidor do usuário tem precedência (ADR-0002)."""
    from agent.config import ConfigAgente
    from agent.provider import OllamaProvider, obter_provider

    monkeypatch.setenv("HF_BASE_URL", "http://localhost:11434/v1")
    prov = obter_provider(ConfigAgente(provider="local", base_url="http://localhost:11434/v1"))
    assert isinstance(prov, OllamaProvider)


def test_obter_provider_runtime_embarcado_sem_hf_base_url(monkeypatch):
    """Sem HF_BASE_URL ⇒ runtime embarcado é o padrão; provider aponta ao loopback."""
    from agent.config import ConfigAgente
    from agent.provider import OpenAICompatProvider, obter_provider

    monkeypatch.delenv("HF_BASE_URL", raising=False)

    class RuntimeFalso:
        def base_url(self) -> str:
            return "http://127.0.0.1:5599/v1"

    monkeypatch.setattr(rt, "runtime_embarcado", lambda: RuntimeFalso())
    prov = obter_provider(ConfigAgente(provider="local"))
    assert isinstance(prov, OpenAICompatProvider)
    assert prov.url == "http://127.0.0.1:5599/v1/chat/completions"


def test_obter_provider_embarcado_indisponivel_degrada(monkeypatch, perfil_atencao):
    """Sem binário/modelo E sem HF_BASE_URL ⇒ degradação P8, nunca exceção."""
    from agent.agente import analisar
    from agent.config import ConfigAgente

    monkeypatch.delenv("HF_BASE_URL", raising=False)
    monkeypatch.setattr(
        rt, "runtime_embarcado",
        lambda: RuntimeLLM(ConfigRuntime(binario=None, modelo=None)),
    )
    res = analisar(perfil_atencao, cfg=ConfigAgente(provider="local"))
    assert res.modo == "degradado"
    assert res.guardrails_violados == ["ERRO_CONFIG:RuntimeLLMIndisponivel"]
    assert res.fatos.saldo_devedor_total > 0  # determinístico intacto


# --------------------------------- invalidação na troca de modelo (C-03)
def test_base_url_apos_encerrar_nao_ressobe(binario_e_modelo, script_servidor):
    """Uma instância cujo `encerrar()` já rodou (troca de modelo/shutdown) NÃO
    pode ressubir o `llama-server` — ressuscitaria o modelo antigo e deixaria
    dois servidores no ar (C-03). ANTES da correção `base_url()` reiniciava o
    processo com o cfg antigo; agora levanta `RuntimeLLMInvalidado`."""
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=10.0),
        montar_comando=_comando_fake(script_servidor),
    )
    try:
        runtime.base_url()
        assert runtime.ativo()
        runtime.encerrar()  # troca de modelo derruba e invalida a instância
        assert not runtime.ativo()
        with pytest.raises(RuntimeLLMInvalidado):
            runtime.base_url()  # não ressobe: recusa com motivo (P8)
        assert not runtime.ativo()  # nenhum processo novo no ar
    finally:
        runtime.encerrar()


def test_chokepoint_reobtem_instancia_apos_invalidacao(monkeypatch):
    """O chokepoint `base_url_runtime_embarcado` intercepta a instância obsoleta
    e re-obtém a ATUAL (modelo novo) uma única vez, em vez de propagar o erro —
    é assim que a operação em voo passa a usar o modelo novo (C-03)."""
    from agent import provider as prov

    class InstanciaObsoleta:
        def base_url(self) -> str:
            raise RuntimeLLMInvalidado("RUNTIME_ENCERRADO: obsoleta (teste)")

    class InstanciaNova:
        def base_url(self) -> str:
            return "http://127.0.0.1:5599/v1"

    instancias = iter([InstanciaObsoleta(), InstanciaNova()])
    monkeypatch.setattr(rt, "runtime_embarcado", lambda: next(instancias))
    assert prov.base_url_runtime_embarcado() == "http://127.0.0.1:5599/v1"


def test_chokepoint_nao_recorre_infinitamente(monkeypatch):
    """Só UM retry: se a re-obtenção também vier invalidada (corrida patológica),
    propaga e degrada (P8) — sem recursão infinita."""
    from agent import provider as prov

    class SempreObsoleta:
        def base_url(self) -> str:
            raise RuntimeLLMInvalidado("RUNTIME_ENCERRADO: obsoleta (teste)")

    monkeypatch.setattr(rt, "runtime_embarcado", lambda: SempreObsoleta())
    with pytest.raises(RuntimeLLMInvalidado):
        prov.base_url_runtime_embarcado()


# ----------------------------- lock não retido durante o boot (C-12)
def _boot_lento(binario_e_modelo):
    """Runtime cujo poll de saúde BLOQUEIA até o teste liberar — simula o boot
    de dezenas de segundos de um modelo real, de forma controlável. Devolve
    (runtime, liberar, saude_chamada)."""
    binario, modelo = binario_e_modelo
    liberar = threading.Event()
    saude_chamada = threading.Event()

    def saude_lenta(_url: str) -> bool:
        saude_chamada.set()
        liberar.wait(timeout=10)  # segura o boot no meio do poll
        return True

    def comando_dummy(_porta):
        # Processo real e matável, sem abrir porta (não precisamos do HTTP: a
        # saúde é injetada). `time.sleep` longo p/ o teste controlar a morte.
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=10.0,
                      intervalo_poll_s=0.01),
        montar_comando=comando_dummy,
        verificar_saude=saude_lenta,
    )
    return runtime, liberar, saude_chamada


def test_ativo_responde_durante_o_boot_sem_bloquear(binario_e_modelo):
    """`ativo()` (pollado por `GET /llm/status`) responde JÁ durante o boot —
    não fica preso atrás do lock enquanto o modelo carrega (C-12). ANTES da
    correção `base_url` segurava `self._lock` no poll e `ativo()` bloqueava."""
    runtime, liberar, saude_chamada = _boot_lento(binario_e_modelo)
    t = threading.Thread(target=runtime.base_url)
    t.start()
    try:
        assert saude_chamada.wait(timeout=5), "o boot não chegou ao poll de saúde"
        inicio = time.monotonic()
        vivo = runtime.ativo()
        decorrido = time.monotonic() - inicio
        assert decorrido < 1.0, f"ativo() bloqueou {decorrido:.1f}s atrás do lock"
        assert vivo  # o processo do boot já está no ar
    finally:
        liberar.set()
        t.join(timeout=10)
        runtime.encerrar()


def test_encerrar_durante_o_boot_mata_o_processo(binario_e_modelo):
    """`encerrar()` no meio do boot mata o processo que subia sem esperar o
    health timeout (C-12) e o boot em voo termina invalidado — o processo NÃO
    fica órfão. ANTES `encerrar()` bloqueava atrás do lock retido pelo poll."""
    runtime, liberar, saude_chamada = _boot_lento(binario_e_modelo)
    resultado: dict[str, BaseException] = {}

    def correr() -> None:
        try:
            runtime.base_url()
        except BaseException as exc:  # noqa: BLE001 - captura p/ inspeção no teste
            resultado["exc"] = exc

    t = threading.Thread(target=correr)
    t.start()
    try:
        assert saude_chamada.wait(timeout=5), "o boot não chegou ao poll de saúde"
        proc = runtime._proc
        assert proc is not None and proc.poll() is None  # boot no ar
        inicio = time.monotonic()
        runtime.encerrar()  # durante o boot
        decorrido = time.monotonic() - inicio
        assert decorrido < 3.0, f"encerrar() esperou {decorrido:.1f}s (timeout do boot)"
    finally:
        liberar.set()
        t.join(timeout=10)
    assert proc.poll() is not None  # o processo do boot morreu
    assert not runtime.ativo()
    assert isinstance(resultado.get("exc"), RuntimeLLMInvalidado)


# ---------------------------- classificador e métricas de boot (ADR-0022)
# Linhas REAIS do crash de campo (2026-07-15, GTX 1650 4 GB, b9966): o auto-fit
# avisa que não coube ("failed to fit params", pois -ngl foi forçado) e a
# alocação estoura com OOM — as DUAS linhas aparecem, e a falta de VRAM é a
# causa decisiva (dispara a dica de reduzir contexto no T-2502).
_LOG_CRASH_OOM = [
    "0.00.483.401 W common_fit_params: failed to fit params to free device "
    "memory: n_gpu_layers already set by user to 99, abort",
    "ggml_vulkan: Device memory allocation of size 1056964608 failed.",
    "ggml_vulkan: vk::Device::allocateMemory: ErrorOutOfDeviceMemory",
    "0.04.251.378 E alloc_tensor_range: failed to allocate Vulkan0 buffer of "
    "size 1056964608",
]

# Variante em que o auto-fit aborta mas NÃO se chega ao OOM (sem a linha de
# alocação Vulkan): classifica como GPU_FIT_ABORTADO.
_LOG_FIT_ABORTADO = [
    "0.00.483.401 W common_fit_params: failed to fit params to free device "
    "memory: n_gpu_layers already set by user to 99, abort",
    "0.00.500.000 E srv    load_model: failed to load model",
]

# Boot BOM mínimo (linhas reais de campo): só o n_ctx_slot é extraível.
_LOG_BOOT_BOM_MINIMO = [
    r"0.00.340.011 I srv    load_model: loading model 'C:\...\modelos\phi.gguf'",
    "0.07.971.309 I srv    load_model: initializing, n_slots = 4, "
    "n_ctx_slot = 4096, kv_unified = 'true'",
    "0.07.990.688 I srv  llama_server: model loaded",
    "0.07.990.715 I srv  llama_server: listening on http://127.0.0.1:18181",
]

# Boot BOM com `-lv 4` — sequência REAL de campo (b9966, GTX 1650): o load faz
# DOIS passes e há VÁRIAS linhas `model buffer size`; a de dry-run `Vulkan0 ...
# 0.00 MiB` vem primeiro, depois `CPU_Mapped ... 2281.66 MiB`, e só então a real
# `Vulkan0 ... 358.41 MiB`. O parser ancora em `VulkanN` (exclui CPU_Mapped e
# Vulkan_Host) e pega a ÚLTIMA ocorrência ⇒ 358.41 MiB, offload 5/33.
_LOG_BOOT_BOM_METRICAS = [
    "0.02.450.563 I load_tensors: offloaded 5/33 layers to GPU",
    "load_tensors:      Vulkan0 model buffer size =     0.00 MiB",
    "load_tensors:  Vulkan_Host model buffer size =     0.00 MiB",
    "0.02.450.563 I load_tensors: offloaded 5/33 layers to GPU",
    "load_tensors:   CPU_Mapped model buffer size =  2281.66 MiB",
    "0.02.450.589 I load_tensors:      Vulkan0 model buffer size =   358.41 MiB",
    "0.07.971.309 I srv    load_model: initializing, n_slots = 4, "
    "n_ctx_slot = 4096, kv_unified = 'true'",
]

# Saída REAL do `llama-server --list-devices` no host (2 GPUs).
_SAIDA_LIST_DEVICES = (
    "Available devices:\n"
    "  Vulkan0: NVIDIA GeForce GTX 1650 (4149 MiB, 3535 MiB free)\n"
    "  Vulkan1: Intel(R) UHD Graphics 630 (8120 MiB, 7458 MiB free)\n"
)


def test_classificador_gpu_sem_memoria():
    """O crash real de campo (OOM) ⇒ GPU_SEM_MEMORIA (a causa decisiva vence o
    aviso de fit, mesmo com as duas linhas presentes)."""
    assert rt.classificar_falha(_LOG_CRASH_OOM) == rt.MotivoFalhaGPU.GPU_SEM_MEMORIA


def test_classificador_gpu_fit_abortado():
    """Auto-fit aborta sem chegar ao OOM ⇒ GPU_FIT_ABORTADO."""
    assert rt.classificar_falha(_LOG_FIT_ABORTADO) == rt.MotivoFalhaGPU.GPU_FIT_ABORTADO


def test_classificador_generico():
    """Falha sem padrão conhecido ⇒ GENERICO (fallback sempre existe)."""
    linhas = ["0.00.1 E srv load_model: failed to load model, arquivo corrompido"]
    assert rt.classificar_falha(linhas) == rt.MotivoFalhaGPU.GENERICO


def test_classificador_tolerante_a_lixo():
    """Linhas vazias/lixo e sequência vazia ⇒ GENERICO, sem exceção."""
    assert rt.classificar_falha([]) == rt.MotivoFalhaGPU.GENERICO
    assert rt.classificar_falha(["", "   ", "\x00lixo binário"]) == \
        rt.MotivoFalhaGPU.GENERICO


def test_extrair_metricas_boot_bom_completo():
    """Do boot bom rico, extrai camadas, VRAM (a ÚLTIMA `VulkanN`, não o dry-run
    zerado nem o `CPU_Mapped`) e contexto. Dispositivo NÃO sai do stderr."""
    m = rt.extrair_metricas(_LOG_BOOT_BOM_METRICAS)
    assert m.camadas_offload == 5
    assert m.camadas_total == 33
    assert m.vram_bytes == int(round(358.41 * 1024 * 1024))
    assert m.ctx_efetivo == 4096
    assert m.dispositivo is None  # vem do --list-devices, não do stderr


def test_extrair_metricas_boot_bom_minimo():
    """Do boot bom mínimo (linhas reais), só o contexto é extraível — o resto
    fica None (tolerância)."""
    m = rt.extrair_metricas(_LOG_BOOT_BOM_MINIMO)
    assert m.ctx_efetivo == 4096
    assert m.camadas_offload is None
    assert m.camadas_total is None
    assert m.vram_bytes is None
    assert m.dispositivo is None


def test_extrair_metricas_tolerante_a_lixo():
    """Linhas vazias/lixo ⇒ todas as métricas None, sem exceção."""
    m = rt.extrair_metricas(["", "nada aqui", "\x00"])
    assert m == rt.MetricasBoot()


def test_parsear_dispositivos_linhas_reais():
    """Parser puro do `--list-devices` com a saída real do host (2 GPUs)."""
    devs = rt._parsear_dispositivos(_SAIDA_LIST_DEVICES)
    assert devs == [
        rt.DispositivoGPU("NVIDIA GeForce GTX 1650", 4149, 3535),
        rt.DispositivoGPU("Intel(R) UHD Graphics 630", 8120, 7458),
    ]


def test_parsear_dispositivos_tolerante():
    """Sem dispositivos / lixo ⇒ lista vazia, sem exceção."""
    assert rt._parsear_dispositivos("") == []
    assert rt._parsear_dispositivos("Available devices:\n  (nenhum)\n") == []


def test_listar_dispositivos_tolerante_a_binario_invalido(tmp_path):
    """Binário que não executa ⇒ lista vazia (tolerância total), e o resultado
    é cacheado por caminho (não re-executa)."""
    falso = tmp_path / "nao-executavel.bin"
    falso.write_text("não sou um exe", encoding="utf-8")
    rt._CACHE_DISPOSITIVOS.pop(str(falso), None)
    assert rt.listar_dispositivos(falso) == []
    assert str(falso) in rt._CACHE_DISPOSITIVOS  # cacheado


def test_listar_dispositivos_usa_cache(monkeypatch, tmp_path):
    """Com o cache quente, `--list-devices` não é re-executado."""
    falso = tmp_path / "bin"
    rt._CACHE_DISPOSITIVOS[str(falso)] = [rt.DispositivoGPU("GPU Fake", 4096, 2048)]

    def nao_deve_rodar(*a, **k):  # pragma: no cover - só falha se chamado
        raise AssertionError("subprocess.run não deveria rodar com cache quente")

    monkeypatch.setattr(rt.subprocess, "run", nao_deve_rodar)
    assert rt.listar_dispositivos(falso) == [rt.DispositivoGPU("GPU Fake", 4096, 2048)]


# ------------------------------------- retry em CPU e boot_info (ADR-0022)
def _montar_conta_e_morre():
    """montar_comando que conta as tentativas e SEMPRE devolve um comando que
    morre na hora (simula o crash da GPU em todos os boots)."""
    estado = {"n": 0}

    def montar(_porta):
        estado["n"] += 1
        return [sys.executable, "-c", "raise SystemExit(1)"]

    return montar, estado


def test_boot_info_inicial_nunca_subiu(binario_e_modelo):
    """Antes de qualquer boot, o diagnóstico é neutro (`nunca_subiu`, sem
    métricas)."""
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(ConfigRuntime(binario=binario, modelo=modelo))
    info = runtime.boot_info()
    assert info.modo == "nunca_subiu"
    assert info.motivo_fallback is None
    assert info.metricas == rt.MetricasBoot()


def test_boot_info_gpu_no_sucesso_de_primeira(binario_e_modelo, script_servidor):
    """Boot que sobe de primeira (config auto) ⇒ modo `gpu`, sem motivo."""
    binario, modelo = binario_e_modelo
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=10.0),
        montar_comando=_comando_fake(script_servidor),
    )
    try:
        runtime.base_url()
        info = runtime.boot_info()
        assert info.modo == "gpu"
        assert info.motivo_fallback is None
    finally:
        runtime.encerrar()


def test_retry_cpu_salva_o_boot(binario_e_modelo, script_servidor):
    """Processo que morre na 1ª tentativa e sobe na 2ª ⇒ UMA retentativa em CPU;
    boot_info vira `cpu_fallback` com motivo tipado."""
    binario, modelo = binario_e_modelo
    estado = {"n": 0}

    def montar(porta):
        estado["n"] += 1
        if estado["n"] == 1:
            return [sys.executable, "-c", "raise SystemExit(1)"]  # 1ª: crash
        return [sys.executable, str(script_servidor), "--port", str(porta)]  # 2ª: sobe

    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=10.0),
        montar_comando=montar,
    )
    try:
        base = runtime.base_url()
        assert base.endswith("/v1")
        assert estado["n"] == 2  # exatamente uma retentativa
        info = runtime.boot_info()
        assert info.modo == "cpu_fallback"
        assert isinstance(info.motivo_fallback, rt.MotivoFalhaGPU)
    finally:
        runtime.encerrar()


def test_retry_morre_nas_duas_degrada_sem_loop(binario_e_modelo):
    """Se as duas tentativas morrem ⇒ RuntimeLLMIndisponivel, sem terceira
    tentativa (sem loop), e boot_info fica `nunca_subiu` com o motivo."""
    binario, modelo = binario_e_modelo
    montar, estado = _montar_conta_e_morre()
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=2.0),
        montar_comando=montar,
    )
    with pytest.raises(RuntimeLLMIndisponivel):
        runtime.base_url()
    assert estado["n"] == 2  # 1 tentativa + 1 retentativa, e para
    assert not runtime.ativo()
    assert runtime.boot_info().modo == "nunca_subiu"


def test_sem_retry_quando_config_ja_e_cpu_puro(binario_e_modelo):
    """Config já em CPU puro (`-ngl 0`) que falha NÃO faz retry (a retentativa em
    CPU não mudaria nada) — degrada com uma única tentativa."""
    binario, modelo = binario_e_modelo
    montar, estado = _montar_conta_e_morre()
    runtime = RuntimeLLM(
        ConfigRuntime(binario=binario, modelo=modelo, timeout_health_s=2.0,
                      flags_extra=("-ngl", "0")),
        montar_comando=montar,
    )
    with pytest.raises(RuntimeLLMIndisponivel):
        runtime.base_url()
    assert estado["n"] == 1  # nenhuma retentativa


# ------------------------------------------------------- real (opt-in)
@pytest.mark.skipif(
    not os.getenv(rt.VAR_TESTE_REAL),
    reason="requer llama-server + modelo GGUF reais (HF_LLAMA_REAL=1, HF_LLAMA_SERVER, HF_LLM_MODELO)",
)
def test_runtime_real_sobe_e_responde_health():
    binario = resolver_binario_llama()
    modelo = resolver_modelo()
    assert binario is not None and modelo is not None, "configure HF_LLAMA_SERVER e HF_LLM_MODELO"
    runtime = RuntimeLLM(ConfigRuntime(binario=binario, modelo=modelo))
    try:
        base = runtime.base_url()
        assert base.endswith("/v1")
        assert rt._saude_ok(base.removesuffix("/v1") + "/health")
        assert runtime.ativo()
    finally:
        runtime.encerrar()
        time.sleep(0.1)
