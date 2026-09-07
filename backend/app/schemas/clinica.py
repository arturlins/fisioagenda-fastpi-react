"""DTOs de clínica e do vínculo com usuários."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import PapelUsuario


def _validar_fuso(valor: str) -> str:
    """O fuso não é enfeite: é ele que converte o horário da grade semanal
    (`time`) em instante absoluto (`timestamptz`) na materialização da agenda.
    Um valor inválido só apareceria como agendamento na hora errada."""
    if valor not in available_timezones():
        raise ValueError(f"Fuso horário desconhecido: {valor}")
    return valor


class CriarClinicaRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=150, examples=["Unidade Centro"])
    fuso_horario: str = Field(default="America/Maceio", max_length=64)
    telefone: str | None = Field(default=None, max_length=20)
    endereco: str | None = Field(default=None, max_length=255)
    cidade: str | None = Field(default=None, max_length=100)
    uf: str | None = Field(default=None, pattern=r"^[A-Z]{2}$", examples=["AL"])

    _fuso = field_validator("fuso_horario")(_validar_fuso)


class AtualizarClinicaRequest(CriarClinicaRequest):
    ativa: bool = True


class ClinicaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    nome: str
    fuso_horario: str
    telefone: str | None
    endereco: str | None
    cidade: str | None
    uf: str | None
    ativa: bool
    criado_em: datetime


class VincularUsuarioRequest(BaseModel):
    usuario_public_id: UUID
    papel: PapelUsuario = PapelUsuario.COMUM


class AtualizarVinculoRequest(BaseModel):
    papel: PapelUsuario
    ativo: bool = True


class VinculoResponse(BaseModel):
    """Quem atua nesta clínica e com qual privilégio."""

    usuario_public_id: UUID
    usuario_nome: str
    usuario_email: str
    papel: PapelUsuario
    ativo: bool
