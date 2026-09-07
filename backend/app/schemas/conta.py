"""DTOs de conta e do registro inicial."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.schemas.usuario import SENHA_TAMANHO_MINIMO, UsuarioResponse


class RegistroContaRequest(BaseModel):
    """Cria a conta e o primeiro usuário, que nasce dono.

    É a única rota pública da API. Daqui em diante, todo usuário é criado por
    quem já está dentro — sistema interno não tem cadastro aberto.
    """

    nome_conta: str = Field(min_length=2, max_length=150, examples=["Clínica Movimento"])
    cnpj: str | None = Field(default=None, pattern=r"^\d{14}$", examples=["12345678000199"])
    nome_responsavel: str = Field(min_length=2, max_length=150, examples=["Ana Ribeiro"])
    email: EmailStr = Field(max_length=150, examples=["ana@clinicamovimento.com.br"])
    senha: SecretStr = Field(min_length=SENHA_TAMANHO_MINIMO, max_length=128)


class ContaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    nome: str
    cnpj: str | None
    ativa: bool
    criado_em: datetime


class RegistroContaResponse(BaseModel):
    conta: ContaResponse
    usuario: UsuarioResponse
