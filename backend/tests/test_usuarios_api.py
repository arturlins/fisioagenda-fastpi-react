"""API de usuários — os quatro verbos e as regras que os cercam.

Roda contra o Postgres de verdade, com Keycloak dublê: o que se testa aqui é a
nossa lógica, não o IdP.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acesso import Usuario
from tests.conftest import KeycloakFalso

SENHA = "SenhaDeTeste#2026"


def corpo_de_criacao(**extras: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "nome": "Carla Fisioterapeuta",
        "email": f"carla-{uuid.uuid4().hex[:8]}@clinicateste.com.br",
        "senha": SENHA,
        "e_profissional": True,
    }
    return base | extras


# --- POST --------------------------------------------------------------------


async def test_post_cria_usuario_com_201_e_location(
    cliente: AsyncClient, como: Any, dono: Usuario, keycloak: KeycloakFalso
) -> None:
    como(dono)

    resposta = await cliente.post("/api/v1/usuarios", json=corpo_de_criacao())

    assert resposta.status_code == 201
    assert resposta.headers["Location"].startswith("/api/v1/usuarios/")
    corpo = resposta.json()
    assert corpo["dono_da_conta"] is False
    assert len(keycloak.usuarios) == 1  # a credencial foi criada no IdP


async def test_post_nao_expoe_identificador_interno_nem_credencial(
    cliente: AsyncClient, como: Any, dono: Usuario
) -> None:
    como(dono)

    resposta = await cliente.post("/api/v1/usuarios", json=corpo_de_criacao())

    corpo = resposta.json()
    assert "id" not in corpo
    assert "keycloak_id" not in corpo
    assert "senha" not in corpo
    assert uuid.UUID(corpo["public_id"])


async def test_post_recusa_email_duplicado_com_409(
    cliente: AsyncClient, como: Any, dono: Usuario, usuario_comum: Usuario
) -> None:
    como(dono)

    resposta = await cliente.post(
        "/api/v1/usuarios", json=corpo_de_criacao(email=usuario_comum.email)
    )

    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "email_ja_cadastrado"


async def test_post_recusa_senha_curta_apontando_o_campo(
    cliente: AsyncClient, como: Any, dono: Usuario
) -> None:
    """A política do realm exige 10 caracteres; validar aqui evita um 502."""
    como(dono)

    resposta = await cliente.post("/api/v1/usuarios", json=corpo_de_criacao(senha="123"))

    assert resposta.status_code == 422
    campos = [detalhe["campo"] for detalhe in resposta.json()["detalhes"]]
    assert any("senha" in campo for campo in campos)


async def test_post_sem_credencial_devolve_401(cliente: AsyncClient) -> None:
    resposta = await cliente.post("/api/v1/usuarios", json=corpo_de_criacao())

    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "nao_autenticado"


async def test_post_de_usuario_comum_devolve_403(
    cliente: AsyncClient, como: Any, usuario_comum: Usuario
) -> None:
    """Sem vínculo administrador em clínica alguma, não cria usuário."""
    como(usuario_comum)

    resposta = await cliente.post("/api/v1/usuarios", json=corpo_de_criacao())

    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "acesso_negado"


async def test_falha_ao_gravar_localmente_remove_o_usuario_do_keycloak(
    cliente: AsyncClient, como: Any, dono: Usuario, keycloak: KeycloakFalso, monkeypatch: Any
) -> None:
    """Compensação do ADR-006: o pior caso é um usuário órfão no IdP, e ele é
    removido. Sem isso, sobraria credencial válida sem usuário correspondente."""
    como(dono)
    from app.repositories.usuario_repository import UsuarioRepository

    async def explodir(self: Any, usuario: Usuario) -> Usuario:
        raise RuntimeError("falha simulada ao gravar")

    monkeypatch.setattr(UsuarioRepository, "adicionar", explodir)

    resposta = await cliente.post("/api/v1/usuarios", json=corpo_de_criacao())

    assert resposta.status_code == 500
    assert len(keycloak.removidos) == 1
    assert keycloak.usuarios == {}


# --- GET ---------------------------------------------------------------------


async def test_get_lista_pagina_e_conta_o_total(
    cliente: AsyncClient, como: Any, dono: Usuario, usuario_comum: Usuario
) -> None:
    como(dono)

    resposta = await cliente.get("/api/v1/usuarios")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 2
    assert corpo["pagina"] == 1
    assert {item["public_id"] for item in corpo["itens"]} == {
        str(dono.public_id),
        str(usuario_comum.public_id),
    }


async def test_get_filtra_por_busca(
    cliente: AsyncClient, como: Any, dono: Usuario, usuario_comum: Usuario
) -> None:
    como(dono)

    resposta = await cliente.get("/api/v1/usuarios", params={"busca": "Bruno"})

    assert resposta.json()["total"] == 1


@pytest.mark.parametrize("termo", ["%", "_", "%%"])
async def test_get_com_curinga_na_busca_nao_casa_com_tudo(
    cliente: AsyncClient, como: Any, dono: Usuario, usuario_comum: Usuario, termo: str
) -> None:
    """`%` e `_` são curingas do ILIKE: sem escape, a busca devolveria a conta inteira."""
    como(dono)

    resposta = await cliente.get("/api/v1/usuarios", params={"busca": termo})

    assert resposta.json()["total"] == 0


async def test_get_por_public_id(cliente: AsyncClient, como: Any, dono: Usuario) -> None:
    como(dono)

    resposta = await cliente.get(f"/api/v1/usuarios/{dono.public_id}")

    assert resposta.status_code == 200
    assert resposta.json()["public_id"] == str(dono.public_id)


async def test_get_de_inexistente_devolve_404(
    cliente: AsyncClient, como: Any, dono: Usuario
) -> None:
    como(dono)

    resposta = await cliente.get(f"/api/v1/usuarios/{uuid.uuid4()}")

    assert resposta.status_code == 404
    assert resposta.json()["codigo"] == "recurso_nao_encontrado"


# --- PUT ---------------------------------------------------------------------


async def test_put_atualiza_e_sincroniza_o_keycloak(
    cliente: AsyncClient,
    como: Any,
    dono: Usuario,
    usuario_comum: Usuario,
    keycloak: KeycloakFalso,
) -> None:
    como(dono)
    keycloak.usuarios[usuario_comum.keycloak_id] = {
        "email": usuario_comum.email,
        "nome": usuario_comum.nome,
        "habilitado": True,
    }
    keycloak.emails[usuario_comum.email.lower()] = usuario_comum.keycloak_id
    email_novo = f"bruno.novo-{uuid.uuid4().hex[:6]}@clinicateste.com.br"

    resposta = await cliente.put(
        f"/api/v1/usuarios/{usuario_comum.public_id}",
        json={
            "nome": "Bruno Terapeuta Silva",
            "email": email_novo,
            "e_profissional": True,
            "especialidade": "Ortopedia",
            "ativo": True,
        },
    )

    assert resposta.status_code == 200
    assert resposta.json()["email"] == email_novo
    assert keycloak.usuarios[usuario_comum.keycloak_id]["email"] == email_novo


async def test_put_nao_permite_virar_dono_da_conta(
    cliente: AsyncClient, como: Any, dono: Usuario, usuario_comum: Usuario, keycloak: KeycloakFalso
) -> None:
    """`dono_da_conta` não está no DTO de atualização: quem se autopromovesse
    levaria a conta inteira. O campo extra é simplesmente ignorado."""
    como(dono)
    keycloak.usuarios[usuario_comum.keycloak_id] = {
        "email": usuario_comum.email,
        "nome": usuario_comum.nome,
        "habilitado": True,
    }

    resposta = await cliente.put(
        f"/api/v1/usuarios/{usuario_comum.public_id}",
        json={
            "nome": usuario_comum.nome,
            "email": usuario_comum.email,
            "e_profissional": True,
            "ativo": True,
            "dono_da_conta": True,
        },
    )

    assert resposta.status_code == 200
    assert resposta.json()["dono_da_conta"] is False


# --- DELETE ------------------------------------------------------------------


async def test_delete_faz_exclusao_logica_e_desabilita_no_keycloak(
    cliente: AsyncClient,
    como: Any,
    dono: Usuario,
    usuario_comum: Usuario,
    keycloak: KeycloakFalso,
    sessao: AsyncSession,
) -> None:
    como(dono)
    keycloak.usuarios[usuario_comum.keycloak_id] = {
        "email": usuario_comum.email,
        "nome": usuario_comum.nome,
        "habilitado": True,
    }

    resposta = await cliente.delete(f"/api/v1/usuarios/{usuario_comum.public_id}")

    assert resposta.status_code == 204
    assert usuario_comum.keycloak_id in keycloak.desabilitados
    # A linha continua no banco: histórico clínico e financeiro aponta para ela.
    await sessao.refresh(usuario_comum)
    assert usuario_comum.excluido_em is not None
    assert usuario_comum.ativo is False


async def test_usuario_excluido_some_da_api(
    cliente: AsyncClient, como: Any, dono: Usuario, usuario_comum: Usuario, keycloak: KeycloakFalso
) -> None:
    como(dono)
    keycloak.usuarios[usuario_comum.keycloak_id] = {"email": "x", "nome": "x", "habilitado": True}
    await cliente.delete(f"/api/v1/usuarios/{usuario_comum.public_id}")

    resposta = await cliente.get(f"/api/v1/usuarios/{usuario_comum.public_id}")

    assert resposta.status_code == 404


async def test_delete_do_proprio_usuario_devolve_422(
    cliente: AsyncClient, como: Any, dono: Usuario
) -> None:
    como(dono)

    resposta = await cliente.delete(f"/api/v1/usuarios/{dono.public_id}")

    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "regra_de_negocio"


async def test_delete_do_dono_da_conta_devolve_422(
    cliente: AsyncClient, como: Any, dono: Usuario, usuario_comum: Usuario, sessao: AsyncSession
) -> None:
    """Outro administrador não pode remover o dono."""
    usuario_comum.dono_da_conta = False
    outro_dono = Usuario(
        conta_id=dono.conta_id,
        keycloak_id=uuid.uuid4(),
        nome="Segundo Dono",
        email=f"segundo-{uuid.uuid4().hex[:8]}@clinicateste.com.br",
        dono_da_conta=True,
    )
    sessao.add(outro_dono)
    await sessao.flush()
    como(outro_dono)

    resposta = await cliente.delete(f"/api/v1/usuarios/{dono.public_id}")

    assert resposta.status_code == 422
