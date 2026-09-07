"""Dependências de autenticação e autorização das rotas.

`auto_error=False` no esquema Bearer é deliberado: deixado como `True`, o
FastAPI devolveria um 403 próprio, fora do formato padronizado de erro da API.
Aqui a ausência de credencial vira `NaoAutenticadoError`, que passa pelo mesmo
handler de todos os outros erros.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Path
from fastapi.security import OAuth2AuthorizationCodeBearer

from app.core.config import obter_configuracao
from app.core.seguranca import TokenVerificado, UsuarioAutenticado, verificar_token
from app.dependencies import (
    AutenticacaoServiceDep,
    CacheDeChavesDep,
    Config,
    obter_clinica_repository,
)
from app.exceptions.domain import AcessoNegadoError, NaoAutenticadoError, RecursoNaoEncontradoError
from app.models.enums import PapelUsuario
from app.repositories.clinica_repository import ClinicaRepository

_emissor = obter_configuracao().keycloak_emissor

# Authorization Code + PKCE, e não HTTPBearer, para que o botão "Authorize" do
# /docs faça o login real no Keycloak em vez de pedir um token colado à mão.
# Como esquema de extração, o comportamento é o mesmo: lê o cabeçalho Bearer.
_oauth2 = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"{_emissor}/protocol/openid-connect/auth",
    tokenUrl=f"{_emissor}/protocol/openid-connect/token",
    refreshUrl=f"{_emissor}/protocol/openid-connect/token",
    auto_error=False,
    description="Token de acesso emitido pelo Keycloak",
)


async def obter_token_verificado(
    config: Config,
    cache: CacheDeChavesDep,
    token: Annotated[str | None, Depends(_oauth2)] = None,
) -> TokenVerificado:
    if not token:
        raise NaoAutenticadoError
    return await verificar_token(token, config, cache)


async def obter_usuario_atual(
    token: Annotated[TokenVerificado, Depends(obter_token_verificado)],
    servico: AutenticacaoServiceDep,
) -> UsuarioAutenticado:
    return await servico.resolver(token)


UsuarioAtual = Annotated[UsuarioAutenticado, Depends(obter_usuario_atual)]


async def requer_admin_da_conta(usuario: UsuarioAtual) -> UsuarioAutenticado:
    """Operações no nível da conta: criar usuário, criar clínica.

    Dono da conta tem acesso irrestrito; fora ele, é preciso ser administrador
    de pelo menos uma clínica da conta.
    """
    if usuario.e_dono_da_conta:
        return usuario

    administra_alguma = any(
        vinculo.ativo and vinculo.papel is PapelUsuario.ADMINISTRADOR
        for vinculo in usuario.vinculos
    )
    if not administra_alguma:
        raise AcessoNegadoError
    return usuario


AdminDaConta = Annotated[UsuarioAutenticado, Depends(requer_admin_da_conta)]


def requer_acesso_a_clinica(
    *, como_administrador: bool, parametro: str = "clinica_public_id"
) -> Callable[..., Coroutine[Any, Any, UsuarioAutenticado]]:
    """Fábrica de dependência para rotas que operam sobre uma clínica.

    Recebe o nome do parâmetro de caminho porque ele muda conforme a rota.
    Resolve o `public_id` para a clínica — sempre dentro da conta do usuário —
    e então checa o papel.

    Clínica de outra conta responde 404, não 403: confirmar que o recurso existe
    já é informação que o usuário não deveria obter.
    """

    async def dependencia(
        usuario: UsuarioAtual,
        repositorio: Annotated[ClinicaRepository, Depends(obter_clinica_repository)],
        public_id: Annotated[uuid.UUID, Path(alias=parametro)],
    ) -> UsuarioAutenticado:
        clinica = await repositorio.buscar_por_public_id(usuario.conta_id, public_id)
        if clinica is None:
            raise RecursoNaoEncontradoError.de("Clínica", public_id)

        permitido = (
            usuario.administra(clinica.id) if como_administrador else usuario.enxerga(clinica.id)
        )
        if not permitido:
            raise AcessoNegadoError
        return usuario

    return dependencia
