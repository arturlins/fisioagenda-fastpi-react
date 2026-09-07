"""Tratamento centralizado de exceções.

Equivale ao `@RestControllerAdvice` do projeto da aula: um único lugar traduz
exceção em resposta HTTP, e toda falha sai no mesmo formato.

Princípio que vale para todos os handlers: o cliente recebe o suficiente para
agir; o log recebe o suficiente para diagnosticar. Stack trace, SQL e detalhe de
infraestrutura ficam do lado do log.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import obter_id_correlacao
from app.exceptions.domain import DominioError
from app.schemas.error import DetalheCampo, ErroResposta

_logger = logging.getLogger("fisioagenda.erros")


def _resposta(
    request: Request,
    status: int,
    codigo: str,
    mensagem: str,
    detalhes: list[DetalheCampo] | None = None,
) -> JSONResponse:
    corpo = ErroResposta(
        horario=datetime.now(UTC),
        status=status,
        erro=HTTPStatus(status).phrase,
        codigo=codigo,
        mensagem=mensagem,
        caminho=request.url.path,
        id_correlacao=obter_id_correlacao(),
        detalhes=detalhes,
    )
    cabecalhos = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(
        status_code=status,
        content=corpo.model_dump(mode="json"),
        headers=cabecalhos,
    )


def registrar_tratadores(app: FastAPI) -> None:
    """Registra os handlers globais. Chamado na criação da aplicação."""

    @app.exception_handler(DominioError)
    async def _dominio(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DominioError)
        # Erro de domínio é situação prevista: 5xx merece atenção, 4xx não.
        nivel = logging.ERROR if exc.status_http >= 500 else logging.INFO
        _logger.log(
            nivel,
            "erro de domínio",
            extra={"codigo": exc.codigo, "status": exc.status_http, **exc.detalhes},
        )
        return _resposta(request, exc.status_http, exc.codigo, exc.mensagem)

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: Exception) -> JSONResponse:
        """Equivalente ao `MethodArgumentNotValidException` do Bean Validation."""
        assert isinstance(exc, RequestValidationError)
        detalhes = [
            DetalheCampo(
                campo=".".join(str(parte) for parte in erro["loc"]),
                mensagem=str(erro["msg"]),
            )
            for erro in exc.errors()
        ]
        return _resposta(
            request,
            422,
            "payload_invalido",
            "Os dados enviados não passaram na validação.",
            detalhes,
        )

    @app.exception_handler(IntegrityError)
    async def _integridade(request: Request, exc: Exception) -> JSONResponse:
        """Rede de segurança: uma constraint do banco chegou até aqui.

        Que a aplicação valide antes é o esperado — mas sob concorrência a
        constraint é a única verdade, e o cliente precisa de 409, não de 500.
        A mensagem do banco fica só no log: ela expõe nomes de tabela e coluna.
        """
        _logger.warning("violação de integridade no banco", exc_info=exc)
        return _resposta(
            request,
            409,
            "conflito",
            "A operação conflita com dados já existentes.",
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: Exception) -> JSONResponse:
        """Erros do próprio framework — rota inexistente, método não permitido."""
        assert isinstance(exc, StarletteHTTPException)
        codigos = {404: "rota_nao_encontrada", 405: "metodo_nao_permitido"}
        # O detalhe padrão do Starlette vem em inglês ("Not Found"); traduzir os
        # casos que o cliente realmente encontra evita uma API bilíngue.
        mensagens = {
            404: "Rota não encontrada.",
            405: "Método não permitido para esta rota.",
        }
        return _resposta(
            request,
            exc.status_code,
            codigos.get(exc.status_code, "erro_http"),
            mensagens.get(exc.status_code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, exc: Exception) -> JSONResponse:
        """O que não foi previsto.

        A resposta é genérica de propósito: mensagem de exceção pode conter
        caminho de arquivo, trecho de SQL ou valor de configuração. O que o
        cliente leva é o `id_correlacao` — com ele, quem suporta acha a linha
        exata no log.
        """
        _logger.exception("erro não tratado")
        return _resposta(
            request,
            500,
            "erro_interno",
            "Ocorreu um erro inesperado. Informe o id de correlação ao suporte.",
        )
