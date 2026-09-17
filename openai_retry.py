"""Retry com backoff curto para as chamadas à API da OpenAI.

Mesma motivação do retry do Telegram em bot.py: um engasgo transitório
(rate limit, timeout, conexão, 5xx) não deve derrubar a demo. Só erros
transitórios são repetidos; erro de credencial ou de parsing sobe na hora
para o fallback do próprio módulo (GUIADO / FORA_DE_ESCOPO / nao_entendi).
"""

import logging
import time

import openai

log = logging.getLogger("openai_retry")

# Transitórios: vale tentar de novo. Ficam de fora, de propósito:
# AuthenticationError (credencial errada — retry não resolve) e erros de
# parsing/validação (levantados DEPOIS da chamada, no código do módulo).
ERROS_TRANSITORIOS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)

ESPERAS_PADRAO = (1, 2)  # segundos entre tentativas: 1s, depois 2s


def com_retry(fn, *, contexto: str, esperas=ESPERAS_PADRAO):
    """Executa fn() repetindo em erro transitório da OpenAI.

    São len(esperas)+1 tentativas no total (padrão: 3 = 1 + 2 retries).
    Depois da última, a exceção sobe para o fallback do módulo. Loga em
    INFO cada retry e a desistência final — sem credencial nem conteúdo,
    só o tipo do erro — pra distinguir depois "fallback direto" de
    "fallback após esgotar os retries"."""
    total = len(esperas) + 1
    for i in range(total):
        try:
            return fn()
        except ERROS_TRANSITORIOS as e:
            if i == total - 1:
                log.info("%s: erro transitório %s persistiu após %d "
                         "tentativas — caindo no fallback",
                         contexto, type(e).__name__, total)
                raise
            log.info("%s: erro transitório %s (tentativa %d/%d) — repetindo "
                     "após %ss", contexto, type(e).__name__, i + 1, total,
                     esperas[i])
            time.sleep(esperas[i])
