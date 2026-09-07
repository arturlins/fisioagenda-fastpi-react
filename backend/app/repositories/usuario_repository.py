"""Repository de usuários.

Isola o ORM do resto da aplicação: nenhuma camada acima daqui monta `select`.
Não faz commit — a unidade de trabalho é a requisição (ADR-004).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.acesso import Usuario


class UsuarioRepository:
    def __init__(self, sessao: AsyncSession) -> None:
        self._sessao = sessao

    async def buscar_por_keycloak_id(self, keycloak_id: uuid.UUID) -> Usuario | None:
        """Resolve o portador do token para o usuário do domínio.

        Carrega os vínculos junto: os relacionamentos são `lazy="raise"`, e a
        autorização precisa dos papéis por clínica na mesma requisição.
        """
        consulta = (
            select(Usuario)
            .where(Usuario.keycloak_id == keycloak_id, Usuario.excluido_em.is_(None))
            .options(selectinload(Usuario.vinculos))
        )
        return (await self._sessao.execute(consulta)).scalar_one_or_none()
