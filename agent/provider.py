"""
Providers de LLM (REQ-LLM-003/004, ADR-0002, ADR-0005).

Interface única `LLMProvider.analisar(fatos) -> AnaliseAgente`. Implementações:
  - FakeProvider        : determinístico, SEM rede — usado pelo harness (M1).
  - OllamaProvider      : local-first via API nativa do Ollama (T-201).
  - OpenAICompatProvider: nuvem via endpoint OpenAI-compatible (T-202).

Trocar de provider não muda nada acima desta camada (o pipeline de guardrails
é o mesmo). É a "tomada padrão": o aparelho não sabe de qual usina vem a luz.

Structured output (ADR-0005): sem SDK nem framework — o POST é feito com a
stdlib e a resposta é validada com Pydantic. Erros de rede e de schema SOBEM;
recuperar (1 retry) ou degradar é decisão do orquestrador (REQ-LLM-002/P8).
"""
from __future__ import annotations

import copy
import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Protocol

from pydantic import ValidationError

from contracts import AnaliseAgente, FatosFinanceiros, PassoNegociacao, Prioridade
from core.utils import formatar_brl

from .config import ConfigAgente
from .prompts import SYSTEM_PROMPT, montar_prompt_usuario

log = logging.getLogger("helper_financeiro.provider")

# Baixa temperatura: aderência ao schema e aos fatos vale mais que criatividade.
TEMPERATURA = 0.2
# Os FATOS serializados crescem com o nº de dívidas; o padrão de 2048 tokens
# de contexto do Ollama truncaria carteiras grandes.
NUM_CTX = 8192

# Streaming do contador (T-2603, ADR-0023): o `OpenAICompatProvider` emite o
# progresso (n tokens) no máximo a cada `_STREAM_THROTTLE_TOKENS` tokens OU a
# cada `_STREAM_THROTTLE_S` segundos — o que vier PRIMEIRO — para não inundar o
# event loop/SSE (revisão G3). O contador reseta a cada chamada HTTP.
_STREAM_THROTTLE_TOKENS = 16
_STREAM_THROTTLE_S = 0.2


class LLMProvider(Protocol):
    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente: ...


# --------------------------------------------------------------- FakeProvider
class FakeProvider:
    """Provider determinístico para testes: monta uma análise coerente com os
    fatos usando SOMENTE números que vieram deles (respeita H1 por construção).
    """

    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente:
        comp_pct = round(fatos.comprometimento_renda * 100)
        aval = next((e for e in fatos.estrategias if e.metodo == "avalanche"), None)

        prioridades = []
        # Ordena por taxa mensal desc (mais cara primeiro) — narrativa de avalanche
        for i, d in enumerate(sorted(fatos.dividas,
                                     key=lambda x: x.taxa_mensal, reverse=True), 1):
            prioridades.append(Prioridade(
                ordem=i, credor_token=d.token,
                justificativa=(f"{d.token} tem custo de "
                               f"{round(d.taxa_mensal*100, 2)}% ao mês, "
                               "entre os mais altos da carteira."),
            ))

        roteiro = []
        for d in sorted(fatos.dividas, key=lambda x: x.taxa_mensal, reverse=True):
            roteiro.append(PassoNegociacao(
                credor_token=d.token,
                abordagem="portabilidade" if d.taxa_mensal > 0.03 else "reducao",
                argumentos=[
                    f"Saldo devedor informado de {formatar_brl(d.saldo_devedor)}.",
                    "Histórico de pagamento e intenção de manter o contrato.",
                ],
                concessoes_possiveis=["Quitação à vista se houver desconto relevante."],
            ))

        meses_txt = (f"{aval.meses} meses" if aval and aval.quitavel
                     else "prazo a definir")
        return AnaliseAgente(
            sumario_executivo=(
                f"O comprometimento de renda de {comp_pct}% coloca o orçamento em "
                f"zona de '{fatos.classificacao}'. A prioridade é atacar a dívida "
                "mais cara primeiro (estratégia avalanche)."
            ),
            diagnostico_interpretado=(
                f"Com saldo devedor total de {formatar_brl(fatos.saldo_devedor_total)} e "
                f"fluxo de caixa de {formatar_brl(fatos.fluxo_caixa)}, o foco deve ser reduzir "
                f"o custo dos juros. Pela avalanche, a quitação ocorre em {meses_txt}."
            ),
            prioridades=prioridades,
            roteiro_negociacao=roteiro,
            alertas_risco=(["Fluxo de caixa negativo: cortar despesas é urgente."]
                           if fatos.tem_deficit else []),
            confianca=0.9,
        )


