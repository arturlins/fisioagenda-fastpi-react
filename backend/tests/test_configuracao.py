"""Configuração derivada: emissor do token e exposição da documentação.

Em produção o navegador fala com o Keycloak pela URL pública e a API fala pela
rede interna. O `iss` do token é sempre a pública — se o emissor esperado viesse
da interna, todo token seria recusado.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Ambiente, Configuracao


def _config(**extra: Any) -> Configuracao:
    return Configuracao(
        _env_file=None,
        banco_senha="x",
        keycloak_client_secret="y",
        **extra,
    )


def test_sem_url_publica_o_emissor_e_a_url_interna() -> None:
    config = _config(keycloak_url="http://127.0.0.1:8080")

    assert config.keycloak_emissor == "http://127.0.0.1:8080/realms/fisioagenda"
    assert config.keycloak_jwks_url == (
        "http://127.0.0.1:8080/realms/fisioagenda/protocol/openid-connect/certs"
    )


def test_com_url_publica_o_emissor_muda_e_o_backchannel_continua_interno() -> None:
    config = _config(
        keycloak_url="http://keycloak:8080",
        keycloak_url_publica="https://auth.203-0-113-10.sslip.io",
    )

    assert config.keycloak_emissor == "https://auth.203-0-113-10.sslip.io/realms/fisioagenda"
    assert config.keycloak_jwks_url.startswith("http://keycloak:8080/realms/fisioagenda/")
    assert config.keycloak_token_url.startswith("http://keycloak:8080/realms/fisioagenda/")
    assert config.keycloak_admin_url == "http://keycloak:8080/admin/realms/fisioagenda"


def test_barra_final_nas_urls_nao_quebra_o_emissor() -> None:
    config = _config(
        keycloak_url="http://keycloak:8080/",
        keycloak_url_publica="https://auth.exemplo.sslip.io/",
    )

    assert config.keycloak_emissor == "https://auth.exemplo.sslip.io/realms/fisioagenda"
    assert config.keycloak_admin_url == "http://keycloak:8080/admin/realms/fisioagenda"


@pytest.mark.parametrize(
    ("ambiente", "flag", "esperado"),
    [
        (Ambiente.DESENVOLVIMENTO, None, True),
        (Ambiente.PRODUCAO, None, False),
        (Ambiente.PRODUCAO, True, True),
        (Ambiente.DESENVOLVIMENTO, False, False),
    ],
)
def test_documentacao_segue_o_ambiente_salvo_flag_explicita(
    ambiente: Ambiente, flag: bool | None, esperado: bool
) -> None:
    assert _config(ambiente=ambiente, docs_habilitada=flag).documentacao_habilitada is esperado


async def _status(config: Configuracao, caminho: str) -> int:
    from app.main import criar_app

    transporte = ASGITransport(app=criar_app(config))
    async with AsyncClient(transport=transporte, base_url="http://teste") as cliente:
        return (await cliente.get(caminho)).status_code


async def test_producao_com_flag_publica_swagger_e_schema() -> None:
    config = _config(ambiente=Ambiente.PRODUCAO, docs_habilitada=True)

    assert await _status(config, "/docs") == 200
    assert await _status(config, "/openapi.json") == 200


async def test_producao_sem_flag_nao_publica_documentacao() -> None:
    config = _config(ambiente=Ambiente.PRODUCAO)

    assert await _status(config, "/docs") == 404
    assert await _status(config, "/openapi.json") == 404
