"""Tratamento centralizado de exceções.

Rotas de teste levantam cada erro possível; as asserções cobrem o código HTTP,
o formato da resposta e — o que mais importa — o que NÃO pode vazar.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.exceptions.domain import (
    AcessoNegadoError,
    EmailJaCadastradoError,
    IntegracaoError,
    NaoAutenticadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from app.main import criar_app

SEGREDO_NA_EXCECAO = "senha=super-secreta-123"


class CorpoExemplo(BaseModel):
    email: str
    idade: int


@pytest.fixture
def app_com_erros() -> FastAPI:
    app = criar_app()

    @app.get("/erros/nao-encontrado")
    async def _nao_encontrado() -> None:
        raise RecursoNaoEncontradoError.de("Usuário", uuid.uuid4())

    @app.get("/erros/conflito")
    async def _conflito() -> None:
        raise EmailJaCadastradoError("ana@exemplo.local")

    @app.get("/erros/regra")
    async def _regra() -> None:
        raise RegraDeNegocioError("Profissional não habilitado para este serviço.")

    @app.get("/erros/nao-autenticado")
    async def _nao_autenticado() -> None:
        raise NaoAutenticadoError

    @app.get("/erros/negado")
    async def _negado() -> None:
        raise AcessoNegadoError

    @app.get("/erros/integracao")
    async def _integracao() -> None:
        raise IntegracaoError("Keycloak")

    @app.get("/erros/integridade")
    async def _integridade() -> None:
        raise IntegrityError(
            "INSERT INTO usuarios ...", {}, Exception("uq_usuarios_conta_id_email")
        )

    @app.get("/erros/inesperado")
    async def _inesperado() -> None:
        raise RuntimeError(SEGREDO_NA_EXCECAO)

    @app.post("/erros/validacao")
    async def _validacao(corpo: CorpoExemplo) -> CorpoExemplo:
        return corpo

    return app


@pytest.fixture
async def cliente_erros(app_com_erros: FastAPI) -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False: o Starlette devolve a resposta do handler e
    # relança a exceção para o servidor logar. Em teste, queremos inspecionar a
    # resposta, não receber a exceção.
    async with AsyncClient(
        transport=ASGITransport(app=app_com_erros, raise_app_exceptions=False),
        base_url="http://teste",
    ) as cliente:
        yield cliente


@pytest.mark.parametrize(
    ("rota", "status", "codigo"),
    [
        ("/erros/nao-encontrado", 404, "recurso_nao_encontrado"),
        ("/erros/conflito", 409, "email_ja_cadastrado"),
        ("/erros/regra", 422, "regra_de_negocio"),
        ("/erros/nao-autenticado", 401, "nao_autenticado"),
        ("/erros/negado", 403, "acesso_negado"),
        ("/erros/integracao", 502, "integracao_indisponivel"),
        ("/erros/integridade", 409, "conflito"),
        ("/erros/inesperado", 500, "erro_interno"),
    ],
)
async def test_cada_erro_vira_o_status_e_o_codigo_certos(
    cliente_erros: AsyncClient, rota: str, status: int, codigo: str
) -> None:
    resposta = await cliente_erros.get(rota)

    assert resposta.status_code == status
    corpo = resposta.json()
    assert corpo["codigo"] == codigo
    assert corpo["status"] == status
    assert corpo["caminho"] == rota
    assert corpo["id_correlacao"]  # sempre presente, liga a resposta ao log
    assert corpo["horario"]


async def test_erro_inesperado_nao_vaza_conteudo_da_excecao(cliente_erros: AsyncClient) -> None:
    """O 500 é o handler mais perigoso: mensagem de exceção carrega segredo."""
    resposta = await cliente_erros.get("/erros/inesperado")

    assert resposta.status_code == 500
    assert SEGREDO_NA_EXCECAO not in resposta.text
    assert "Traceback" not in resposta.text
    assert "RuntimeError" not in resposta.text


async def test_violacao_de_integridade_nao_vaza_nome_de_constraint(
    cliente_erros: AsyncClient,
) -> None:
    resposta = await cliente_erros.get("/erros/integridade")

    assert resposta.status_code == 409
    assert "uq_usuarios" not in resposta.text
    assert "INSERT INTO" not in resposta.text


async def test_nao_autenticado_traz_www_authenticate(cliente_erros: AsyncClient) -> None:
    resposta = await cliente_erros.get("/erros/nao-autenticado")

    assert resposta.headers["WWW-Authenticate"] == "Bearer"


async def test_payload_invalido_aponta_o_campo(cliente_erros: AsyncClient) -> None:
    resposta = await cliente_erros.post("/erros/validacao", json={"email": "ana@exemplo.local"})

    assert resposta.status_code == 422
    corpo = resposta.json()
    assert corpo["codigo"] == "payload_invalido"
    campos = [detalhe["campo"] for detalhe in corpo["detalhes"]]
    assert any("idade" in campo for campo in campos)


async def test_rota_inexistente_usa_o_mesmo_formato(cliente_erros: AsyncClient) -> None:
    """Erro do framework não pode sair num formato diferente do resto da API."""
    resposta = await cliente_erros.get("/rota/que/nao/existe")

    assert resposta.status_code == 404
    corpo = resposta.json()
    assert corpo["codigo"] == "rota_nao_encontrada"
    assert corpo["id_correlacao"]


async def test_metodo_nao_permitido_usa_o_mesmo_formato(cliente_erros: AsyncClient) -> None:
    resposta = await cliente_erros.delete("/erros/validacao")

    assert resposta.status_code == 405
    assert resposta.json()["codigo"] == "metodo_nao_permitido"


async def test_mensagens_do_framework_saem_em_portugues(cliente_erros: AsyncClient) -> None:
    """API bilíngue confunde: o detalhe padrão do Starlette vem em inglês."""
    assert (await cliente_erros.get("/nada/aqui")).json()["mensagem"] == "Rota não encontrada."
    assert (await cliente_erros.delete("/erros/validacao")).json()[
        "mensagem"
    ] == "Método não permitido para esta rota."
