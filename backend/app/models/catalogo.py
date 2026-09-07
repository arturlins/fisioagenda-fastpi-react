"""Catálogo: serviços da conta e a habilitação de cada profissional.

Os preços aqui são tabela de referência. O valor efetivamente cobrado fica
congelado em `contratos.valor_mensalidade_centavos` — reajustar o serviço não
pode reescrever o histórico de quem contratou por outro valor.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TIMESTAMPTZ, Base, IdMixin, PublicIdMixin, SoftDeleteMixin, TimestampsMixin
from app.models.enums import MODALIDADE_SERVICO, ModalidadeServico


class Servico(Base, IdMixin, PublicIdMixin, TimestampsMixin, SoftDeleteMixin):
    __tablename__ = "servicos"
    __table_args__ = (
        UniqueConstraint("conta_id", "nome"),
        # Dinheiro em centavos, nunca negativo.
        CheckConstraint(
            "preco_mensalidade_centavos IS NULL OR preco_mensalidade_centavos >= 0",
            name="preco_mensalidade_nao_negativo",
        ),
        CheckConstraint(
            "preco_sessao_centavos IS NULL OR preco_sessao_centavos >= 0",
            name="preco_sessao_nao_negativo",
        ),
        CheckConstraint("duracao_minutos > 0", name="duracao_positiva"),
        CheckConstraint("capacidade_padrao > 0", name="capacidade_positiva"),
    )

    conta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    modalidade: Mapped[ModalidadeServico] = mapped_column(
        MODALIDADE_SERVICO, nullable=False, server_default=ModalidadeServico.INDIVIDUAL.value
    )
    duracao_minutos: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("50")
    )
    capacidade_padrao: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    preco_mensalidade_centavos: Mapped[int | None] = mapped_column(Integer)
    preco_sessao_centavos: Mapped[int | None] = mapped_column(Integer)
    cor: Mapped[str] = mapped_column(CHAR(7), nullable=False, server_default="#3B82F6")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class ProfissionalServico(Base, IdMixin, PublicIdMixin):
    """Habilitação: impede escalar alguém para um serviço que não atende."""

    __tablename__ = "profissional_servicos"
    __table_args__ = (UniqueConstraint("usuario_id", "servico_id"),)

    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    servico_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servicos.id", ondelete="CASCADE"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("now()")
    )
