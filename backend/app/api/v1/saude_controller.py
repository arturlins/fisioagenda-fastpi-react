"""Endpoints operacionais.

`/saude` responde se o processo está vivo — não toca em dependência nenhuma, para
que um banco fora do ar não faça um orquestrador matar um processo saudável.
`/saude/pronto` responde se a aplicação consegue atender: aí sim o banco é
verificado, e a resposta é 503 quando não estiver acessível.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import obter_sessao

router = APIRouter(tags=["operacional"])
_logger = logging.getLogger("fisioagenda.saude")


class RespostaSaude(BaseModel):
    status: Literal["ok"]


class RespostaProntidao(BaseModel):
    status: Literal["pronto", "indisponivel"]
    banco: Literal["ok", "falha"]


@router.get("/saude", response_model=RespostaSaude, summary="Liveness")
async def saude() -> RespostaSaude:
    return RespostaSaude(status="ok")


@router.get("/saude/pronto", response_model=RespostaProntidao, summary="Readiness")
async def prontidao(
    sessao: Annotated[AsyncSession, Depends(obter_sessao)],
    resposta: Response,
) -> RespostaProntidao:
    try:
        await sessao.execute(text("SELECT 1"))
    except Exception:
        # A causa vai para o log, com id de correlação; a resposta não expõe
        # detalhe de infraestrutura.
        _logger.exception("banco inacessível na verificação de prontidão")
        resposta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return RespostaProntidao(status="indisponivel", banco="falha")

    return RespostaProntidao(status="pronto", banco="ok")
