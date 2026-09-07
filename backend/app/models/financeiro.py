"""Financeiro: contratos, cobranças e pagamentos.

Três níveis: o que foi contratado, o que foi cobrado, o que foi recebido.

"Vencida" NÃO é status — é consulta (`status IN ('aberta','parcial') AND
vence_em < CURRENT_DATE`). Persistir esse estado exigiria um job diário só para
mudar linha, e no dia em que ele falhasse a tela mentiria.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TIMESTAMPTZ, Base, IdMixin, PublicIdMixin, TimestampsMixin
from app.models.enums import (
    FORMA_PAGAMENTO,
    STATUS_COBRANCA,
    STATUS_CONTRATO,
    FormaPagamento,
    StatusCobranca,
    StatusContrato,
)


class Contrato(Base, IdMixin, PublicIdMixin, TimestampsMixin):
    """Mensalidade do paciente em um serviço.

    `valor_mensalidade_centavos` é CONGELADO na contratação: reajustar o serviço
    não reescreve o histórico de quem contratou por outro valor.
    """

    __tablename__ = "contratos"
    __table_args__ = (
        Index("ix_contratos_paciente_status", "paciente_id", "status"),
        Index("ix_contratos_clinica_status", "clinica_id", "status"),
        CheckConstraint("valor_mensalidade_centavos >= 0", name="valor_nao_negativo"),
        CheckConstraint("dia_vencimento BETWEEN 1 AND 31", name="dia_vencimento_valido"),
        CheckConstraint("fim_em IS NULL OR fim_em >= inicio_em", name="vigencia_valida"),
    )

    clinica_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clinicas.id", ondelete="CASCADE"), nullable=False
    )
    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pacientes.id", ondelete="RESTRICT"), nullable=False
    )
    servico_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servicos.id", ondelete="RESTRICT"), nullable=False
    )
    valor_mensalidade_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    # 1 a 31; quando o mês não tem o dia, a aplicação usa o último.
    dia_vencimento: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("10")
    )
    sessoes_por_semana: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[StatusContrato] = mapped_column(
        STATUS_CONTRATO, nullable=False, server_default=StatusContrato.ATIVO.value
    )
    inicio_em: Mapped[date] = mapped_column(Date, nullable=False)
    fim_em: Mapped[date | None] = mapped_column(Date)
    motivo_encerramento: Mapped[str | None] = mapped_column(String(200))
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )


class Cobranca(Base, IdMixin, PublicIdMixin, TimestampsMixin):
    """Uma linha por mês de competência de cada contrato.

    O índice único `(contrato_id, competencia)` é a defesa contra a falha mais
    provável do módulo: o job mensal rodar duas vezes e duplicar cobrança.

    `valor_pago_centavos` é mantido por trigger a partir de `pagamentos`.
    Materializar esse total evita agregado em toda listagem de inadimplência.
    """

    __tablename__ = "cobrancas"
    __table_args__ = (
        UniqueConstraint("contrato_id", "competencia"),
        Index("ix_cobrancas_clinica_vence", "clinica_id", "vence_em"),
        Index("ix_cobrancas_paciente_status", "paciente_id", "status"),
        Index("ix_cobrancas_status_vence", "status", "vence_em"),
        CheckConstraint("valor_centavos >= 0", name="valor_nao_negativo"),
        CheckConstraint("desconto_centavos >= 0", name="desconto_nao_negativo"),
        CheckConstraint("acrescimo_centavos >= 0", name="acrescimo_nao_negativo"),
        CheckConstraint("valor_pago_centavos >= 0", name="valor_pago_nao_negativo"),
    )

    clinica_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clinicas.id", ondelete="CASCADE"), nullable=False
    )
    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pacientes.id", ondelete="RESTRICT"), nullable=False
    )
    # Nulo = cobrança avulsa (sessão isolada, avaliação, taxa de matrícula).
    contrato_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contratos.id", ondelete="SET NULL")
    )
    competencia: Mapped[date | None] = mapped_column(Date)
    descricao: Mapped[str | None] = mapped_column(String(200))
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    desconto_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    acrescimo_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    valor_pago_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    vence_em: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[StatusCobranca] = mapped_column(
        STATUS_COBRANCA, nullable=False, server_default=StatusCobranca.ABERTA.value
    )
    quitada_em: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )


class Pagamento(Base, IdMixin, PublicIdMixin):
    """Recebimentos. Uma cobrança aceita vários — entrada mais saldo, parcial.

    Estorno preenche `estornado_em` em vez de deletar: histórico financeiro não
    se apaga.
    """

    __tablename__ = "pagamentos"
    __table_args__ = (
        Index("ix_pagamentos_cobranca_id", "cobranca_id"),
        Index("ix_pagamentos_pago_em", "pago_em"),
        CheckConstraint("valor_centavos >= 0", name="valor_nao_negativo"),
    )

    cobranca_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cobrancas.id", ondelete="RESTRICT"), nullable=False
    )
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    forma: Mapped[FormaPagamento] = mapped_column(
        FORMA_PAGAMENTO, nullable=False, server_default=FormaPagamento.PIX.value
    )
    pago_em: Mapped[date] = mapped_column(Date, nullable=False)
    observacoes: Mapped[str | None] = mapped_column(String(255))
    estornado_em: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    registrado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("now()")
    )
