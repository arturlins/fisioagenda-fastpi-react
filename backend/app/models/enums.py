"""Enums do domínio, espelhando os tipos nativos do PostgreSQL.

Os valores gravados no banco são exatamente os do `fisioagenda_mvp.dbml`. Por
isso todo enum usa `values_callable`: sem ele o SQLAlchemy grava o *nome* do
membro (`ADMINISTRADOR`), não o valor (`administrador`).
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as EnumSQL


class PapelUsuario(StrEnum):
    ADMINISTRADOR = "administrador"
    COMUM = "comum"


class ModalidadeServico(StrEnum):
    INDIVIDUAL = "individual"
    GRUPO = "grupo"


class StatusAgendamento(StrEnum):
    """Status do HORÁRIO. O status por paciente vive em `agendamento_pacientes`."""

    AGENDADO = "agendado"
    CONFIRMADO = "confirmado"
    REALIZADO = "realizado"
    CANCELADO = "cancelado"
    REMARCADO = "remarcado"
    FALTA_PROFISSIONAL = "falta_profissional"


class StatusParticipacao(StrEnum):
    """Status por paciente. Numa turma de seis, cinco presentes e um faltoso."""

    AGENDADO = "agendado"
    CONFIRMADO = "confirmado"
    PRESENTE = "presente"
    FALTA_PACIENTE = "falta_paciente"
    CANCELADO = "cancelado"
    REMARCADO = "remarcado"


class TipoEvolucao(StrEnum):
    AVALIACAO = "avaliacao"
    EVOLUCAO = "evolucao"
    REAVALIACAO = "reavaliacao"
    ALTA = "alta"
    ANOTACAO = "anotacao"


class GravidadePontoAtencao(StrEnum):
    INFO = "info"
    ATENCAO = "atencao"
    CRITICO = "critico"


class TipoBloqueio(StrEnum):
    FERIAS = "ferias"
    FERIADO = "feriado"
    LICENCA = "licenca"
    PESSOAL = "pessoal"
    CLINICA_FECHADA = "clinica_fechada"
    OUTRO = "outro"


class StatusContrato(StrEnum):
    ATIVO = "ativo"
    SUSPENSO = "suspenso"
    ENCERRADO = "encerrado"


class StatusCobranca(StrEnum):
    ABERTA = "aberta"
    PARCIAL = "parcial"
    PAGA = "paga"
    CANCELADA = "cancelada"


class FormaPagamento(StrEnum):
    DINHEIRO = "dinheiro"
    PIX = "pix"
    DEBITO = "debito"
    CREDITO = "credito"
    TRANSFERENCIA = "transferencia"
    OUTRO = "outro"


def enum_nativo[T: StrEnum](enum: type[T], nome: str) -> EnumSQL:
    """Tipo enum nativo do PostgreSQL, gravando o valor do membro."""
    return EnumSQL(
        enum,
        name=nome,
        native_enum=True,
        values_callable=lambda e: [membro.value for membro in e],
    )


PAPEL_USUARIO = enum_nativo(PapelUsuario, "papel_usuario")
MODALIDADE_SERVICO = enum_nativo(ModalidadeServico, "modalidade_servico")
STATUS_AGENDAMENTO = enum_nativo(StatusAgendamento, "status_agendamento")
STATUS_PARTICIPACAO = enum_nativo(StatusParticipacao, "status_participacao")
TIPO_EVOLUCAO = enum_nativo(TipoEvolucao, "tipo_evolucao")
GRAVIDADE_PONTO_ATENCAO = enum_nativo(GravidadePontoAtencao, "gravidade_ponto_atencao")
TIPO_BLOQUEIO = enum_nativo(TipoBloqueio, "tipo_bloqueio")
STATUS_CONTRATO = enum_nativo(StatusContrato, "status_contrato")
STATUS_COBRANCA = enum_nativo(StatusCobranca, "status_cobranca")
FORMA_PAGAMENTO = enum_nativo(FormaPagamento, "forma_pagamento")
