"""Controller de usuários — os quatro verbos HTTP.

| Verbo  | Rota                  | Significado                          |
|--------|-----------------------|--------------------------------------|
| POST   | /usuarios             | cria, devolve 201 e `Location`       |
| GET    | /usuarios             | lista paginada, com filtros          |
| GET    | /usuarios/{public_id} | um usuário                           |
| PUT    | /usuarios/{public_id} | substitui os campos editáveis        |
| DELETE | /usuarios/{public_id} | exclusão lógica, devolve 204         |
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from app.api.v1.deps import AdminDaConta, UsuarioAtual
from app.dependencies import UsuarioServiceDep
from app.mappers import usuario_mapper
from app.schemas.error import ErroResposta
from app.schemas.usuario import (
    AtualizarUsuarioRequest,
    CriarUsuarioRequest,
    PaginaDeUsuarios,
    UsuarioResponse,
)

router = APIRouter(prefix="/api/v1/usuarios", tags=["usuários"])

RESPOSTAS_PADRAO: dict[int | str, dict[str, object]] = {
    401: {"model": ErroResposta, "description": "Credencial ausente ou inválida"},
    403: {"model": ErroResposta, "description": "Sem permissão"},
}

PublicId = Annotated[uuid.UUID, Path(description="Identificador público do usuário")]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Cria um usuário na conta",
    responses={**RESPOSTAS_PADRAO, 409: {"model": ErroResposta, "description": "E-mail em uso"}},
)
async def criar(
    dto: CriarUsuarioRequest,
    ator: AdminDaConta,
    servico: UsuarioServiceDep,
    resposta: Response,
) -> UsuarioResponse:
    # Conversão DTO -> entidade na camada web, como no projeto da aula: o Service
    # recebe entidade de domínio e não conhece o contrato HTTP.
    novo = usuario_mapper.para_entidade(dto)
    usuario = await servico.criar(ator.conta_id, novo, dto.senha)
    resposta.headers["Location"] = f"/api/v1/usuarios/{usuario.public_id}"
    return usuario_mapper.para_resposta(usuario)


@router.get("", summary="Lista os usuários da conta", responses=RESPOSTAS_PADRAO)
async def listar(
    ator: UsuarioAtual,
    servico: UsuarioServiceDep,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamanho: Annotated[int, Query(ge=1, le=100)] = 20,
    ativo: Annotated[bool | None, Query(description="Filtra por situação")] = None,
    e_profissional: Annotated[bool | None, Query(description="Só quem atende")] = None,
    busca: Annotated[str | None, Query(max_length=100, description="Nome ou e-mail")] = None,
) -> PaginaDeUsuarios:
    itens, total = await servico.listar(
        ator.conta_id,
        pagina=pagina,
        tamanho=tamanho,
        apenas_ativos=ativo,
        apenas_profissionais=e_profissional,
        busca=busca,
    )
    return PaginaDeUsuarios(
        itens=usuario_mapper.para_lista(itens),
        total=total,
        pagina=pagina,
        tamanho=tamanho,
    )


@router.get(
    "/{public_id}",
    summary="Busca um usuário",
    responses={**RESPOSTAS_PADRAO, 404: {"model": ErroResposta, "description": "Não encontrado"}},
)
async def buscar(
    public_id: PublicId,
    ator: UsuarioAtual,
    servico: UsuarioServiceDep,
) -> UsuarioResponse:
    usuario = await servico.buscar(ator.conta_id, public_id)
    return usuario_mapper.para_resposta(usuario)


@router.put(
    "/{public_id}",
    summary="Atualiza um usuário",
    responses={
        **RESPOSTAS_PADRAO,
        404: {"model": ErroResposta, "description": "Não encontrado"},
        409: {"model": ErroResposta, "description": "E-mail em uso"},
    },
)
async def atualizar(
    public_id: PublicId,
    dto: AtualizarUsuarioRequest,
    ator: AdminDaConta,
    servico: UsuarioServiceDep,
) -> UsuarioResponse:
    dados = usuario_mapper.de_atualizacao_para_entidade(dto)
    usuario = await servico.atualizar(ator.conta_id, public_id, dados)
    return usuario_mapper.para_resposta(usuario)


@router.delete(
    "/{public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um usuário (lógico)",
    responses={
        **RESPOSTAS_PADRAO,
        404: {"model": ErroResposta, "description": "Não encontrado"},
        422: {"model": ErroResposta, "description": "Regra de negócio impede a exclusão"},
    },
)
async def excluir(
    public_id: PublicId,
    ator: AdminDaConta,
    servico: UsuarioServiceDep,
) -> None:
    await servico.excluir(ator.conta_id, public_id, ator=ator)
