"""Disponibilidade: grade semanal e bloqueios.

A grade serve para a interface montar os horários; não é validação rígida — a
recepção pode encaixar fora dela quando precisa.
"""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TIMESTAMPTZ, Base, IdMixin, PublicIdMixin
from app.models.enums import TIPO_BLOQUEIO, TipoBloqueio


class HorarioProfissional(Base, IdMixin, PublicIdMixin):
    """Mais de uma linha por dia cobre intervalo de almoço."""

    __tablename__ = "horarios_profissional"
    __table_args__ = (
        Index(
            "ix_horarios_profissional_clinica_usuario_dia", "clinica_id", "usuario_id", "dia_semana"
        ),
        CheckConstraint("dia_semana BETWEEN 0 AND 6", name="dia_semana_valido"),
        CheckConstraint("hora_fim > hora_inicio", name="intervalo_valido"),
    )

    clinica_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clinicas.id", ondelete="CASCADE"), nullable=False
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    dia_semana: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fim: Mapped[time] = mapped_column(Time, nullable=False)


class BloqueioAgenda(Base, IdMixin, PublicIdMixin):
    """Ausências e indisponibilidades.

    `usuario_id` nulo é bloqueio da clínica inteira — feriado, reforma. Esse
    único campo nullable evita duas tabelas quase idênticas.
    """

    __tablename__ = "bloqueios_agenda"
    __table_args__ = (
        Index("ix_bloqueios_agenda_clinica_inicio", "clinica_id", "inicio_em"),
        Index("ix_bloqueios_agenda_usuario_inicio", "usuario_id", "inicio_em"),
        CheckConstraint("fim_em > inicio_em", name="intervalo_valido"),
    )

    clinica_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clinicas.id", ondelete="CASCADE"), nullable=False
    )
    usuario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE")
    )
    tipo: Mapped[TipoBloqueio] = mapped_column(
        TIPO_BLOQUEIO, nullable=False, server_default=TipoBloqueio.OUTRO.value
    )
    inicio_em: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    fim_em: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(200))
    criado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("now()")
    )
