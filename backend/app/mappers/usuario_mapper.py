"""Mapper de usuário: entidade ⇄ DTO.

Funções puras, sem lógica de negócio e sem tocar no banco — o papel do
`CustomerMapper` da aula.

A conversão DTO → entidade acontece na camada web (Controller), como no projeto
de referência: o Service passa a lidar só com entidades de domínio, sem conhecer
os contratos de HTTP. As entidades que saem daqui são **transientes** — campos
que o cliente não escolhe (`conta_id`, `keycloak_id`, `dono_da_conta`) são
responsabilidade do Service.
"""

from __future__ import annotations

from app.models.acesso import ClinicaUsuario, Usuario
from app.schemas.usuario import (
    AtualizarUsuarioRequest,
    CriarUsuarioRequest,
    PerfilResponse,
    UsuarioResponse,
    VinculoClinicaResponse,
)


def para_entidade(dto: CriarUsuarioRequest) -> Usuario:
    """DTO de criação → entidade transiente.

    Sem `senha`: a credencial não pertence à entidade, vive no Keycloak
    (ADR-001). Ela viaja separada, do Controller para o Service.
    """
    return Usuario(
        nome=dto.nome,
        email=str(dto.email),
        telefone=dto.telefone,
        e_profissional=dto.e_profissional,
        registro_conselho=dto.registro_conselho,
        especialidade=dto.especialidade,
        cor_agenda=dto.cor_agenda,
        dono_da_conta=False,
    )


def de_atualizacao_para_entidade(dto: AtualizarUsuarioRequest) -> Usuario:
    """DTO de atualização → entidade transiente, que o Service usa como fonte
    dos novos valores ao atualizar a entidade já persistida."""
    return Usuario(
        nome=dto.nome,
        email=str(dto.email),
        telefone=dto.telefone,
        e_profissional=dto.e_profissional,
        registro_conselho=dto.registro_conselho,
        especialidade=dto.especialidade,
        cor_agenda=dto.cor_agenda,
        ativo=dto.ativo,
    )


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
