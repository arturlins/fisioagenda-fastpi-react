"""Controller de autenticação e registro (camada MVC).

Recebe a requisição, delega ao serviço, devolve DTO. Não monta consulta, não
decide regra e nunca devolve entidade do ORM.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.v1.deps import UsuarioAtual
from app.dependencies import ContaServiceDep
from app.mappers import conta_mapper, usuario_mapper
from app.schemas.conta import RegistroContaRequest, RegistroContaResponse
from app.schemas.error import ErroResposta
from app.schemas.usuario import PerfilResponse

router = APIRouter(prefix="/api/v1/auth", tags=["autenticação"])


@router.post(
    "/registro-conta",
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma conta e o usuário dono",
    description=(
        "Única rota pública da API. Cria a conta, registra a credencial no Keycloak e grava o "
        "primeiro usuário, que nasce dono. Daqui em diante, usuários são criados por quem já "
        "está dentro."
    ),
    responses={
        409: {"model": ErroResposta, "description": "E-mail já cadastrado"},
        502: {"model": ErroResposta, "description": "Keycloak indisponível"},
    },
)
async def registrar_conta(
    dto: RegistroContaRequest,
    servico: ContaServiceDep,
    resposta: Response,
) -> RegistroContaResponse:
    # Conversão na camada web: o Service recebe entidades, não o DTO.
    conta, dono = await servico.registrar(
        conta_mapper.para_conta(dto), conta_mapper.para_dono(dto), dto.senha
    )
    resposta.headers["Location"] = f"/api/v1/usuarios/{dono.public_id}"
    return conta_mapper.para_resposta_de_registro(conta, dono)


@router.get(
    "/eu",
    summary="Perfil do usuário autenticado",
    description="Quem sou e em quais clínicas atuo, com o papel em cada uma.",
    responses={401: {"model": ErroResposta, "description": "Credencial ausente ou inválida"}},
)
async def perfil(usuario: UsuarioAtual) -> PerfilResponse:
    return usuario_mapper.para_perfil(usuario.usuario, list(usuario.vinculos))
