"""Controller de clínicas e vínculos — os quatro verbos, em dois níveis.

`/clinicas` é escopo de conta: só administrador da conta cria, edita ou remove.
`/clinicas/{id}/usuarios` é escopo de clínica: exige administrar aquela unidade,
o que o `requer_acesso_a_clinica` verifica resolvendo o `public_id` dentro da
conta do autenticado.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from app.api.v1.deps import AdminDaConta, UsuarioAtual, requer_acesso_a_clinica
from app.dependencies import ClinicaServiceDep
from app.mappers import clinica_mapper
from app.schemas.clinica import (
    AtualizarClinicaRequest,
    AtualizarVinculoRequest,
    ClinicaResponse,
    CriarClinicaRequest,
    VincularUsuarioRequest,
    VinculoResponse,
)
from app.schemas.error import ErroResposta

router = APIRouter(prefix="/api/v1/clinicas", tags=["clínicas"])

RESPOSTAS_PADRAO: dict[int | str, dict[str, object]] = {
    401: {"model": ErroResposta, "description": "Credencial ausente ou inválida"},
    403: {"model": ErroResposta, "description": "Sem permissão"},
    404: {"model": ErroResposta, "description": "Não encontrado"},
}

ClinicaId = Annotated[uuid.UUID, Path(description="Identificador público da clínica")]
UsuarioId = Annotated[uuid.UUID, Path(description="Identificador público do usuário")]

# Só quem administra a clínica mexe nos vínculos dela.
_admin_da_clinica = Depends(requer_acesso_a_clinica(como_administrador=True, parametro="public_id"))


# --- clínicas ----------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma clínica",
    responses={**RESPOSTAS_PADRAO, 409: {"model": ErroResposta, "description": "Nome em uso"}},
)
async def criar(
    dto: CriarClinicaRequest,
    ator: AdminDaConta,
    servico: ClinicaServiceDep,
    resposta: Response,
) -> ClinicaResponse:
    # Conversão DTO -> entidade na camada web (padrão da aula).
    clinica = await servico.criar(ator.conta_id, clinica_mapper.para_entidade(dto))
    resposta.headers["Location"] = f"/api/v1/clinicas/{clinica.public_id}"
    return clinica_mapper.para_resposta(clinica)


@router.get("", summary="Lista as clínicas da conta", responses=RESPOSTAS_PADRAO)
async def listar(ator: UsuarioAtual, servico: ClinicaServiceDep) -> list[ClinicaResponse]:
    return clinica_mapper.para_lista(await servico.listar(ator.conta_id))


@router.get("/{public_id}", summary="Busca uma clínica", responses=RESPOSTAS_PADRAO)
async def buscar(
    public_id: ClinicaId, ator: UsuarioAtual, servico: ClinicaServiceDep
) -> ClinicaResponse:
    return clinica_mapper.para_resposta(await servico.buscar(ator.conta_id, public_id))


@router.put(
    "/{public_id}",
    summary="Atualiza uma clínica",
    responses={**RESPOSTAS_PADRAO, 409: {"model": ErroResposta, "description": "Nome em uso"}},
)
async def atualizar(
    public_id: ClinicaId,
    dto: AtualizarClinicaRequest,
    ator: AdminDaConta,
    servico: ClinicaServiceDep,
) -> ClinicaResponse:
    dados = clinica_mapper.de_atualizacao_para_entidade(dto)
    clinica = await servico.atualizar(ator.conta_id, public_id, dados)
    return clinica_mapper.para_resposta(clinica)


@router.delete(
    "/{public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma clínica sem vínculos",
    responses={
        **RESPOSTAS_PADRAO,
        422: {"model": ErroResposta, "description": "A clínica ainda tem usuários vinculados"},
    },
)
async def excluir(public_id: ClinicaId, ator: AdminDaConta, servico: ClinicaServiceDep) -> None:
    await servico.excluir(ator.conta_id, public_id)


# --- vínculos ----------------------------------------------------------------


@router.post(
    "/{public_id}/usuarios",
    status_code=status.HTTP_201_CREATED,
    summary="Vincula um usuário à clínica com um papel",
    dependencies=[_admin_da_clinica],
    responses={
        **RESPOSTAS_PADRAO,
        409: {"model": ErroResposta, "description": "Vínculo já existe"},
    },
)
async def vincular(
    public_id: ClinicaId,
    dto: VincularUsuarioRequest,
    ator: UsuarioAtual,
    servico: ClinicaServiceDep,
) -> VinculoResponse:
    vinculo = await servico.vincular(ator.conta_id, public_id, dto.usuario_public_id, dto.papel)
    return clinica_mapper.para_vinculo(vinculo)


@router.get(
    "/{public_id}/usuarios",
    summary="Lista quem atua na clínica",
    responses=RESPOSTAS_PADRAO,
)
async def listar_vinculos(
    public_id: ClinicaId, ator: UsuarioAtual, servico: ClinicaServiceDep
) -> list[VinculoResponse]:
    vinculos = await servico.listar_vinculos(ator.conta_id, public_id)
    return clinica_mapper.para_lista_de_vinculos(vinculos)


@router.put(
    "/{public_id}/usuarios/{usuario_public_id}",
    summary="Altera o papel de um usuário na clínica",
    dependencies=[_admin_da_clinica],
    responses={
        **RESPOSTAS_PADRAO,
        422: {"model": ErroResposta, "description": "A clínica ficaria sem administrador"},
    },
)
async def atualizar_vinculo(
    public_id: ClinicaId,
    usuario_public_id: UsuarioId,
    dto: AtualizarVinculoRequest,
    ator: UsuarioAtual,
    servico: ClinicaServiceDep,
) -> VinculoResponse:
    vinculo = await servico.atualizar_vinculo(
        ator.conta_id, public_id, usuario_public_id, dto.papel, dto.ativo
    )
    return clinica_mapper.para_vinculo(vinculo)


@router.delete(
    "/{public_id}/usuarios/{usuario_public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove o vínculo de um usuário com a clínica",
    dependencies=[_admin_da_clinica],
    responses={
        **RESPOSTAS_PADRAO,
        422: {"model": ErroResposta, "description": "A clínica ficaria sem administrador"},
    },
)
async def remover_vinculo(
    public_id: ClinicaId,
    usuario_public_id: UsuarioId,
    ator: UsuarioAtual,
    servico: ClinicaServiceDep,
) -> None:
    await servico.remover_vinculo(ator.conta_id, public_id, usuario_public_id)