# --------------------------------------------------------- Providers reais (M2)
def _post_json(url: str, payload: dict[str, Any],
               headers: dict[str, str], timeout_s: int) -> dict[str, Any]:
    """POST JSON → JSON com a stdlib (ADR-0005). Erros de rede/HTTP sobem."""
    corpo = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=corpo, method="POST",
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        dados: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    return dados


def _abrir_stream(url: str, corpo: bytes, headers: dict[str, str],
                  timeout_s: int) -> Any:
    """Abre um POST `stream=true` e devolve a resposta file-like (iterável por
    linhas `data: ...`) — SEM ler o corpo inteiro (ADR-0023, T-2603).

    Seam de teste espelhando `_post_json`: os testes trocam esta função por um
    file-like que emite chunks SSE, exercitando o parser sem tocar a rede. Um
    HTTP 400 (ex.: a recusa de gramática do phi-3.5) levanta `HTTPError` AQUI, no
    `urlopen`, ANTES de qualquer chunk — provado no spike do dia 1 contra o build
    embarcado real —, então o fallback do T-2505 dispara igual ao POST único."""
    req = urllib.request.Request(
        url, data=corpo, method="POST",
        headers={"Content-Type": "application/json", **headers})
    return urllib.request.urlopen(req, timeout=timeout_s)


def _mensagens(fatos: FatosFinanceiros,
               correcao: str | None = None) -> list[dict[str, str]]:
    """Mensagens do chat; `correcao` é o feedback do guardrail no retry único.

    Modelos locais pequenos fabricam números mesmo com o prompt endurecido
    (caso real: "ex.: R$ 200/mês"). Nomear os números órfãos na recuperação
    (REQ-LLM-002) é muito mais eficaz do que uma nova amostra às cegas.
    """
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": montar_prompt_usuario(fatos)},
    ]
    if correcao:
        msgs.append({"role": "user", "content": correcao})
    return msgs


def schema_estrito() -> dict[str, Any]:
    """Schema do `AnaliseAgente` endurecido para o modo strict OpenAI.

    O strict exige `additionalProperties: false` e todos os campos em
    `required` em CADA objeto — o Pydantic não emite isso por padrão.
    """
    schema: dict[str, Any] = copy.deepcopy(AnaliseAgente.model_json_schema())

    def endurecer(no: Any) -> None:
        if isinstance(no, dict):
            if no.get("type") == "object" and "properties" in no:
                no["additionalProperties"] = False
                no["required"] = list(no["properties"].keys())
            for valor in no.values():
                endurecer(valor)
        elif isinstance(no, list):
            for item in no:
                endurecer(item)

    endurecer(schema)
    return schema


class OllamaProvider:
    """Local-first via API nativa do Ollama (T-201, REQ-LLM-003/004).

    Usa `/api/chat` com `format` = JSON Schema do `AnaliseAgente`: o servidor
    restringe a gramática de amostragem, então a aderência ao schema é por
    construção — a forma mais forte disponível (ADR-0005).
    """

    def __init__(self, cfg: ConfigAgente):
        self.cfg = cfg
        # Aceita tanto a raiz ("http://localhost:11434") quanto a forma
        # OpenAI-compat ("…/v1") no HF_BASE_URL — a API nativa fica na raiz.
        raiz = cfg.base_url.rstrip("/").removesuffix("/v1")
        self.url = f"{raiz}/api/chat"
        if "localhost" not in raiz and "127.0.0.1" not in raiz:
            log.warning("Provider 'local' apontando para host remoto (%s) — "
                        "verifique o REQ-LLM-004 (sem tráfego externo).", raiz)

    def analisar(self, fatos: FatosFinanceiros,
                 correcao: str | None = None) -> AnaliseAgente:
        resposta = _post_json(self.url, {
            "model": self.cfg.model,
            "messages": _mensagens(fatos, correcao),
            "stream": False,
            "format": AnaliseAgente.model_json_schema(),
            "options": {"temperature": TEMPERATURA, "num_ctx": NUM_CTX},
        }, headers={}, timeout_s=self.cfg.timeout_s)
        return AnaliseAgente.model_validate_json(resposta["message"]["content"])

    def analisar_com_correcao(self, fatos: FatosFinanceiros,
                              correcao: str) -> AnaliseAgente:
        return self.analisar(fatos, correcao)


