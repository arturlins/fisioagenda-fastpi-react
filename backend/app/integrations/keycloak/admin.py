"""Cliente da Admin API do Keycloak.

Autentica por `client_credentials` com o service account do client confidencial
`fisioagenda-backend`, que tem apenas `manage-users`, `view-users` e
`query-users`. As credenciais de admin raiz do realm não passam por aqui.

Toda falha de rede ou 5xx do Keycloak vira `IntegracaoError` (502): o problema
não é desta aplicação, e a distinção importa para quem opera.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx

from app.core.config import Configuracao
from app.exceptions.domain import ConflitoDeEstadoError, IntegracaoError

_logger = logging.getLogger("fisioagenda.keycloak.admin")

# Margem antes do vencimento: um token que expira durante a requisição em voo
# custa um 401 inexplicável.
_MARGEM_DE_RENOVACAO_S = 30.0


def _separar_nome(nome: str) -> tuple[str, str]:
    """Divide o nome completo em primeiro e último para o Keycloak.

    A fonte de verdade do nome é `usuarios.nome`, um campo só. O Keycloak exige
    os dois preenchidos para considerar o perfil completo, então nome de uma
    palavra repete: melhor redundante do que login bloqueado.
    """
    partes = nome.strip().split()
    if not partes:
        return ("Usuário", "Usuário")
    if len(partes) == 1:
        return (partes[0], partes[0])
    return (partes[0], " ".join(partes[1:]))


class UsuarioJaExisteNoIdpError(ConflitoDeEstadoError):
    codigo = "email_ja_cadastrado"

    def __init__(self, email: str) -> None:
        super().__init__(f"Já existe usuário com o e-mail {email} no provedor de identidade.")


class KeycloakAdmin:
    def __init__(self, config: Configuracao, cliente: httpx.AsyncClient) -> None:
        self._config = config
        self._cliente = cliente
        self._token: str | None = None
        self._expira_em: float = 0.0

    # --- autenticação do próprio cliente -------------------------------------

    async def _obter_token(self) -> str:
        if self._token and time.monotonic() < self._expira_em:
            return self._token

        try:
            resposta = await self._cliente.post(
                self._config.keycloak_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config.keycloak_client_id,
                    "client_secret": self._config.keycloak_client_secret.get_secret_value(),
                },
            )
            resposta.raise_for_status()
            corpo = resposta.json()
        except httpx.HTTPError as erro:
            _logger.exception("falha ao obter token de service account")
            raise IntegracaoError("Keycloak") from erro

        self._token = str(corpo["access_token"])
        self._expira_em = time.monotonic() + float(corpo["expires_in"]) - _MARGEM_DE_RENOVACAO_S
        return self._token

    async def _requisitar(self, metodo: str, caminho: str, **kwargs: Any) -> httpx.Response:
        token = await self._obter_token()
        url = f"{self._config.keycloak_admin_url}{caminho}"
        try:
            return await self._cliente.request(
                metodo, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
        except httpx.HTTPError as erro:
            _logger.exception("falha de rede ao falar com a Admin API")
            raise IntegracaoError("Keycloak") from erro

    @staticmethod
    def _garantir_sucesso(resposta: httpx.Response, operacao: str) -> None:
        if resposta.is_success:
            return
        # O corpo do Keycloak pode trazer detalhe de configuração do realm; ele
        # vai para o log, não para o cliente da nossa API.
        _logger.error(
            "Admin API respondeu erro",
            extra={"operacao": operacao, "status": resposta.status_code},
        )
        raise IntegracaoError("Keycloak")

    # --- operações sobre usuários --------------------------------------------

    async def criar_usuario(self, *, email: str, nome: str, senha: str) -> uuid.UUID:
        """Cria o usuário e devolve o `sub`, que vira `usuarios.keycloak_id`."""
        primeiro, ultimo = _separar_nome(nome)
        resposta = await self._requisitar(
            "POST",
            "/users",
            json={
                "username": email,
                "email": email,
                "firstName": primeiro,
                "lastName": ultimo,
                "enabled": True,
                "emailVerified": True,
                # Perfil completo e sem pendências: com qualquer ação obrigatória
                # em aberto, o Keycloak recusa o login com "Account is not fully
                # set up" — inclusive quando o sobrenome vai vazio.
                "requiredActions": [],
                "credentials": [{"type": "password", "value": senha, "temporary": False}],
            },
        )

        if resposta.status_code == httpx.codes.CONFLICT:
            raise UsuarioJaExisteNoIdpError(email)
        self._garantir_sucesso(resposta, "criar_usuario")

        # O Keycloak devolve 201 com Location terminando no id; quando o
        # cabeçalho não vem, consultar por username é o caminho de reserva.
        local = resposta.headers.get("Location", "")
        if local:
            return uuid.UUID(local.rstrip("/").rsplit("/", 1)[-1])

        encontrado = await self.buscar_por_email(email)
        if encontrado is None:
            raise IntegracaoError("Keycloak", "Usuário criado mas não localizado no Keycloak.")
        return encontrado

    async def buscar_por_email(self, email: str) -> uuid.UUID | None:
        resposta = await self._requisitar(
            "GET", "/users", params={"username": email, "exact": "true"}
        )
        self._garantir_sucesso(resposta, "buscar_por_email")
        encontrados: list[dict[str, Any]] = resposta.json()
        return uuid.UUID(encontrados[0]["id"]) if encontrados else None

    async def atualizar_usuario(self, keycloak_id: uuid.UUID, *, email: str, nome: str) -> None:
        """Envia o perfil completo, nunca um campo isolado.

        O User Profile do Keycloak valida a representacao inteira no PUT: mandar
        so o e-mail faz `firstName` e `lastName` chegarem vazios e a atualizacao
        volta 400. Por isso os dois valores atuais sao sempre exigidos aqui.
        """
        primeiro, ultimo = _separar_nome(nome)
        resposta = await self._requisitar(
            "PUT",
            f"/users/{keycloak_id}",
            json={
                "username": email,
                "email": email,
                "firstName": primeiro,
                "lastName": ultimo,
            },
        )
        if resposta.status_code == httpx.codes.CONFLICT:
            raise UsuarioJaExisteNoIdpError(email)
        self._garantir_sucesso(resposta, "atualizar_usuario")

    async def definir_habilitado(self, keycloak_id: uuid.UUID, *, habilitado: bool) -> None:
        """Desabilitar é o que o soft delete faz no IdP: a conta perde acesso
        imediatamente, mas o histórico de quem fez o quê continua resolvível."""
        resposta = await self._requisitar(
            "PUT", f"/users/{keycloak_id}", json={"enabled": habilitado}
        )
        self._garantir_sucesso(resposta, "definir_habilitado")

    async def remover_usuario(self, keycloak_id: uuid.UUID) -> None:
        """Usado como compensação quando a gravação local falha (ADR-006)."""
        resposta = await self._requisitar("DELETE", f"/users/{keycloak_id}")
        if resposta.status_code == httpx.codes.NOT_FOUND:
            return  # já não existe: o efeito desejado é o mesmo
        self._garantir_sucesso(resposta, "remover_usuario")
