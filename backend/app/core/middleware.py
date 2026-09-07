"""Middlewares transversais."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import definir_id_correlacao, obter_id_correlacao

CABECALHO_CORRELACAO = "X-Request-ID"

_logger_acesso = logging.getLogger("fisioagenda.acesso")


class CorrelacaoMiddleware(BaseHTTPMiddleware):
    """Dá a cada requisição um identificador e o devolve no cabeçalho da resposta.

    Aceita o identificador que o cliente enviar — útil para rastrear uma chamada
    do frontend até o log do backend — mas gera um novo quando não vier ou vier
    com formato inesperado, para que o valor nunca seja controlado por inteiro
    por quem chama.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        recebido = request.headers.get(CABECALHO_CORRELACAO, "")
        identificador = recebido if _e_identificador_aceitavel(recebido) else str(uuid.uuid4())
        definir_id_correlacao(identificador)

        inicio = time.perf_counter()
        resposta = await call_next(request)
        duracao_ms = (time.perf_counter() - inicio) * 1000

        resposta.headers[CABECALHO_CORRELACAO] = identificador
        _logger_acesso.info(
            "requisição concluída",
            extra={
                "metodo": request.method,
                "rota": request.url.path,
                "status": resposta.status_code,
                "duracao_ms": round(duracao_ms, 2),
            },
        )
        return resposta


def _e_identificador_aceitavel(valor: str) -> bool:
    # Limita tamanho e alfabeto: o valor vai para o log, e log não aceita
    # conteúdo arbitrário de terceiros.
    return 0 < len(valor) <= 64 and all(c.isalnum() or c in "-_" for c in valor)


__all__ = ["CABECALHO_CORRELACAO", "CorrelacaoMiddleware", "obter_id_correlacao"]
