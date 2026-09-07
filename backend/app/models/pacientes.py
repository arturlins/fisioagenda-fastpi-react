"""Pacientes e prontuário.

O paciente pertence à CONTA e é compartilhado entre as clínicas: quem faz
pilates numa unidade e fisioterapia em outra é uma pessoa só, com um prontuário
só. Sem senha, sem token, sem sessão — o paciente não acessa o sistema.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TIMESTAMPTZ, Base, IdMixin, PublicIdMixin, SoftDeleteMixin, TimestampsMixin
from app.models.enums import (
    GRAVIDADE_PONTO_ATENCAO,
    TIPO_EVOLUCAO,
    GravidadePontoAtencao,
    TipoEvolucao,
)


class Paciente(Base, IdMixin, PublicIdMixin, TimestampsMixin, SoftDeleteMixin):
    __tablename__ = "pacientes"
    __table_args__ = (
        UniqueConstraint("conta_id", "cpf"),
        Index("ix_pacientes_conta_nome", "conta_id", "nome"),
    )

    conta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    sexo: Mapped[str | None] = mapped_column(String(20))
    cpf: Mapped[str | None] = mapped_column(String(11))
    telefone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(150))
    endereco: Mapped[str | None] = mapped_column(String(255))
    cidade: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(CHAR(2))
    contato_emergencia_nome: Mapped[str | None] = mapped_column(String(150))
    contato_emergencia_telefone: Mapped[str | None] = mapped_column(String(20))
    profissao: Mapped[str | None] = mapped_column(String(120))
    encaminhado_por: Mapped[str | None] = mapped_column(String(150))
    observacoes: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    criado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )


class PontoAtencao(Base, IdMixin, PublicIdMixin):
    """Alertas PERSISTENTES do paciente, exibidos antes de todo atendimento.

    Não confundir com o campo `pontos_atencao` de `evolucoes`, que é a observação
    daquela sessão. Aqui é o que vale para sempre; lá é o que aconteceu no dia.
    """

    __tablename__ = "pontos_atencao"
    __table_args__ = (Index("ix_pontos_atencao_paciente_ativo", "paciente_id", "ativo"),)

    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False
    )
    gravidade: Mapped[GravidadePontoAtencao] = mapped_column(
        GRAVIDADE_PONTO_ATENCAO,
        nullable=False,
        server_default=GravidadePontoAtencao.ATENCAO.value,
    )
    titulo: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    criado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    resolvido_em: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("now()")
    )


class Evolucao(Base, IdMixin, PublicIdMixin, TimestampsMixin):
    """Ficha de evolução, em estrutura próxima ao SOAP.

    `agendamento_paciente_id` é único e nullable: uma evolução por participação
    do paciente num atendimento; nulo é anotação fora de atendimento.

    `assinado_em` fecha o registro. A partir daí a aplicação trata como imutável
    — prontuário não se edita, se retifica.
    """

    __tablename__ = "evolucoes"
    __table_args__ = (
        Index("ix_evolucoes_paciente_realizado", "paciente_id", "realizado_em"),
        Index("ix_evolucoes_profissional_realizado", "profissional_id", "realizado_em"),
        CheckConstraint(
            "escala_dor IS NULL OR escala_dor BETWEEN 0 AND 10", name="escala_dor_valida"
        ),
    )

    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False
    )
    agendamento_paciente_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agendamento_pacientes.id", ondelete="SET NULL"),
        unique=True,
    )
    profissional_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    tipo: Mapped[TipoEvolucao] = mapped_column(
        TIPO_EVOLUCAO, nullable=False, server_default=TipoEvolucao.EVOLUCAO.value
    )
    realizado_em: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)

    queixa: Mapped[str | None] = mapped_column(Text)
    avaliacao: Mapped[str | None] = mapped_column(Text)
    conduta: Mapped[str | None] = mapped_column(Text)
    evolucao: Mapped[str | None] = mapped_column(Text)
    pontos_atencao: Mapped[str | None] = mapped_column(Text)
    plano_proxima_sessao: Mapped[str | None] = mapped_column(Text)
    escala_dor: Mapped[int | None] = mapped_column(SmallInteger)
    assinado_em: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
