"""Configuração da aplicação.

Tudo vem do ambiente. Nenhum valor sensível tem default utilizável: se a senha do
banco não estiver definida, a aplicação não sobe — falha alta e cedo, em vez de
conectar em algum lugar inesperado.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Ambiente(StrEnum):
    DESENVOLVIMENTO = "desenvolvimento"
    TESTE = "teste"
    PRODUCAO = "producao"


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- Aplicação -----------------------------------------------------------
    app_nome: str = "FisioAgenda API"
    app_versao: str = "0.1.0"
    ambiente: Ambiente = Ambiente.DESENVOLVIMENTO

    # --- Banco ---------------------------------------------------------------
    # O compose publica o Postgres em 127.0.0.1:5433 (a 5432 pode estar ocupada
    # por uma instalação nativa).
    banco_host: str = "127.0.0.1"
    banco_porta: int = 5433
    banco_nome: str = "fisioagenda"
    banco_usuario: str = "fisioagenda_app"
    banco_senha: SecretStr
    banco_echo: bool = False
    banco_pool_tamanho: int = Field(default=5, ge=1)
    banco_pool_overflow: int = Field(default=10, ge=0)

    # --- Keycloak ------------------------------------------------------------
    keycloak_url: str = "http://127.0.0.1:8080"
    keycloak_realm: str = "fisioagenda"
    # Client confidencial da API. O service account dele fala com a Admin API;
    # as credenciais de admin raiz do Keycloak nunca entram aqui.
    keycloak_client_id: str = "fisioagenda-backend"
    keycloak_client_secret: SecretStr
    keycloak_timeout_segundos: float = 10.0
    # Tempo mínimo entre recargas do JWKS. Sem isso, token com `kid` inválido
    # viraria um vetor de carga contra o Keycloak: uma requisição de rede por
    # requisição HTTP maliciosa.
    keycloak_jwks_intervalo_minimo_s: float = 30.0

    # --- HTTP ----------------------------------------------------------------
    http_host: str = "127.0.0.1"
    http_porta: int = 8000
    cors_origens: list[str] = ["http://localhost:5173"]

    # --- Log -----------------------------------------------------------------
    log_nivel: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_formato: Literal["json", "texto"] = "json"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def banco_url(self) -> str:
        """DSN assíncrono. psycopg 3 acompanha o ciclo de release do Postgres (ADR-003)."""
        senha = self.banco_senha.get_secret_value()
        return (
            f"postgresql+psycopg://{self.banco_usuario}:{senha}"
            f"@{self.banco_host}:{self.banco_porta}/{self.banco_nome}"
        )

    @property
    def e_producao(self) -> bool:
        return self.ambiente is Ambiente.PRODUCAO

    # --- URLs derivadas do Keycloak ------------------------------------------
    # Montadas aqui, uma vez, para que nenhuma camada precise concatenar caminho
    # de OIDC à mão.

    @property
    def keycloak_emissor(self) -> str:
        """Valor esperado da claim `iss`. Comparado byte a byte na verificação."""
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_emissor}/protocol/openid-connect/certs"

    @property
    def keycloak_token_url(self) -> str:
        return f"{self.keycloak_emissor}/protocol/openid-connect/token"

    @property
    def keycloak_admin_url(self) -> str:
        return f"{self.keycloak_url}/admin/realms/{self.keycloak_realm}"


@lru_cache
def obter_configuracao() -> Configuracao:
    """Instância única. `lru_cache` permite substituir a configuração nos testes."""
    return Configuracao()
