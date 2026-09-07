"""Registro de conta.

É o único caso de uso do sistema que escreve em dois sistemas sem transação
distribuída entre eles: o Keycloak e o Postgres. A ordem e a compensação estão
no ADR-006, e a razão delas está comentada abaixo.
"""

from __future__ import annotations

import logging
import uuid

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.keycloak.admin import KeycloakAdmin
from app.models.acesso import Usuario
from app.models.organizacao import Conta
from app.repositories.conta_repository import ContaRepository
from app.repositories.usuario_repository import UsuarioRepository

_logger = logging.getLogger("fisioagenda.contas")


class ContaService:
    def __init__(
        self,
        sessao: AsyncSession,
        conta_repository: ContaRepository,
        usuario_repository: UsuarioRepository,
        keycloak: KeycloakAdmin,
    ) -> None:
        # A sessão entra aqui, e não só nos repositórios, porque este caso de uso
        # precisa saber se o commit deu certo para decidir compensar. É a única
        # exceção ao ADR-004, e ela é deliberada.
        self._sessao = sessao
        self._contas = conta_repository
        self._usuarios = usuario_repository
        self._keycloak = keycloak

    async def registrar(
        self, conta: Conta, dono: Usuario, senha: SecretStr
    ) -> tuple[Conta, Usuario]:
        """Recebe as entidades já montadas pelo Controller e as persiste."""
        # Cria primeiro no Keycloak: se a ordem fosse inversa e o IdP falhasse,
        # ficaria uma linha local apontando para um `keycloak_id` inexistente —
        # usuário que não loga e não pode ser recriado, porque o índice único de
        # e-mail bloqueia. Aqui, o pior caso é um usuário órfão no Keycloak:
        # falha visível e reparável, em vez de silenciosa.
        keycloak_id = await self._keycloak.criar_usuario(
            email=dono.email, nome=dono.nome, senha=senha.get_secret_value()
        )

        try:
            conta = await self._contas.adicionar(conta)
            # O elo entre os dois só existe depois de a conta ganhar id no banco.
            dono.conta_id = conta.id
            dono.keycloak_id = keycloak_id
            dono = await self._usuarios.adicionar(dono)
            await self._sessao.commit()
        except Exception:
            await self._sessao.rollback()
            await self._compensar(keycloak_id)
            raise

        _logger.info(
            "conta registrada",
            extra={"conta_public_id": str(conta.public_id), "dono": str(dono.public_id)},
        )
        return conta, dono

    async def _compensar(self, keycloak_id: uuid.UUID) -> None:
        """Desfaz o usuário criado no Keycloak quando a gravação local falha.

        A falha da própria compensação não pode mascarar o erro original — por
        isso ela é registrada em nível crítico e engolida aqui: quem sobe é a
        exceção que realmente explica o que aconteceu.
        """
        try:
            await self._keycloak.remover_usuario(keycloak_id)
        except Exception:
            _logger.critical(
                "usuário órfão no Keycloak: criado, mas não gravado localmente",
                extra={"keycloak_id": str(keycloak_id)},
                exc_info=True,
            )
