"""Registro de conta e perfil do autenticado."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acesso import ClinicaUsuario, Usuario
from app.models.organizacao import Conta
from tests.conftest import KeycloakFalso

SENHA = "SenhaDeTeste#2026"


def corpo_de_registro(**extras: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "nome_conta": f"Clínica {uuid.uuid4().hex[:6]}",
        "nome_responsavel": "Ana Ribeiro Souza",
        "email": f"ana-{uuid.uuid4().hex[:8]}@clinicateste.com.br",
        "senha": SENHA,
    }
    return base | extras


async def test_registro_cria_conta_e_dono_sem_autenticacao(
    cliente: AsyncClient, keycloak: KeycloakFalso, sessao: AsyncSession
) -> None:
    """Única rota pública da API."""
    corpo = corpo_de_registro()

    resposta = await cliente.post("/api/v1/auth/registro-conta", json=corpo)

    assert resposta.status_code == 201
    assert resposta.headers["Location"].startswith("/api/v1/usuarios/")
    dados = resposta.json()
    assert dados["usuario"]["dono_da_conta"] is True
    assert dados["conta"]["nome"] == corpo["nome_conta"]
    assert len(keycloak.usuarios) == 1

    gravado = await sessao.scalar(select(Usuario).where(Usuario.email == corpo["email"]))
    assert gravado is not None
    assert gravado.dono_da_conta is True


async def test_registro_nao_expoe_credencial_nem_identificador_interno(
    cliente: AsyncClient,
) -> None:
    resposta = await cliente.post("/api/v1/auth/registro-conta", json=corpo_de_registro())

    texto = resposta.text
    assert "senha" not in texto
    assert "keycloak_id" not in texto


async def test_registro_com_email_ja_existente_no_idp_devolve_409(
    cliente: AsyncClient, keycloak: KeycloakFalso
) -> None:
    corpo = corpo_de_registro()
    await cliente.post("/api/v1/auth/registro-conta", json=corpo)

    resposta = await cliente.post(
        "/api/v1/auth/registro-conta", json=corpo_de_registro(email=corpo["email"])
    )

    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "email_ja_cadastrado"


async def test_registro_com_keycloak_fora_do_ar_devolve_502(
    cliente: AsyncClient, keycloak: KeycloakFalso, sessao: AsyncSession
) -> None:
    """502 e não 500: quem falhou foi a dependência, não esta aplicação.

    E nada é gravado localmente — a conta só existe se a credencial existir.
    """
    keycloak.falhar_ao_criar = True
    corpo = corpo_de_registro()

    resposta = await cliente.post("/api/v1/auth/registro-conta", json=corpo)

    assert resposta.status_code == 502
    assert resposta.json()["codigo"] == "integracao_indisponivel"
    assert await sessao.scalar(select(Conta).where(Conta.nome == corpo["nome_conta"])) is None


async def test_falha_ao_gravar_a_conta_compensa_no_keycloak(
    cliente: AsyncClient, keycloak: KeycloakFalso, monkeypatch: Any
) -> None:
    """ADR-006: usuário criado no IdP e não gravado aqui é removido de volta."""
    from app.repositories.conta_repository import ContaRepository

    async def explodir(self: Any, conta: Conta) -> Conta:
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(ContaRepository, "adicionar", explodir)

    resposta = await cliente.post("/api/v1/auth/registro-conta", json=corpo_de_registro())

    assert resposta.status_code == 500
    assert len(keycloak.removidos) == 1
    assert keycloak.usuarios == {}


async def test_registro_recusa_email_invalido(cliente: AsyncClient) -> None:
    resposta = await cliente.post(
        "/api/v1/auth/registro-conta", json=corpo_de_registro(email="nao-e-email")
    )

    assert resposta.status_code == 422
    campos = [detalhe["campo"] for detalhe in resposta.json()["detalhes"]]
    assert any("email" in campo for campo in campos)


async def test_eu_sem_credencial_devolve_401(cliente: AsyncClient) -> None:
    resposta = await cliente.get("/api/v1/auth/eu")

    assert resposta.status_code == 401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


async def test_eu_devolve_perfil_e_vinculos(
    cliente: AsyncClient,
    como: Any,
    usuario_comum: Usuario,
    vinculo_admin: ClinicaUsuario,
    clinica: Any,
    sessao: AsyncSession,
) -> None:
    sessao.add(vinculo_admin)
    await sessao.flush()
    vinculo_admin.clinica = clinica
    como(usuario_comum, (vinculo_admin,))

    resposta = await cliente.get("/api/v1/auth/eu")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["usuario"]["public_id"] == str(usuario_comum.public_id)
    assert corpo["vinculos"][0]["papel"] == "administrador"
    assert corpo["vinculos"][0]["clinica_public_id"] == str(clinica.public_id)
