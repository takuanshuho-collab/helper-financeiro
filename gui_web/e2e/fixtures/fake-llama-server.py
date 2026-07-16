"""
"llama-server" FALSO para o E2E do painel "Ultimo boot da IA" (T-2503, ADR-0022).

Controlado pela env HF_FAKE_LLAMA_MODE (propagada do processo do Electron ate
aqui, atraves do sidecar Python — nenhum arquivo em disco alem do llm.json de
teste): "cpu_fallback" falha a 1a tentativa (sem "-ngl 0" no argv) imitando o
OOM de campo do ADR-0022 e sobe saudavel na retentativa (com "-ngl 0"); outros
valores sobem de primeira. Sem chat completions "de verdade": o endpoint
devolve 500 de proposito — o grafo do agente (agent/grafo.py) degrada com
seguranca (P8) qualquer falha do provider, entao o job da analise ainda chega
a "pronto" (com secao degradada) e o boot_info do runtime already registrado
continua valendo para o painel/o aviso_runtime.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


def _arg(flag):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _falhar(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
    sys.exit(1)


if "--list-devices" in sys.argv:
    # Formato esperado por `runtime_llm._RE_DISPOSITIVO_LISTA`.
    print("  Vulkan0: NVIDIA GeForce GTX 1650 (4149 MiB, 3535 MiB free)")
    sys.exit(0)

MODO = os.environ.get("HF_FAKE_LLAMA_MODE", "gpu")
TEM_NGL0 = _arg("-ngl") == "0"

if MODO == "falha_total":
    _falhar("ggml_vulkan: ErrorOutOfDeviceMemory (falha total simulada)")

if MODO == "cpu_fallback" and not TEM_NGL0:
    _falhar("ggml_vulkan: ErrorOutOfDeviceMemory (1a tentativa simulada)")

# Boot bom (1a tentativa em modo "gpu"/default, ou retentativa cpu_fallback):
# emite as linhas que `runtime_llm.extrair_metricas` sabe ler.
if TEM_NGL0:
    sys.stderr.write("offloaded 0/32 layers to GPU\n")
else:
    sys.stderr.write("offloaded 24/32 layers to GPU\n")
sys.stderr.write("Vulkan0 model buffer size = 358.41 MiB\n")
sys.stderr.write("n_ctx_slot = 4096\n")
sys.stderr.flush()

PORTA = int(_arg("--port"))


class Handler(BaseHTTPRequestHandler):
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

    def do_POST(self):
        # Sem chat completions real: o grafo degrada com seguranca (P8) — ver
        # docstring do modulo. 500 rapido evita esperar timeout de rede.
        self.send_response(500)
        self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", PORTA), Handler).serve_forever()
