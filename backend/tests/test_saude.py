"""Endpoints operacionais e correlação de requisição.

Liveness não toca em dependência: liveness que depende de infraestrutura não é
liveness. A prontidão, que depende, é coberta na verificação de integração.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.core.middleware import CABECALHO_CORRELACAO


async def test_saude_responde_ok(cliente: AsyncClient) -> None:
    resposta = await cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


async def test_correlacao_gerada_quando_cliente_nao_envia(cliente: AsyncClient) -> None:
    resposta = await cliente.get("/saude")

    assert uuid.UUID(resposta.headers[CABECALHO_CORRELACAO])


async def test_correlacao_do_cliente_e_preservada(cliente: AsyncClient) -> None:
    resposta = await cliente.get("/saude", headers={CABECALHO_CORRELACAO: "rastro-do-frontend-1"})

    assert resposta.headers[CABECALHO_CORRELACAO] == "rastro-do-frontend-1"


async def test_correlacao_invalida_e_substituida(cliente: AsyncClient) -> None:
    """O valor vai para o log — não pode ser conteúdo arbitrário de terceiros."""
    resposta = await cliente.get(
        "/saude", headers={CABECALHO_CORRELACAO: "quebra\tde;log " + "x" * 90}
    )

    assert uuid.UUID(resposta.headers[CABECALHO_CORRELACAO])