# Padrões (case-insensitive) do corpo com que o `llama-server` RECUSA, com
# HTTP 400, a gramática derivada de `json_schema` estrito para certos
# tokenizers — provado em campo com o phi-3.5 (1º do catálogo) nos builds b9966
# e b10043: `{"error":{...,"message":"Failed to initialize samplers: Unexpected
# empty grammar stack after accepting piece: | (29989)",...}}`. É bug conhecido
# do llama.cpp (issues #12597/#21017/#23677), não do nosso schema. Guardados
# numa tupla-constante como os `_PADROES_FALHA` do runtime.
_PADROES_RECUSA_GRAMATICA: tuple[str, ...] = (
    "failed to initialize samplers",
    "empty grammar stack",
)

# Instrução do fallback: o modo de falha REAL observado foi o modelo ECOAR os
# FATOS em vez de produzir a análise (por isso a validação Pydantic quase
# passou, a 1 erro). A mensagem é curta e imperativa e deixa explícito que a
# resposta é a ANÁLISE, não uma cópia da entrada. O JSON Schema é anexado logo
# depois desta frase (ver `_analisar_json_object`).
_INSTRUCAO_JSON_OBJECT = (
    "Responda com UM ÚNICO objeto JSON — a sua ANÁLISE — que valide contra o "
    "JSON Schema abaixo. NÃO repita nem ecoe os FATOS: o objeto é o seu parecer "
    "(sumário executivo, diagnóstico, prioridades, roteiro de negociação, "
    "alertas), jamais uma cópia dos dados de entrada. Não escreva nada fora do "
    "objeto JSON.\nJSON Schema:\n"
)

# Teto de erros nomeados no conserto dirigido: um JSON grosseiramente errado
# gera dezenas de violações; as primeiras já orientam a correção e a lista curta
# não estoura o contexto do modelo pequeno.
_MAX_ERROS_CONSERTO = 10


def _resumo_erros_pydantic(erro: ValidationError) -> str:
    """Traduz os erros do Pydantic em linhas legíveis para o modelo consertar.

    Para cada erro: caminho do campo, a mensagem e o tipo — o suficiente para o
    modelo saber ONDE e O QUE corrigir sem receber o dump cru do Pydantic.
    """
    linhas = []
    for err in erro.errors()[:_MAX_ERROS_CONSERTO]:
        caminho = ".".join(map(str, err["loc"])) or "(raiz)"
        linhas.append(f"- {caminho}: {err['msg']} (tipo esperado: {err['type']})")
    return "\n".join(linhas)


