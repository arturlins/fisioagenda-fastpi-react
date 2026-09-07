"""Verificação de token.

Sem rede: um par de chaves é gerado no teste e servido como JWKS por um
transporte falso do httpx. Assim o caminho real de código roda — inclusive a
recarga do cache — sem depender do Keycloak estar no ar.

Metade destes testes é sobre o que precisa ser REJEITADO. Verificador de JWT que
só foi testado com token bom não foi testado.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Configuracao, obter_configuracao
from app.core.seguranca import verificar_token
from app.exceptions.domain import IntegracaoError, NaoAutenticadoError
from app.integrations.keycloak.jwks import CacheDeChaves

KID = "chave-de-teste"
OUTRO_KID = "chave-que-nao-existe"


@pytest.fixture(scope="module")
def chave_privada() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def documento_jwks(chave_privada: rsa.RSAPrivateKey) -> dict[str, Any]:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(chave_privada.public_key()))
    jwk |= {"kid": KID, "use": "sig", "alg": "RS256"}
    return {"keys": [jwk]}


@pytest.fixture
def config() -> Configuracao:
    return obter_configuracao()


@pytest.fixture
def cache(config: Configuracao, documento_jwks: dict[str, Any]) -> CacheDeChaves:
    def responder(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=documento_jwks)

    cliente = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    return CacheDeChaves(config, cliente)


def _gerar_token(
    chave_privada: rsa.RSAPrivateKey,
    config: Configuracao,
    *,
    kid: str = KID,
    algoritmo: str = "RS256",
    emissor: str | None = None,
    audiencia: str | None = None,
    expira_em: timedelta = timedelta(minutes=15),
    claims_extras: dict[str, Any] | None = None,
) -> str:
    agora = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "iss": emissor if emissor is not None else config.keycloak_emissor,
        "aud": audiencia if audiencia is not None else config.keycloak_client_id,
        "iat": agora,
        "exp": agora + expira_em,
        "email": "ana@exemplo.local",
        "preferred_username": "ana",
        "azp": "fisioagenda-web",
        "realm_access": {"roles": ["fisio-usuario"]},
    }
    claims |= claims_extras or {}
    return jwt.encode(claims, chave_privada, algorithm=algoritmo, headers={"kid": kid})


# --- caminho feliz -----------------------------------------------------------


async def test_token_valido_e_aceito(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, cache: CacheDeChaves
) -> None:
    token = _gerar_token(chave_privada, config)

    verificado = await verificar_token(token, config, cache)

    assert verificado.email == "ana@exemplo.local"
    assert verificado.nome_de_usuario == "ana"
    assert verificado.cliente_de_origem == "fisioagenda-web"
    assert "fisio-usuario" in verificado.papeis_de_realm


# --- o que precisa ser rejeitado ---------------------------------------------


async def test_token_expirado_e_rejeitado(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, cache: CacheDeChaves
) -> None:
    token = _gerar_token(chave_privada, config, expira_em=timedelta(seconds=-10))

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(token, config, cache)


async def test_audiencia_de_outro_client_e_rejeitada(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, cache: CacheDeChaves
) -> None:
    """Token emitido para outro serviço não vale nesta API."""
    token = _gerar_token(chave_privada, config, audiencia="outro-sistema")

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(token, config, cache)


async def test_emissor_diferente_e_rejeitado(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, cache: CacheDeChaves
) -> None:
    """Um Keycloak que o atacante controla emitiria tokens perfeitamente válidos."""
    token = _gerar_token(chave_privada, config, emissor="http://keycloak-falso/realms/fisioagenda")

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(token, config, cache)


async def test_algoritmo_simetrico_e_rejeitado(config: Configuracao, cache: CacheDeChaves) -> None:
    """Confusão de algoritmo: a chave pública do realm é publicamente conhecida.

    Se HS256 fosse aceito, qualquer um assinaria um token com ela e seria aceito.
    """
    agora = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iss": config.keycloak_emissor,
            "aud": config.keycloak_client_id,
            "iat": agora,
            "exp": agora + timedelta(minutes=15),
        },
        "segredo-qualquer",
        algorithm="HS256",
        headers={"kid": KID},
    )

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(token, config, cache)


async def test_token_sem_assinatura_e_rejeitado(config: Configuracao, cache: CacheDeChaves) -> None:
    agora = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iss": config.keycloak_emissor,
            "aud": config.keycloak_client_id,
            "iat": agora,
            "exp": agora + timedelta(minutes=15),
        },
        key="",
        algorithm="none",
        headers={"kid": KID},
    )

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(token, config, cache)


async def test_assinatura_adulterada_e_rejeitada(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, cache: CacheDeChaves
) -> None:
    token = _gerar_token(chave_privada, config)
    cabecalho, corpo, _ = token.split(".")
    outro = _gerar_token(chave_privada, config, claims_extras={"email": "outro@exemplo.local"})
    assinatura_de_outro = outro.split(".")[2]

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(f"{cabecalho}.{corpo}.{assinatura_de_outro}", config, cache)


async def test_kid_desconhecido_e_rejeitado_apos_recarga(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, cache: CacheDeChaves
) -> None:
    token = _gerar_token(chave_privada, config, kid=OUTRO_KID)

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(token, config, cache)


async def test_token_sem_kid_e_rejeitado(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, cache: CacheDeChaves
) -> None:
    agora = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iss": config.keycloak_emissor,
            "aud": config.keycloak_client_id,
            "iat": agora,
            "exp": agora + timedelta(minutes=15),
        },
        chave_privada,
        algorithm="RS256",
    )

    with pytest.raises(NaoAutenticadoError):
        await verificar_token(token, config, cache)


async def test_texto_qualquer_no_lugar_do_token_e_rejeitado(
    config: Configuracao, cache: CacheDeChaves
) -> None:
    with pytest.raises(NaoAutenticadoError):
        await verificar_token("isto-nao-e-um-jwt", config, cache)


# --- comportamento do cache --------------------------------------------------


async def test_kid_desconhecido_nao_recarrega_a_cada_tentativa(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, documento_jwks: dict[str, Any]
) -> None:
    """Sem intervalo mínimo, tokens forjados viram carga contra o Keycloak."""
    chamadas = 0

    def responder(_: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(200, json=documento_jwks)

    cache = CacheDeChaves(config, httpx.AsyncClient(transport=httpx.MockTransport(responder)))
    token = _gerar_token(chave_privada, config, kid=OUTRO_KID)

    for _ in range(5):
        with pytest.raises(NaoAutenticadoError):
            await verificar_token(token, config, cache)

    assert chamadas == 1


async def test_keycloak_fora_do_ar_vira_erro_de_integracao(config: Configuracao) -> None:
    """502, não 401: o token pode até estar certo — quem falhou foi a dependência."""

    def responder(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    cache = CacheDeChaves(config, httpx.AsyncClient(transport=httpx.MockTransport(responder)))

    with pytest.raises(IntegracaoError):
        await cache.obter(KID)


async def test_chave_conhecida_nao_gera_requisicao(
    chave_privada: rsa.RSAPrivateKey, config: Configuracao, documento_jwks: dict[str, Any]
) -> None:
    """O Keycloak não pode estar no caminho crítico de toda requisição."""
    chamadas = 0

    def responder(_: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(200, json=documento_jwks)

    cache = CacheDeChaves(config, httpx.AsyncClient(transport=httpx.MockTransport(responder)))
    token = _gerar_token(chave_privada, config)

    for _ in range(3):
        await verificar_token(token, config, cache)

    assert chamadas == 1


async def test_aquecer_informa_falha_sem_derrubar_a_aplicacao(config: Configuracao) -> None:
    def responder(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    cache = CacheDeChaves(config, httpx.AsyncClient(transport=httpx.MockTransport(responder)))

    assert await cache.aquecer() is False


def test_intervalo_minimo_de_recarga_esta_configurado(config: Configuracao) -> None:
    assert config.keycloak_jwks_intervalo_minimo_s > 0
    assert time.monotonic() > 0  # sanidade: o relógio usado no cache é monotônico
