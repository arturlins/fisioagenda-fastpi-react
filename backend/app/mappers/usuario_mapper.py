"""Mapper de usuário: entidade ⇄ DTO.

Funções puras, sem lógica de negócio e sem tocar no banco — exatamente o papel
do `AccountMapper` do projeto da aula. Se aqui aparecer um `if` que decide algo,
a regra está no lugar errado.
"""

from __future__ import annotations

import uuid

from app.models.acesso import ClinicaUsuario, Usuario
from app.schemas.usuario import (
    AtualizarUsuarioRequest,
    CriarUsuarioRequest,
    PerfilResponse,
    UsuarioResponse,
    VinculoClinicaResponse,
)


def de_criar_request(dto: CriarUsuarioRequest, *, conta_id: int, keycloak_id: uuid.UUID) -> Usuario:
    """`conta_id` e `keycloak_id` vêm de fora: um do contexto autenticado, o
    outro do Keycloak. Nenhum dos dois é escolha do cliente."""
    return Usuario(
        conta_id=conta_id,
        keycloak_id=keycloak_id,
        nome=dto.nome,
        email=str(dto.email),
        telefone=dto.telefone,
        e_profissional=dto.e_profissional,
        registro_conselho=dto.registro_conselho,
        especialidade=dto.especialidade,
        cor_agenda=dto.cor_agenda,
        dono_da_conta=False,
    )


def aplicar_atualizacao(usuario: Usuario, dto: AtualizarUsuarioRequest) -> Usuario:
    """Copia os campos editáveis para a entidade já carregada.

    `dono_da_conta`, `conta_id` e `keycloak_id` não estão aqui: nenhum é editável
    por requisição — quem se autopromovesse a dono teria a conta inteira.
    """
    usuario.nome = dto.nome
    usuario.email = str(dto.email)
    usuario.telefone = dto.telefone
    usuario.e_profissional = dto.e_profissional
    usuario.registro_conselho = dto.registro_conselho
    usuario.especialidade = dto.especialidade
    usuario.cor_agenda = dto.cor_agenda
    usuario.ativo = dto.ativo
    return usuario


def para_resposta(usuario: Usuario) -> UsuarioResponse:
    return UsuarioResponse.model_validate(usuario)


def para_lista(usuarios: list[Usuario]) -> list[UsuarioResponse]:
    return [para_resposta(usuario) for usuario in usuarios]


def para_vinculo(vinculo: ClinicaUsuario) -> VinculoClinicaResponse:
    return VinculoClinicaResponse(
        clinica_public_id=vinculo.clinica.public_id,
        clinica_nome=vinculo.clinica.nome,
        papel=vinculo.papel,
        ativo=vinculo.ativo,
    )


def para_perfil(usuario: Usuario, vinculos: list[ClinicaUsuario]) -> PerfilResponse:
    return PerfilResponse(
        usuario=para_resposta(usuario),
        vinculos=[para_vinculo(vinculo) for vinculo in vinculos],
    )