class OpenAICompatProvider:
    """Endpoint OpenAI-compatible — nuvem OU servidor local (LM Studio, etc.).

    A chave vem SÓ via env (SEC-002) e é EXIGIDA apenas para endpoints remotos;
    um servidor local em loopback dispensa chave (ADR-0010). O documento/os
    fatos nunca saem da máquina quando o endpoint é local.

    Structured output com fallback (T-2505): a 1ª chamada usa `json_schema`
    estrito — a forma mais forte, que funciona com Qwen/Granite/LM Studio/nuvem.
    Se o servidor recusar essa gramática com um 400 conhecido (bug do llama.cpp
    com o tokenizer do phi-3.5, ver `_PADROES_RECUSA_GRAMATICA`), reenvia UMA
    vez com `response_format=json_object` + o JSON Schema injetado no prompt. A
    validação segue 100% Pydantic; o retry-correção (ADR-0011) e a degradação
    P8 do grafo continuam intactos — o fallback é ORTOGONAL a eles.
    """

    #: Callback de progresso OPCIONAL (T-2603, ADR-0023). Setado por INSTÂNCIA
    #: pelo nó `chamar_llm` quando a análise roda sob stream (o provider é
    #: recriado a cada análise — `obter_provider` —, logo um provider por
    #: análise: sem corrida entre jobs). `None` (default) ⇒ POST único como
    #: sempre; ausente na extração/Ollama/Fake ⇒ retrocompatível. Args:
    #: `(n_tokens_acumulados, tentativa)` — `tentativa` é SEMÂNTICA, não nº de
    #: chamada HTTP (correção do revisor, T-2603): 1 = gerando a análise
    #: (INCLUSIVE quando o fallback de gramática do T-2505 refez a chamada —
    #: mecânica interna transparente, o phi-3.5 400a a 1ª chamada de TODA
    #: análise e o usuário não pode ler isso como "refinando"); 2 = refinando
    #: de verdade (retry do grafo com feedback do guardrail, ou o conserto
    #: dirigido do JSON inválido). Quem traduz para rótulo é o backend (nunca
    #: expõe retry como falha — revisão U3).
    on_progress: Callable[[int, int], None] | None = None

    def __init__(self, cfg: ConfigAgente,
                 relogio: Callable[[], float] = time.monotonic):
        if not cfg.api_key and not cfg.endpoint_local:
            raise RuntimeError(
                "HF_API_KEY ausente: endpoint remoto exige chave via variável "
                "de ambiente (REQ-SEC-002).")
        self.cfg = cfg
        self.url = cfg.base_url.rstrip("/") + "/chat/completions"
        # Relógio injetável para o throttle do contador (teste sem dormir).
        self._relogio = relogio
        # Memoização por INSTÂNCIA: assim que este servidor recusa a gramática
        # do `json_schema` estrito, as chamadas seguintes DESTA instância vão
        # direto ao fallback, sem gastar a 1ª requisição fadada ao 400 (o retry
        # do grafo faz uma 2ª chamada `analisar` na mesma instância). Como o
        # provider é RECRIADO a cada análise (`obter_provider`), isso nunca
        # gruda entre sessões: um servidor/modelo que aceita o schema estrito
        # volta ao caminho forte na próxima análise.
        self._gramatica_recusada = False

    def _headers(self) -> dict[str, str]:
        return ({"Authorization": f"Bearer {self.cfg.api_key}"}
                if self.cfg.api_key else {})

    def analisar(self, fatos: FatosFinanceiros,
                 correcao: str | None = None) -> AnaliseAgente:
        if self._gramatica_recusada:
            return self._analisar_json_object(fatos, correcao)
        try:
            return self._analisar_json_schema(fatos, correcao)
        except urllib.error.HTTPError as e:
            # Só o 400 de recusa de gramática vira fallback; qualquer outro
            # HTTPError (400 de outro tipo, 401, 500…) SOBE como hoje (P8).
            if e.code == 400 and self._e_recusa_de_gramatica(e):
                log.info("llama-server recusou a gramática do json_schema "
                         "estrito (400); reenviando com json_object + schema "
                         "no prompt (T-2505).")
                self._gramatica_recusada = True
                return self._analisar_json_object(fatos, correcao)
            raise

    def _e_recusa_de_gramatica(self, erro: urllib.error.HTTPError) -> bool:
        """True se o corpo do 400 casa (case-insensitive) com uma recusa de
        gramática conhecida. Lê o corpo do erro apenas uma vez; falha de leitura
        é tratada como 'não é recusa de gramática' (o erro original propaga)."""
        try:
            corpo = erro.read().decode("utf-8", "replace").lower()
        except Exception:  # noqa: BLE001 — corpo ilegível ⇒ não é a recusa alvo
            return False
        return any(padrao in corpo for padrao in _PADROES_RECUSA_GRAMATICA)

    def _conteudo_chat(self, payload: dict[str, Any], *,
                       refinando: bool = False) -> str:
        """Faz o POST do chat e devolve `choices[0].message.content`.

        Ponto ÚNICO por onde os 3 degraus do T-2505 falam com o servidor: com
        `on_progress` ligado usa `stream=true` (conta tokens e emite progresso);
        sem ele, POST único via `_post_json` — BYTE A BYTE idêntico ao caminho
        pré-T-2603 (mesmo payload, sem a chave `stream`), o que preserva a
        resiliência do T-2505 e os testes existentes sem mudança de expectativa.
        A sentinela de teste garante: para o MESMO corpo, stream e POST único
        devolvem o MESMO texto. `refinando` é a semântica que o chamador declara
        para o progresso (ver o docstring de `on_progress`)."""
        if self.on_progress is not None:
            return self._chat_stream(payload, refinando=refinando)
        resposta = _post_json(self.url, payload, headers=self._headers(),
                              timeout_s=self.cfg.timeout_s)
        conteudo: str = resposta["choices"][0]["message"]["content"]
        return conteudo

    def _chat_stream(self, payload: dict[str, Any], *,
                     refinando: bool = False) -> str:
        """Consome um chat `stream=true` acumulando o texto EXATAMENTE como o
        corpo não-streaming produziria, contando tokens e emitindo o progresso
        com throttle (ADR-0023, T-2603).

        Defensivo (revisão S4): qualquer erro NO MEIO do stream (chunk malformado,
        conexão caída) propaga e o texto parcial é DESCARTADO — nunca retornamos
        um JSON truncado. Como o `return` só ocorre após o `[DONE]`/EOF, uma
        exceção no laço aborta sem devolver nada, e o erro sobe pelo MESMO caminho
        do POST único: o 400 de gramática (que chega no `urlopen`, antes de
        qualquer token) continua caindo no fallback `json_object`; os demais
        degradam no grafo (P8)."""
        tentativa = 2 if refinando else 1
        corpo = json.dumps({**payload, "stream": True}).encode("utf-8")
        pedacos: list[str] = []
        n_tokens = 0
        marco_t = self._relogio()
        marco_n = 0
        with _abrir_stream(self.url, corpo, self._headers(),
                           self.cfg.timeout_s) as resp:
            for linha_bruta in resp:
                linha = (linha_bruta.decode("utf-8") if isinstance(linha_bruta, bytes)
                         else linha_bruta).strip()
                if not linha.startswith("data:"):
                    continue  # linhas em branco / comentários SSE (`: ping`)
                dado = linha[len("data:"):].strip()
                if dado == "[DONE]":
                    break
                delta = json.loads(dado)["choices"][0].get("delta", {})
                conteudo = delta.get("content")
                if not conteudo:
                    continue  # chunks de role/finish_reason sem texto
                pedacos.append(conteudo)
                n_tokens += 1
                agora = self._relogio()
                if (n_tokens - marco_n >= _STREAM_THROTTLE_TOKENS
                        or agora - marco_t >= _STREAM_THROTTLE_S):
                    self._emitir_progresso(n_tokens, tentativa)
                    marco_t, marco_n = agora, n_tokens
        return "".join(pedacos)

    def _emitir_progresso(self, n_tokens: int, tentativa: int) -> None:
        """Chama o callback de progresso, se houver (mantém `_chat_stream` enxuto)."""
        callback = self.on_progress
        if callback is not None:
            callback(n_tokens, tentativa)

    def _analisar_json_schema(self, fatos: FatosFinanceiros,
                              correcao: str | None) -> AnaliseAgente:
        """1ª forma (forte): a gramática de amostragem é restrita pelo schema."""
        conteudo = self._conteudo_chat({
            "model": self.cfg.model,
            "messages": _mensagens(fatos, correcao),
            "temperature": TEMPERATURA,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "AnaliseAgente", "strict": True,
                                "schema": schema_estrito()},
            },
        }, refinando=correcao is not None)  # retry do guardrail = refino real
        return AnaliseAgente.model_validate_json(conteudo)

    def _post_json_object(self, mensagens: list[dict[str, str]], *,
                          refinando: bool = False) -> str:
        """Uma requisição `json_object` (temp 0) → conteúdo bruto (string JSON).

        Temperatura ZERO só aqui, de propósito: sem a gramática restringindo a
        amostragem, o formato depende do modelo "se comportar" — medido em
        campo (GTX 1650, phi-3.5, 2026-07-17): com `TEMPERATURA` (0.2) só 1 de
        3 análises validou o schema; com 0.0/0.1, 4 de 4. O caminho forte
        (`json_schema` estrito) mantém a `TEMPERATURA` normal — lá a gramática
        garante o formato e a variação melhora o texto.
        """
        return self._conteudo_chat({
            "model": self.cfg.model,
            "messages": mensagens,
            "temperature": 0.0,  # aderência ao schema > variação de texto
            "response_format": {"type": "json_object"},
        }, refinando=refinando)

    def _analisar_json_object(self, fatos: FatosFinanceiros,
                              correcao: str | None) -> AnaliseAgente:
        """Fallback: `json_object` (JSON livre) + o schema injetado no prompt.

        A eventual correção do guardrail (retry do grafo) é preservada — entra
        via `_mensagens`; o schema vem DEPOIS dela, como última mensagem `user`.

        Conserto dirigido (T-2505, rodada 3): se o JSON produzido não validar,
        faz UMA única chamada de correção antes de propagar. Com temperatura 0 o
        modelo é determinístico POR PROMPT, então o retry CEGO do grafo (o
        `except ValidationError` de `chamar_llm`, que reenvia SEM `correcao`)
        repetiria o mesmo JSON inválido byte a byte. Devolver ao modelo o JSON
        que ele mesmo produziu + os erros nomeados do Pydantic quebra esse
        determinismo na direção certa — mesmo princípio do retry-correção do
        ADR-0011, aplicado ao FORMATO em vez de aos números. Um conserto por
        chamada de `analisar` (sem loop); se ele também falhar, a exceção sobe e
        o grafo degrada com `REQ-LLM-002:SCHEMA` (honesto).
        """
        mensagens = _mensagens(fatos, correcao)
        mensagens.append({
            "role": "user",
            "content": _INSTRUCAO_JSON_OBJECT + json.dumps(schema_estrito()),
        })
        # `refinando`: o fallback de gramática NÃO é refino (mecânica interna,
        # transparente ao usuário — correção do revisor T-2603); só o retry do
        # guardrail (correcao) e o conserto dirigido abaixo contam como refino.
        conteudo = self._post_json_object(mensagens,
                                          refinando=correcao is not None)
        try:
            return AnaliseAgente.model_validate_json(conteudo)
        except ValidationError as e:
            mensagens.append({"role": "assistant", "content": conteudo})
            mensagens.append({"role": "user", "content": (
                "Seu JSON NÃO validou contra o schema. Erros:\n"
                + _resumo_erros_pydantic(e)
                + "\nDevolva SOMENTE o objeto JSON corrigido, completo, "
                "sem comentários."
            )})
            corrigido = self._post_json_object(mensagens, refinando=True)
            return AnaliseAgente.model_validate_json(corrigido)  # falha ⇒ propaga

    def analisar_com_correcao(self, fatos: FatosFinanceiros,
                              correcao: str) -> AnaliseAgente:
        return self.analisar(fatos, correcao)


