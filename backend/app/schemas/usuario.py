"""DTOs de usuário.

O que sai daqui é o contrato público da API. `id` interno e `keycloak_id` nunca
aparecem: o primeiro é enumerável (ADR-007), o segundo é detalhe de como a
autenticação foi implementada e não interessa a quem consome a API.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.models.enums import PapelUsuario

# A política do realm exige 10 caracteres. Validar aqui devolve 422 com o campo
# apontado, em vez de um 502 vindo do Keycloak lá na frente.
SENHA_TAMANHO_MINIMO = 10


class CriarUsuarioRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr = Field(max_length=150)
    senha: SecretStr = Field(min_length=SENHA_TAMANHO_MINIMO, max_length=128)
    telefone: str | None = Field(default=None, max_length=20)
    e_profissional: bool = True
    registro_conselho: str | None = Field(default=None, max_length=30)
    especialidade: str | None = Field(default=None, max_length=120)
    cor_agenda: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class AtualizarUsuarioRequest(BaseModel):
    """PUT substitui o recurso: todo campo editável vem no corpo.

    `senha` fica de fora de propósito — trocar senha é operação do Keycloak, com
    fluxo próprio, e não deve viajar junto de uma edição de cadastro.
    """

    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr = Field(max_length=150)
    telefone: str | None = Field(default=None, max_length=20)
    e_profissional: bool = True
    registro_conselho: str | None = Field(default=None, max_length=30)
    especialidade: str | None = Field(default=None, max_length=120)
    cor_agenda: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    ativo: bool = True


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    nome: str
    email: EmailStr
    telefone: str | None
    e_profissional: bool
    registro_conselho: str | None
    especialidade: str | None
    cor_agenda: str | None
    dono_da_conta: bool
    ativo: bool
    criado_em: datetime


class VinculoClinicaResponse(BaseModel):
    """Onde o usuário atua e com qual privilégio."""

    clinica_public_id: UUID
    clinica_nome: str
    papel: PapelUsuario
    ativo: bool


class PerfilResponse(BaseModel):
    """Resposta de `GET /auth/eu`: quem sou e o que posso."""

    usuario: UsuarioResponse
    vinculos: list[VinculoClinicaResponse]


class PaginaDeUsuarios(BaseModel):
    itens: list[UsuarioResponse]
    total: int
    pagina: int
    tamanho: int
