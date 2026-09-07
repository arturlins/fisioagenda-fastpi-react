"""Cache das chaves públicas do Keycloak.

Buscar o JWKS a cada requisição colocaria o Keycloak no caminho crítico de toda
chamada da API. Buscar uma vez e nunca mais quebraria na rotação de chaves. O
meio-termo é cachear e recarregar quando aparece um `kid` desconhecido — que é
exatamente o sintoma de rotação.

A recarga tem intervalo mínimo: sem ele, um atacante mandando tokens com `kid`
aleatório força uma requisição de rede por requisição HTTP.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from jwt import PyJWK

from app.core.config import Configuracao
from app.exceptions.domain import IntegracaoError, NaoAutenticadoError

_logger = logging.getLogger("fisioagenda.keycloak.jwks")


class CacheDeChaves:
    """Chaves públicas do realm, indexadas por `kid`."""

    def __init__(self, config: Configuracao, cliente: httpx.AsyncClient) -> None:
        self._config = config
        self._cliente = cliente
        self._chaves: dict[str, PyJWK] = {}
        self._carregado_em: float = 0.0
        # Serializa recargas concorrentes: sob rajada, uma requisição busca e as
        # demais aproveitam o resultado.
        self._trava = asyncio.Lock()

    async def obter(self, kid: str) -> PyJWK:
        chave = self._chaves.get(kid)
        if chave is not None:
            return chave

        await self._recarregar()

        chave = self._chaves.get(kid)
        if chave is None:
            # Depois de recarregar, `kid` desconhecido é token forjado ou de
            # outro realm — não é problema de cache.
            _logger.warning("token com kid desconhecido", extra={"kid": kid})
            raise NaoAutenticadoError
        return chave

    async def _recarregar(self) -> None:
        async with self._trava:
            agora = time.monotonic()
            if agora - self._carregado_em < self._config.keycloak_jwks_intervalo_minimo_s:
                return

            try:
                resposta = await self._cliente.get(self._config.keycloak_jwks_url)
                resposta.raise_for_status()
                documento: dict[str, Any] = resposta.json()
            except httpx.HTTPError as erro:
                _logger.exception("falha ao obter o JWKS do Keycloak")
                raise IntegracaoError("Keycloak") from erro

            self._chaves = {
                chave["kid"]: PyJWK(chave)
                for chave in documento.get("keys", [])
                if chave.get("kid") and chave.get("use", "sig") == "sig"
            }
            self._carregado_em = agora
            _logger.info("JWKS recarregado", extra={"chaves": len(self._chaves)})

    async def aquecer(self) -> bool:
        """Carrega as chaves na subida. Retorna se o Keycloak respondeu."""
        try:
            await self._recarregar()
        except IntegracaoError:
            return False
        return bool(self._chaves)
