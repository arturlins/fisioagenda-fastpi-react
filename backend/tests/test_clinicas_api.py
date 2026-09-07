"""API de clínicas e vínculos, incluindo o isolamento entre contas.

O teste que mais importa aqui é o de tenant: um `public_id` de outra conta não
pode ser alcançável, e a resposta precisa ser 404 — 403 confirmaria que o
recurso existe.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acesso import ClinicaUsuario, Usuario
from app.models.enums import PapelUsuario
from app.models.organizacao import Clinica, Conta


def corpo_de_clinica(**extras: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "nome": f"Unidade {uuid.uuid4().hex[:6]}",
        "fuso_horario": "America/Maceio",
        "uf": "AL",
    }
    return base | extras


# --- CRUD --------------------------------------------------------------------


async def test_post_cria_clinica_com_201_e_location(
    cliente: AsyncClient, como: Any, dono: Usuario
) -> None:
    como(dono)

    resposta = await cliente.post("/api/v1/clinicas", json=corpo_de_clinica())

    assert resposta.status_code == 201
    assert resposta.headers["Location"].startswith("/api/v1/clinicas/")


async def test_post_recusa_fuso_horario_inexistente(
    cliente: AsyncClient, como: Any, dono: Usuario
) -> None:
    """O fuso converte a grade semanal em instante absoluto: um valor inválido
    só apareceria como atendimento na hora errada, muito depois."""
    como(dono)

    resposta = await cliente.post(
        "/api/v1/clinicas", json=corpo_de_clinica(fuso_horario="Marte/Olimpo")
    )

    assert resposta.status_code == 422


async def test_post_recusa_nome_duplicado_na_conta(
    cliente: AsyncClient, como: Any, dono: Usuario, clinica: Clinica
) -> None:
    como(dono)

    resposta = await cliente.post("/api/v1/clinicas", json=corpo_de_clinica(nome=clinica.nome))

    assert resposta.status_code == 409


async def test_get_lista_e_busca_por_public_id(
    cliente: AsyncClient, como: Any, dono: Usuario, clinica: Clinica
) -> None:
    como(dono)

    lista = await cliente.get("/api/v1/clinicas")
    uma = await cliente.get(f"/api/v1/clinicas/{clinica.public_id}")

    assert [item["public_id"] for item in lista.json()] == [str(clinica.public_id)]
    assert uma.json()["nome"] == clinica.nome


async def test_put_atualiza_clinica(
    cliente: AsyncClient, como: Any, dono: Usuario, clinica: Clinica
) -> None:
    como(dono)

    resposta = await cliente.put(
        f"/api/v1/clinicas/{clinica.public_id}",
        json=corpo_de_clinica(
            nome="Unidade Centro II", fuso_horario="America/Sao_Paulo", ativa=True
        ),
    )

    assert resposta.status_code == 200
    assert resposta.json()["fuso_horario"] == "America/Sao_Paulo"


async def test_delete_remove_clinica_sem_vinculos(
    cliente: AsyncClient, como: Any, dono: Usuario, clinica: Clinica
) -> None:
    como(dono)

    resposta = await cliente.delete(f"/api/v1/clinicas/{clinica.public_id}")

    assert resposta.status_code == 204


async def test_delete_recusa_clinica_com_vinculos(
    cliente: AsyncClient,
    como: Any,
    dono: Usuario,
    clinica: Clinica,
    vinculo_admin: ClinicaUsuario,
    sessao: AsyncSession,
) -> None:
    """As chaves apontando para `clinicas` são CASCADE: apagar levaria a agenda
    junto, em silêncio."""
    como(dono)
    sessao.add(vinculo_admin)
    await sessao.flush()

    resposta = await cliente.delete(f"/api/v1/clinicas/{clinica.public_id}")

    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "regra_de_negocio"


# --- vínculos ----------------------------------------------------------------


async def test_post_vincula_usuario_com_papel(
    cliente: AsyncClient, como: Any, dono: Usuario, clinica: Clinica, usuario_comum: Usuario
) -> None:
    como(dono)

    resposta = await cliente.post(
        f"/api/v1/clinicas/{clinica.public_id}/usuarios",
        json={"usuario_public_id": str(usuario_comum.public_id), "papel": "administrador"},
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["papel"] == "administrador"
    assert corpo["usuario_public_id"] == str(usuario_comum.public_id)


async def test_post_vinculo_duplicado_devolve_409(
    cliente: AsyncClient,
    como: Any,
    dono: Usuario,
    clinica: Clinica,
    usuario_comum: Usuario,
    vinculo_admin: ClinicaUsuario,
    sessao: AsyncSession,
) -> None:
    como(dono)
    sessao.add(vinculo_admin)
    await sessao.flush()

    resposta = await cliente.post(
        f"/api/v1/clinicas/{clinica.public_id}/usuarios",
        json={"usuario_public_id": str(usuario_comum.public_id), "papel": "comum"},
    )

    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "vinculo_ja_existe"


async def test_put_altera_o_papel_do_vinculo(
    cliente: AsyncClient,
    como: Any,
    dono: Usuario,
    clinica: Clinica,
    usuario_comum: Usuario,
    vinculo_admin: ClinicaUsuario,
    sessao: AsyncSession,
) -> None:
    como(dono)
    sessao.add(vinculo_admin)
    await sessao.flush()

    resposta = await cliente.put(
        f"/api/v1/clinicas/{clinica.public_id}/usuarios/{usuario_comum.public_id}",
        json={"papel": "comum", "ativo": True},
    )

    assert resposta.status_code == 200
    assert resposta.json()["papel"] == "comum"


async def test_delete_remove_o_vinculo(
    cliente: AsyncClient,
    como: Any,
    dono: Usuario,
    clinica: Clinica,
    usuario_comum: Usuario,
    vinculo_admin: ClinicaUsuario,
    sessao: AsyncSession,
) -> None:
    como(dono)
    sessao.add(vinculo_admin)
    await sessao.flush()

    resposta = await cliente.delete(
        f"/api/v1/clinicas/{clinica.public_id}/usuarios/{usuario_comum.public_id}"
    )
    depois = await cliente.get(f"/api/v1/clinicas/{clinica.public_id}/usuarios")

    assert resposta.status_code == 204
    assert depois.json() == []


async def test_vincular_usuario_de_outra_conta_devolve_404(
    cliente: AsyncClient, como: Any, dono: Usuario, clinica: Clinica, sessao: AsyncSession
) -> None:
    outra_conta = Conta(nome=f"Outra {uuid.uuid4().hex[:6]}")
    sessao.add(outra_conta)
    await sessao.flush()
    forasteiro = Usuario(
        conta_id=outra_conta.id,
        keycloak_id=uuid.uuid4(),
        nome="De Fora",
        email=f"fora-{uuid.uuid4().hex[:8]}@clinicateste.com.br",
    )
    sessao.add(forasteiro)
    await sessao.flush()
    como(dono)

    resposta = await cliente.post(
        f"/api/v1/clinicas/{clinica.public_id}/usuarios",
        json={"usuario_public_id": str(forasteiro.public_id), "papel": "comum"},
    )

    assert resposta.status_code == 404


# --- isolamento entre contas -------------------------------------------------


async def test_clinica_de_outra_conta_responde_404_e_nao_403(
    cliente: AsyncClient, como: Any, clinica: Clinica, sessao: AsyncSession
) -> None:
    """403 confirmaria que o recurso existe — informação que o usuário de outra
    conta não deveria obter."""
    outra_conta = Conta(nome=f"Outra {uuid.uuid4().hex[:6]}")
    sessao.add(outra_conta)
    await sessao.flush()
    invasor = Usuario(
        conta_id=outra_conta.id,
        keycloak_id=uuid.uuid4(),
        nome="Invasor",
        email=f"invasor-{uuid.uuid4().hex[:8]}@clinicateste.com.br",
        dono_da_conta=True,
    )
    sessao.add(invasor)
    await sessao.flush()
    como(invasor)

    leitura = await cliente.get(f"/api/v1/clinicas/{clinica.public_id}")
    listagem = await cliente.get("/api/v1/clinicas")

    assert leitura.status_code == 404
    assert listagem.json() == []


async def test_usuario_comum_nao_administra_clinica_sem_vinculo(
    cliente: AsyncClient, como: Any, usuario_comum: Usuario, clinica: Clinica
) -> None:
    como(usuario_comum)

    resposta = await cliente.post(
        f"/api/v1/clinicas/{clinica.public_id}/usuarios",
        json={"usuario_public_id": str(usuario_comum.public_id), "papel": "comum"},
    )

    assert resposta.status_code == 403


async def test_administrador_da_clinica_gerencia_os_vinculos_dela(
    cliente: AsyncClient,
    como: Any,
    usuario_comum: Usuario,
    clinica: Clinica,
    vinculo_admin: ClinicaUsuario,
    sessao: AsyncSession,
    dono: Usuario,
) -> None:
    """Papel é por clínica: administrar uma unidade basta para gerir os vínculos dela."""
    sessao.add(vinculo_admin)
    await sessao.flush()
    como(usuario_comum, (vinculo_admin,))

    resposta = await cliente.post(
        f"/api/v1/clinicas/{clinica.public_id}/usuarios",
        json={"usuario_public_id": str(dono.public_id), "papel": PapelUsuario.COMUM.value},
    )

    assert resposta.status_code == 201
