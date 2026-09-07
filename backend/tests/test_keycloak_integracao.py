"""Integração real com o Keycloak.

Os testes de `test_seguranca.py` provam a lógica de verificação com chaves
sintéticas. Estes provam que o Keycloak de verdade emite um token que essa
lógica aceita — sem isso, um realm mal configurado passaria despercebido até a
primeira tentativa de login.

Pulam sozinhos quando o Keycloak não está no ar: `docker compose up -d`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from app.core.config import Configuracao, obter_configuracao
from app.core.seguranca import verificar_token
from app.exceptions.domain import NaoAutenticadoError
from app.integrations.keycloak.admin import KeycloakAdmin, UsuarioJaExisteNoIdpError
from app.integrations.keycloak.jwks import CacheDeChaves

pytestmark = pytest.mark.keycloak

SENHA_DE_TESTE = "SenhaDeTeste#2026"  # credencial descartável, criada e removida no teste


def _segredo_do_client_de_testes() -> str | None:
    """Lê o .env da raiz, onde vivem os segredos da infraestrutura local.

    Não entra em `Configuracao`: é credencial que só os testes usam, e config de
    aplicação não deve carregar campo que a aplicação nunca lê.
    """
    arquivo = Path(__file__).resolve().parents[2] / ".env"
    if not arquivo.exists():
        return None
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if linha.startswith("KEYCLOAK_TESTES_CLIENT_SECRET="):
            return linha.split("=", 1)[1].strip()
    return None


@pytest.fixture
def config() -> Configuracao:
    return obter_configuracao()


@pytest.fixture
async def cliente_http(config: Configuracao) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=config.keycloak_timeout_segundos) as cliente:
        yield cliente


@pytest.fixture
async def keycloak_no_ar(config: Configuracao, cliente_http: httpx.AsyncClient) -> None:
    try:
        resposta = await cliente_http.get(config.keycloak_jwks_url)
    except httpx.HTTPError:
        pytest.skip("Keycloak indisponível — rode `docker compose up -d`")
    if resposta.status_code != httpx.codes.OK:
        pytest.skip("Keycloak respondeu, mas o realm fisioagenda não está pronto")


@pytest.fixture
async def admin(
    config: Configuracao, cliente_http: httpx.AsyncClient, keycloak_no_ar: None
) -> KeycloakAdmin:
    return KeycloakAdmin(config, cliente_http)


@pytest.fixture
async def usuario_descartavel(admin: KeycloakAdmin) -> AsyncIterator[tuple[uuid.UUID, str]]:
    email = f"teste-{uuid.uuid4().hex[:12]}@exemplo.local"
    keycloak_id = await admin.criar_usuario(
        email=email, nome="Teste Automatizado", senha=SENHA_DE_TESTE
    )
    try:
        yield keycloak_id, email
    finally:
        await admin.remover_usuario(keycloak_id)


async def _token_do_usuario(
    config: Configuracao, cliente_http: httpx.AsyncClient, email: str
) -> str:
    segredo = _segredo_do_client_de_testes()
    if not segredo:
        pytest.skip("KEYCLOAK_TESTES_CLIENT_SECRET ausente no .env da raiz")

    resposta = await cliente_http.post(
        config.keycloak_token_url,
        data={
            "grant_type": "password",
            "client_id": "fisioagenda-testes",
            "client_secret": segredo,
            "username": email,
            "password": SENHA_DE_TESTE,
        },
    )
    resposta.raise_for_status()
    return str(resposta.json()["access_token"])


async def test_service_account_obtem_token_com_client_credentials(admin: KeycloakAdmin) -> None:
    """Prova que o segredo do .env chegou ao realm — o placeholder ${VAR} do
    realm.json só é interpolado com o allowlist configurado (ADR-010)."""
    encontrado = await admin.buscar_por_email("nao-existe-ninguem@exemplo.local")

    assert encontrado is None  # a chamada em si já exigiu autenticar


async def test_ciclo_de_vida_do_usuario_na_admin_api(
    admin: KeycloakAdmin, usuario_descartavel: tuple[uuid.UUID, str]
) -> None:
    keycloak_id, email = usuario_descartavel

    assert await admin.buscar_por_email(email) == keycloak_id

    await admin.definir_habilitado(keycloak_id, habilitado=False)
    await admin.atualizar_usuario(keycloak_id, nome="Teste Renomeado")


async def test_email_duplicado_vira_conflito(
    admin: KeycloakAdmin, usuario_descartavel: tuple[uuid.UUID, str]
) -> None:
    _, email = usuario_descartavel

    with pytest.raises(UsuarioJaExisteNoIdpError):
        await admin.criar_usuario(email=email, nome="Outro", senha=SENHA_DE_TESTE)


async def test_token_emitido_pelo_keycloak_passa_na_verificacao(
    config: Configuracao,
    cliente_http: httpx.AsyncClient,
    usuario_descartavel: tuple[uuid.UUID, str],
) -> None:
    """O teste que mais importa: realm, mapper de audiência e verificador
    concordando entre si, contra o Keycloak de verdade."""
    keycloak_id, email = usuario_descartavel
    token = await _token_do_usuario(config, cliente_http, email)

    verificado = await verificar_token(token, config, CacheDeChaves(config, cliente_http))

    assert verificado.sub == keycloak_id
    assert verificado.email == email
    # Só chega aqui se o mapper de audiência do realm colocou o client da API
    # no `aud` — sem ele, a verificação teria falhado.
    assert "fisio-usuario" in verificado.papeis_de_realm


async def test_token_do_keycloak_e_recusado_com_audiencia_errada(
    config: Configuracao,
    cliente_http: httpx.AsyncClient,
    usuario_descartavel: tuple[uuid.UUID, str],
) -> None:
    _, email = usuario_descartavel
    token = await _token_do_usuario(config, cliente_http, email)

    config_de_outra_api = config.model_copy(update={"keycloak_client_id": "outra-api"})

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(token, config_de_outra_api, CacheDeChaves(config, cliente_http))
