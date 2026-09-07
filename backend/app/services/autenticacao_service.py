"""Resolução do portador do token para o usuário do domínio.

Autenticado no Keycloak não basta: o token pode ser de alguém que existe no IdP
mas não nesta aplicação, ou de quem foi desativado ou excluído aqui sem que o
IdP soubesse. Essa checagem é o que impede que uma dessincronia vire acesso.
"""

from __future__ import annotations

import logging

from app.core.seguranca import TokenVerificado, UsuarioAutenticado
from app.exceptions.domain import NaoAutenticadoError
from app.repositories.usuario_repository import UsuarioRepository

_logger = logging.getLogger("fisioagenda.autenticacao")


class AutenticacaoService:
    def __init__(self, repositorio: UsuarioRepository) -> None:
        self._repositorio = repositorio

    async def resolver(self, token: TokenVerificado) -> UsuarioAutenticado:
        usuario = await self._repositorio.buscar_por_keycloak_id(token.sub)

        # Log com o `sub`, nunca com e-mail: o log não é lugar de dado pessoal.
        if usuario is None:
            _logger.warning("token válido sem usuário local", extra={"sub": str(token.sub)})
            raise NaoAutenticadoError

        if not usuario.ativo:
            _logger.info("acesso de usuário inativo", extra={"sub": str(token.sub)})
            raise NaoAutenticadoError

        return UsuarioAutenticado(
            usuario=usuario,
            token=token,
            vinculos=tuple(usuario.vinculos),
        )
