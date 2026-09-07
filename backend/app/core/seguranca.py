"""Verificação de token e modelo do portador autenticado.

O que este módulo NUNCA faz: confiar em claim sem verificar a assinatura. Não
existe `verify_signature=False` em lugar nenhum do projeto — decodificar um JWT
sem validar é o mesmo que aceitar o que o cliente disser sobre si mesmo.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt

from app.core.config import Configuracao
from app.exceptions.domain import NaoAutenticadoError
from app.integrations.keycloak.jwks import CacheDeChaves
from app.models.acesso import ClinicaUsuario, Usuario
from app.models.enums import PapelUsuario

_logger = logging.getLogger("fisioagenda.seguranca")

# Só assinatura assimétrica. Aceitar HS* permitiria o ataque clássico de
# confusão de algoritmo: assinar um token com a chave pública do realm, que é
# publicamente conhecida, e ser aceito como se fosse RSA.
ALGORITMOS_ACEITOS = ("RS256", "RS384", "RS512")


@dataclass(frozen=True, slots=True)
class TokenVerificado:
    """O que o token afirma, depois de a assinatura ter sido conferida."""

    sub: uuid.UUID
    email: str | None
    nome_de_usuario: str | None
    cliente_de_origem: str | None
    papeis_de_realm: frozenset[str]

    @classmethod
    def de_claims(cls, claims: dict[str, Any]) -> TokenVerificado:
        try:
            sub = uuid.UUID(claims["sub"])
        except (KeyError, ValueError) as erro:
            raise NaoAutenticadoError from erro

        papeis = claims.get("realm_access", {}).get("roles", [])
        return cls(
            sub=sub,
            email=claims.get("email"),
            nome_de_usuario=claims.get("preferred_username"),
            cliente_de_origem=claims.get("azp"),
            papeis_de_realm=frozenset(papeis),
        )


async def verificar_token(
    token: str, config: Configuracao, cache: CacheDeChaves
) -> TokenVerificado:
    """Valida assinatura, emissor, audiência e validade temporal."""
    try:
        cabecalho = jwt.get_unverified_header(token)
    except jwt.PyJWTError as erro:
        raise NaoAutenticadoError from erro

    if cabecalho.get("alg") not in ALGORITMOS_ACEITOS:
        _logger.warning("token com algoritmo recusado", extra={"alg": cabecalho.get("alg")})
        raise NaoAutenticadoError

    kid = cabecalho.get("kid")
    if not kid:
        raise NaoAutenticadoError

    chave = await cache.obter(kid)

    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key=chave.key,
            algorithms=list(ALGORITMOS_ACEITOS),
            audience=config.keycloak_client_id,
            issuer=config.keycloak_emissor,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
    except jwt.PyJWTError as erro:
        # O motivo exato — expirado, audiência errada, assinatura inválida —
        # fica no log. A resposta é sempre a mesma: ver `NaoAutenticadoError`.
        _logger.info("token rejeitado", extra={"motivo": type(erro).__name__})
        raise NaoAutenticadoError from erro

    return TokenVerificado.de_claims(claims)


@dataclass(frozen=True, slots=True)
class UsuarioAutenticado:
    """O usuário do domínio por trás do token, com os privilégios dele.

    Identidade vem do Keycloak; permissão por clínica vem do banco (ADR-005).
    """

    usuario: Usuario
    token: TokenVerificado
    vinculos: tuple[ClinicaUsuario, ...] = field(default=())

    @property
    def conta_id(self) -> int:
        return self.usuario.conta_id

    @property
    def e_dono_da_conta(self) -> bool:
        return self.usuario.dono_da_conta

    def papel_em(self, clinica_id: int) -> PapelUsuario | None:
        for vinculo in self.vinculos:
            if vinculo.clinica_id == clinica_id and vinculo.ativo:
                return vinculo.papel
        return None

    def administra(self, clinica_id: int) -> bool:
        """Dono da conta tem acesso irrestrito, sem depender de vínculo."""
        if self.e_dono_da_conta:
            return True
        return self.papel_em(clinica_id) is PapelUsuario.ADMINISTRADOR

    def enxerga(self, clinica_id: int) -> bool:
        if self.e_dono_da_conta:
            return True
        return self.papel_em(clinica_id) is not None
