"""Criação da aplicação.

Fábrica em vez de instância global: os testes montam a aplicação com a
configuração deles sem depender de ordem de import.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth_controller import router as auth_router
from app.api.v1.saude_controller import router as saude_router
from app.core.config import Configuracao, obter_configuracao
from app.core.logging import configurar_logging
from app.core.middleware import CorrelacaoMiddleware
from app.core.plataforma import configurar_loop_de_eventos
from app.db.session import encerrar_engine
from app.dependencies import encerrar_cliente_http, obter_cache_de_chaves
from app.exceptions.handlers import registrar_tratadores

# Cobre quem importa a aplicação e cria o próprio loop (pytest, Alembic). O
# uvicorn ignora a política e é tratado em `servidor.py`.
configurar_loop_de_eventos()

_logger = logging.getLogger("fisioagenda")


@asynccontextmanager
async def _ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    config: Configuracao = app.state.config

    # Carrega o JWKS na subida para que a primeira requisição autenticada não
    # pague a ida ao Keycloak. Falhar aqui não impede a aplicação de subir: o
    # Keycloak pode voltar, e /saude/pronto informa a situação enquanto isso.
    chaves_ok = await obter_cache_de_chaves().aquecer()
    if not chaves_ok:
        _logger.warning("subindo sem as chaves do Keycloak; serão buscadas sob demanda")

    _logger.info(
        "aplicação iniciada",
        extra={"ambiente": config.ambiente.value, "versao": config.app_versao},
    )
    yield
    await encerrar_cliente_http()
    await encerrar_engine()
    _logger.info("aplicação encerrada")


def criar_app(config: Configuracao | None = None) -> FastAPI:
    config = config or obter_configuracao()
    configurar_logging(nivel=config.log_nivel, formato=config.log_formato)

    app = FastAPI(
        title=config.app_nome,
        version=config.app_versao,
        summary="Agendamento de fisioterapia — uso interno.",
        lifespan=_ciclo_de_vida,
        # Documentação interativa fica fora do ar em produção.
        docs_url=None if config.e_producao else "/docs",
        redoc_url=None,
        openapi_url=None if config.e_producao else "/openapi.json",
        # O /docs autentica pelo client público do frontend, com PKCE. O client
        # confidencial da API não tem fluxo de navegador e não entra aqui.
        swagger_ui_init_oauth={
            "clientId": "fisioagenda-web",
            "usePkceWithAuthorizationCodeGrant": True,
            "scopes": "openid profile email",
        },
    )
    app.state.config = config

    app.add_middleware(CorrelacaoMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origens,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Location"],
    )

    registrar_tratadores(app)
    app.include_router(saude_router)
    app.include_router(auth_router)
    return app


app = criar_app()
