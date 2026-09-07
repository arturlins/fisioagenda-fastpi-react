"""Agenda: turmas, agendamentos e participações.

Não existe tabela "agenda". Agenda é sempre um filtro sobre `agendamentos` —
por clínica, por serviço ou por profissional. Tabelas separadas duplicariam
estado e obrigariam a manter sincronia entre elas.

A turma é um MOLDE: os agendamentos são materializados a partir dela numa janela
rolante de ~8 semanas. Cancelar um agendamento isolado não altera a turma — é o
comportamento esperado quando um feriado cai numa quarta.
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TIMESTAMPTZ, Base, IdMixin, PublicIdMixin, TimestampsMixin
from app.models.enums import (
    STATUS_AGENDAMENTO,
    STATUS_PARTICIPACAO,
    StatusAgendamento,
    StatusParticipacao,
)


class Turma(Base, IdMixin, PublicIdMixin, TimestampsMixin):
    __tablename__ = "turmas"
    __table_args__ = (
        Index("ix_turmas_clinica_ativa", "clinica_id", "ativa"),
        CheckConstraint("duracao_minutos > 0", name="duracao_positiva"),
        CheckConstraint("capacidade > 0", name="capacidade_positiva"),
        CheckConstraint("fim_em IS NULL OR fim_em >= inicio_em", name="vigencia_valida"),
    )

    clinica_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clinicas.id", ondelete="CASCADE"), nullable=False
    )
    servico_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servicos.id", ondelete="RESTRICT"), nullable=False
    )
    profissional_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    nome: Mapped[str | None] = mapped_column(String(120))
    # Ex.: {1,3} = segunda e quarta. Se o ORM algum dia atrapalhar, o esquema já
    # prevê a tabela filha `turma_dias` como alternativa.
    dias_semana: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    duracao_minutos: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    capacidade: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    inicio_em: Mapped[date] = mapped_column(Date, nullable=False)
    fim_em: Mapped[date | None] = mapped_column(Date)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    criado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )


class TurmaAluno(Base, IdMixin, PublicIdMixin):
    """Matrícula na turma — vínculo de AGENDA.

    O vínculo financeiro é o contrato, separado de propósito: o aluno pode sair
    da turma e continuar devendo, ou trocar de horário sem mexer na mensalidade.
    """

    __tablename__ = "turma_alunos"
    __table_args__ = (
        UniqueConstraint("turma_id", "paciente_id"),
        Index("ix_turma_alunos_paciente_id", "paciente_id"),
        CheckConstraint("saiu_em IS NULL OR saiu_em >= entrou_em", name="periodo_valido"),
    )

    turma_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turmas.id", ondelete="CASCADE"), nullable=False
    )
    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False
    )
    entrou_em: Mapped[date] = mapped_column(Date, nullable=False)
    saiu_em: Mapped[date | None] = mapped_column(Date)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("now()")
    )


class Agendamento(Base, IdMixin, PublicIdMixin, TimestampsMixin):
    """A unidade da agenda: um horário, um profissional, um serviço, uma clínica.

    `turma_id` nulo = avulso; preenchido = materializado a partir da turma. Os
    dois formatos convivem na mesma tabela e na mesma agenda.

    Remarcação é um par de ponteiros (`remarcado_de_id` / `remarcado_para_id`),
    o que preserva a cadeia inteira sem tabela de auditoria.

    Conflito de horário NÃO é resolvido aqui: a constraint de exclusão criada na
    migration 0002 é que garante isso, porque validação em código falha sob
    concorrência — duas requisições simultâneas veem o horário livre e inserem.
    """

    __tablename__ = "agendamentos"
    __table_args__ = (
        Index("ix_agendamentos_clinica_inicio", "clinica_id", "inicio_em"),
        Index("ix_agendamentos_profissional_inicio", "profissional_id", "inicio_em"),
        Index("ix_agendamentos_servico_inicio", "servico_id", "inicio_em"),
        Index("ix_agendamentos_turma_inicio", "turma_id", "inicio_em"),
        Index("ix_agendamentos_status", "status"),
        CheckConstraint("fim_em > inicio_em", name="intervalo_valido"),
        CheckConstraint("capacidade > 0", name="capacidade_positiva"),
    )

    clinica_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clinicas.id", ondelete="CASCADE"), nullable=False
    )
    servico_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servicos.id", ondelete="RESTRICT"), nullable=False
    )
    profissional_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    turma_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("turmas.id", ondelete="SET NULL")
    )
    inicio_em: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    fim_em: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    capacidade: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    status: Mapped[StatusAgendamento] = mapped_column(
        STATUS_AGENDAMENTO, nullable=False, server_default=StatusAgendamento.AGENDADO.value
    )

    remarcado_de_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agendamentos.id", ondelete="SET NULL")
    )
    remarcado_para_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agendamentos.id", ondelete="SET NULL")
    )
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(255))
    cancelado_em: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    cancelado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_por_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="SET NULL")
    )


class AgendamentoPaciente(Base, IdMixin, PublicIdMixin, TimestampsMixin):
    """Participação do paciente. Individual = 1 linha; turma = N linhas.

    Os dois níveis de status existem por necessidade: numa turma de seis, cinco
    comparecem e um falta. Com status único no agendamento esse caso não se
    representa.
    """

    __tablename__ = "agendamento_pacientes"
    __table_args__ = (
        UniqueConstraint("agendamento_id", "paciente_id"),
        Index("ix_agendamento_pacientes_paciente_criado", "paciente_id", "criado_em"),
        Index("ix_agendamento_pacientes_contrato_id", "contrato_id"),
        Index("ix_agendamento_pacientes_status", "status"),
    )

    agendamento_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agendamentos.id", ondelete="CASCADE"), nullable=False
    )
    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pacientes.id", ondelete="RESTRICT"), nullable=False
    )
    # Nulo = sessão avulsa, cobrada à parte.
    contrato_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contratos.id", ondelete="SET NULL")
    )
    status: Mapped[StatusParticipacao] = mapped_column(
        STATUS_PARTICIPACAO, nullable=False, server_default=StatusParticipacao.AGENDADO.value
    )
    # Permite que UM aluno da turma reponha em outro horário sem afetar os demais.
    remarcado_para_agendamento_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agendamentos.id", ondelete="SET NULL")
    )
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(255))
    chegou_em: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
