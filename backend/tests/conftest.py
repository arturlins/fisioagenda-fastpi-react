"""Fixtures compartilhadas.

O loop de eventos precisa ser compatível com o psycopg antes de qualquer teste
criar conexão — ver `app.core.plataforma`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.plataforma import configurar_loop_de_eventos

configurar_loop_de_eventos()


@pytest.fixture
def app() -> FastAPI:
    from app.main import criar_app

    return criar_app()


@pytest.fixture
async def cliente(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente que fala com a aplicação em memória, sem porta nem servidor."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://teste") as cliente:
        yield cliente
