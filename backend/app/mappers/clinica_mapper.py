"""Mapper de clínica: entidade ⇄ DTO.

Conversão DTO → entidade na camada web, produzindo entidade transiente: o
`conta_id` é atribuído pelo Service, a partir do contexto autenticado.
"""

from __future__ import annotations

from app.models.acesso import ClinicaUsuario
from app.models.organizacao import Clinica
from app.schemas.clinica import (
    AtualizarClinicaRequest,
    ClinicaResponse,
    CriarClinicaRequest,
    VinculoResponse,
)


def para_entidade(dto: CriarClinicaRequest) -> Clinica:
    return Clinica(
        nome=dto.nome,
        fuso_horario=dto.fuso_horario,
        telefone=dto.telefone,
        endereco=dto.endereco,
        cidade=dto.cidade,
        uf=dto.uf,
    )


def de_atualizacao_para_entidade(dto: AtualizarClinicaRequest) -> Clinica:
    """Entidade transiente com os novos valores; o Service copia sobre a
    entidade persistida."""
    return Clinica(
        nome=dto.nome,
        fuso_horario=dto.fuso_horario,
        telefone=dto.telefone,
        endereco=dto.endereco,
        cidade=dto.cidade,
        uf=dto.uf,
        ativa=dto.ativa,
    )


def para_resposta(clinica: Clinica) -> ClinicaResponse:
    return ClinicaResponse.model_validate(clinica)


def para_lista(clinicas: list[Clinica]) -> list[ClinicaResponse]:
    return [para_resposta(clinica) for clinica in clinicas]


def para_vinculo(vinculo: ClinicaUsuario) -> VinculoResponse:
    return VinculoResponse(
        usuario_public_id=vinculo.usuario.public_id,
        usuario_nome=vinculo.usuario.nome,
        usuario_email=vinculo.usuario.email,
        papel=vinculo.papel,
        ativo=vinculo.ativo,
    )


def para_lista_de_vinculos(vinculos: list[ClinicaUsuario]) -> list[VinculoResponse]:
    return [para_vinculo(vinculo) for vinculo in vinculos]
