"""Organização: contas e clínicas.

`contas` é o tenant raiz — clínicas, usuários, serviços e pacientes pendem dela.
Toda consulta do sistema é escopada por conta.
"""

from __future__ import annotations

from sqlalchemy import CHAR, BigInteger, Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, PublicIdMixin, TimestampsMixin


class Conta(Base, IdMixin, PublicIdMixin, TimestampsMixin):
    __tablename__ = "contas"

    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(14))
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Clinica(Base, IdMixin, PublicIdMixin, TimestampsMixin):
    """Unidade física. É o escopo natural da agenda.

    `fuso_horario` converte os horários de grade semanal (`time`) em instantes
    absolutos (`timestamptz`) na materialização dos agendamentos.
    """

    __tablename__ = "clinicas"
    __table_args__ = (UniqueConstraint("conta_id", "nome"),)

    conta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    fuso_horario: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="America/Maceio"
    )
    telefone: Mapped[str | None] = mapped_column(String(20))
    endereco: Mapped[str | None] = mapped_column(String(255))
    cidade: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(CHAR(2))
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
