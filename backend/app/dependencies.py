"""Wiring de dependências.

Equivale à injeção por construtor do Spring: quem precisa de um serviço recebe
um pronto, sem saber como foi montado.

Os objetos com estado — cliente HTTP, cache de chaves, cliente da Admin API —
são únicos no processo. Criar um `httpx.AsyncClient` por requisição joga fora o
pool de conexões e o keep-alive.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Configuracao, obter_configuracao
from app.db.session import obter_sessao
from app.integrations.keycloak.admin import KeycloakAdmin
from app.integrations.keycloak.jwks import CacheDeChaves
from app.repositories.clinica_repository import ClinicaRepository
from app.repositories.conta_repository import ContaRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.services.autenticacao_service import AutenticacaoService
from app.services.clinica_service import ClinicaService
from app.services.conta_service import ContaService
from app.services.usuario_service import UsuarioService

Sessao = Annotated[AsyncSession, Depends(obter_sessao)]
Config = Annotated[Configuracao, Depends(obter_configuracao)]


@lru_cache
def obter_cliente_http() -> httpx.AsyncClient:
    config = obter_configuracao()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(config.keycloak_timeout_segundos),
        # Limita a fila de conexões: se o Keycloak ficar lento, é melhor falhar
        # rápido do que acumular requisições até esgotar o processo.
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


@lru_cache
def obter_cache_de_chaves() -> CacheDeChaves:
    return CacheDeChaves(obter_configuracao(), obter_cliente_http())


@lru_cache
def obter_keycloak_admin() -> KeycloakAdmin:
    return KeycloakAdmin(obter_configuracao(), obter_cliente_http())


async def encerrar_cliente_http() -> None:
    if obter_cliente_http.cache_info().currsize:
        await obter_cliente_http().aclose()
        obter_cliente_http.cache_clear()
        obter_cache_de_chaves.cache_clear()
        obter_keycloak_admin.cache_clear()


def obter_usuario_repository(sessao: Sessao) -> UsuarioRepository:
    return UsuarioRepository(sessao)


def obter_clinica_repository(sessao: Sessao) -> ClinicaRepository:
    return ClinicaRepository(sessao)


def obter_conta_repository(sessao: Sessao) -> ContaRepository:
    return ContaRepository(sessao)


def obter_clinica_service(
    repositorio: Annotated[ClinicaRepository, Depends(obter_clinica_repository)],
    usuarios: Annotated[UsuarioRepository, Depends(obter_usuario_repository)],
) -> ClinicaService:
    return ClinicaService(repositorio, usuarios)


def obter_usuario_service(
    sessao: Sessao,
    repositorio: Annotated[UsuarioRepository, Depends(obter_usuario_repository)],
    keycloak: Annotated[KeycloakAdmin, Depends(obter_keycloak_admin)],
) -> UsuarioService:
    return UsuarioService(sessao, repositorio, keycloak)


def obter_conta_service(
    sessao: Sessao,
    contas: Annotated[ContaRepository, Depends(obter_conta_repository)],
    usuarios: Annotated[UsuarioRepository, Depends(obter_usuario_repository)],
    keycloak: Annotated[KeycloakAdmin, Depends(obter_keycloak_admin)],
) -> ContaService:
    return ContaService(sessao, contas, usuarios, keycloak)


def obter_autenticacao_service(
    repositorio: Annotated[UsuarioRepository, Depends(obter_usuario_repository)],
) -> AutenticacaoService:
    return AutenticacaoService(repositorio)


CacheDeChavesDep = Annotated[CacheDeChaves, Depends(obter_cache_de_chaves)]
KeycloakAdminDep = Annotated[KeycloakAdmin, Depends(obter_keycloak_admin)]
AutenticacaoServiceDep = Annotated[AutenticacaoService, Depends(obter_autenticacao_service)]
ContaServiceDep = Annotated[ContaService, Depends(obter_conta_service)]
UsuarioServiceDep = Annotated[UsuarioService, Depends(obter_usuario_service)]
ClinicaServiceDep = Annotated[ClinicaService, Depends(obter_clinica_service)]
