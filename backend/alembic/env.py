"""Ambiente do Alembic.

A URL do banco vem da configuração da aplicação, não do `alembic.ini`: senha em
arquivo versionado seria um vazamento por descuido.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from alembic import context
from app.core.config import obter_configuracao
from app.core.plataforma import configurar_loop_de_eventos
from app.db.base import Base

# Importa os models para popular o metadata. Sem isso o autogenerate acha que
# todas as tabelas foram removidas.
import app.models  # noqa: F401  # isort: skip

# O psycopg assíncrono não roda sobre o ProactorEventLoop do Windows; aqui o
# loop é criado por `asyncio.run`, então a política resolve.
configurar_loop_de_eventos()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url_do_banco() -> str:
    return obter_configuracao().banco_url


def run_migrations_offline() -> None:
    """Gera SQL sem conectar — útil para revisar a migration antes de aplicar."""
    context.configure(
        url=_url_do_banco(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _executar_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Sem isso, mudança de tipo e de default passa despercebida pelo
        # autogenerate e o banco silenciosamente diverge dos models.
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuracao_secao = config.get_section(config.config_ini_section, {})
    configuracao_secao["sqlalchemy.url"] = _url_do_banco()

    engine = async_engine_from_config(configuracao_secao, prefix="sqlalchemy.", poolclass=NullPool)

    async with engine.connect() as conexao:
        await conexao.run_sync(_executar_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