def base_url_runtime_embarcado() -> str:
    """Sobe (lazy) o `llama-server` embarcado e devolve o endpoint loopback
    (`…/v1`), pronto para qualquer cliente OpenAI-compatible (ADR-0016 §E).

    Import TARDIO de `sidecar.runtime_llm`: o sidecar importa o agent, não o
    contrário — só tocamos o sidecar quando o caminho embarcado é de fato
    usado, evitando inverter a dependência de camadas no import. Reusado pela
    fábrica de provider (abaixo) e pelas de extração/classificação
    (`agent/extracao.py`/`agent/classificacao.py`, T-1702) — mesma
    precedência nos três fluxos. Se faltar binário/modelo, levanta
    `RuntimeLLMIndisponivel` (subclasse de `RuntimeError`); cada chamador
    decide como degradar (P8), mas nenhum deixa a exceção virar 500.

    Disciplina de troca de modelo (C-03): se a instância obtida já foi encerrada
    por um `POST /llm/modelo` concorrente (`RuntimeLLMInvalidado`), NÃO insiste
    nela — ressubiria o modelo ANTIGO e deixaria dois `llama-server` no ar.
    Re-obtém a instância ATUAL (já com o modelo novo) e tenta **uma única vez**;
    uma segunda invalidação (corrida patológica) propaga e degrada (P8).
    """
    from sidecar.runtime_llm import RuntimeLLMInvalidado, runtime_embarcado

    try:
        return runtime_embarcado().base_url()  # inicia sob demanda; loopback + porta efêmera
    except RuntimeLLMInvalidado:
        return runtime_embarcado().base_url()  # instância nova, modelo novo — 1 retry só


