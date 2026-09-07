"""Acesso: usuários e o vínculo deles com cada clínica.

Não existe `senha_hash` (ADR-001): a credencial vive no Keycloak, e o elo entre
os dois sistemas é o `keycloak_id`, que é o `sub` do JWT.

O papel é POR CLÍNICA, não global — é o que permite a mesma pessoa administrar
uma unidade e ser usuária comum em outra.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TIMESTAMPTZ, Base, IdMixin, PublicIdMixin, SoftDeleteMixin, TimestampsMixin
from app.models.enums import PAPEL_USUARIO, PapelUsuario
from app.models.organizacao import Clinica


class Usuario(Base, IdMixin, PublicIdMixin, TimestampsMixin, SoftDeleteMixin):
    """Login do sistema. Profissional e apoio na mesma tabela.

    Só quem tem `e_profissional` recebe agendamentos. Os campos de profissional
    ficam aqui mesmo, nulos para os demais: uma tabela separada custaria um JOIN
    em toda renderização de agenda e não paga o preço nesse volume.
    """

    __tablename__ = "usuarios"
    __table_args__ = (UniqueConstraint("conta_id", "email"),)

    conta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False
    )
    # Elo com o Keycloak: é o `sub` do token. Sem ele não há como resolver o
    # portador do JWT para um usuário do domínio.
    keycloak_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    telefone: Mapped[str | None] = mapped_column(String(20))

    e_profissional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    registro_conselho: Mapped[str | None] = mapped_column(String(30))
    especialidade: Mapped[str | None] = mapped_column(String(120))
    cor_agenda: Mapped[str | None] = mapped_column(CHAR(7))

    dono_da_conta: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    ultimo_login_em: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)

    # lazy="raise": em código assíncrono, carga preguiçosa silenciosa vira erro
    # de runtime no meio da serialização. Melhor exigir eager explícito.
    vinculos: Mapped[list[ClinicaUsuario]] = relationship(
        back_populates="usuario", lazy="raise", cascade="all, delete-orphan"
    )


class ClinicaUsuario(Base, IdMixin, PublicIdMixin):
    """Vínculo com a clínica e o privilégio nela.

    Responde à pergunta "esse usuário pode ver essa agenda?".
    """

    __tablename__ = "clinica_usuarios"
    __table_args__ = (
        UniqueConstraint("clinica_id", "usuario_id"),
        Index("ix_clinica_usuarios_usuario_id", "usuario_id"),
    )

    clinica_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clinicas.id", ondelete="CASCADE"), nullable=False
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    papel: Mapped[PapelUsuario] = mapped_column(
        PAPEL_USUARIO, nullable=False, server_default=PapelUsuario.COMUM.value
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("now()")
    )

    usuario: Mapped[Usuario] = relationship(back_populates="vinculos", lazy="raise")
    clinica: Mapped[Clinica] = relationship(lazy="raise")
