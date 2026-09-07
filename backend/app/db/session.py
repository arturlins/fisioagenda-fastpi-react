"""Engine e sessão do SQLAlchemy.

A unidade de trabalho é a requisição, não o método de repositório (ADR-004):
`obter_sessao` faz commit ao fim de uma requisição bem-sucedida e rollback em
qualquer exceção. Repositório só faz `add` / `flush` / `refresh`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import obter_configuracao


@lru_cache
def obter_engine() -> AsyncEngine:
    config = obter_configuracao()
    return create_async_engine(
        config.banco_url,
        echo=config.banco_echo,
        pool_size=config.banco_pool_tamanho,
        max_overflow=config.banco_pool_overflow,
        # Conexão pode morrer sem aviso (restart do container, timeout de rede).
        # Sem isso, a primeira requisição depois disso falha com erro obscuro.
        pool_pre_ping=True,
    )


@lru_cache
def obter_fabrica_sessao() -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: depois do commit ainda precisamos ler os atributos
    # da entidade para montar o DTO de resposta.
    return async_sessionmaker(obter_engine(), expire_on_commit=False, autoflush=False)


async def obter_sessao() -> AsyncIterator[AsyncSession]:
    """Dependência de sessão. Commit no sucesso, rollback em qualquer falha."""
    async with obter_fabrica_sessao()() as sessao:
        try:
            yield sessao
        except Exception:
            await sessao.rollback()
            raise
        else:
            await sessao.commit()


async def encerrar_engine() -> None:
    """Fecha o pool. Chamado no encerramento da aplicação."""
    if obter_engine.cache_info().currsize:
        await obter_engine().dispose()
        obter_engine.cache_clear()
        obter_fabrica_sessao.cache_clear()