def _provider_runtime_embarcado(cfg: ConfigAgente) -> LLMProvider:
    """`OpenAICompatProvider` apontado ao endpoint do runtime embarcado."""
    return OpenAICompatProvider(replace(cfg, base_url=base_url_runtime_embarcado()))


def obter_provider(cfg: ConfigAgente) -> LLMProvider:
    """Fábrica: escolhe o provider conforme a configuração.

    ADR-0016 §E: com `provider="local"`, o runtime embarcado é o **padrão de
    fábrica** — MAS a ADR-0002 é preservada: se o usuário apontou um servidor
    próprio via `HF_BASE_URL` (Ollama/LM Studio), ele tem **precedência** e o
    embarcado nem inicia. Sem `HF_BASE_URL` e sem binário/modelo embarcado, a
    resolução levanta `RuntimeLLMIndisponivel` e o grafo degrada (P8).
    """
    if cfg.provider == "fake":
        return FakeProvider()
    if cfg.provider == "openai_compat":
        return OpenAICompatProvider(cfg)
    if cfg.provider == "local":
        if "HF_BASE_URL" in os.environ:
            return OllamaProvider(cfg)  # servidor do usuário tem precedência (ADR-0002)
        return _provider_runtime_embarcado(cfg)
    raise ValueError(f"Provider desconhecido: {cfg.provider}")
