"""Base declarativa e mixins comuns às entidades.

A convenção de nomes de constraint não é cosmética: sem ela o SQLAlchemy deixa
o Postgres nomear índices e chaves, e o Alembic passa a gerar migrations que
tentam remover constraints cujo nome ele não sabe reproduzir.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# O esquema exige timestamptz em toda data absoluta. O mapeamento padrão de
# `datetime` é TIMESTAMP WITHOUT TIME ZONE — precisa ser dito explicitamente.
TIMESTAMPTZ = DateTime(timezone=True)

CONVENCAO_NOMES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_NOMES)


class PublicIdMixin:
    """Identificador público.

    O `id` bigint é interno e nunca aparece em rota ou payload; o `public_id` é o
    único identificador exposto (ADR-007). O default é do servidor, via
    `gen_random_uuid()` do pgcrypto, para que uma inserção feita fora da
    aplicação também receba um valor válido.
    """

    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )


class TimestampsMixin:
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ,
        server_default=text("now()"),
        nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ,
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )


class SoftDeleteMixin:
    """Exclusão lógica, só onde há histórico a preservar (usuarios, pacientes, servicos)."""

    excluido_em: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)

    @property
    def excluido(self) -> bool:
        return self.excluido_em is not None
