"""Repository de clínicas."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organizacao import Clinica


class ClinicaRepository:
    def __init__(self, sessao: AsyncSession) -> None:
        self._sessao = sessao

    async def buscar_por_public_id(self, conta_id: int, public_id: uuid.UUID) -> Clinica | None:
        """Sempre escopado por conta.

        Sem o `conta_id` na cláusula, um `public_id` adivinhado alcançaria a
        clínica de outro tenant. O escopo não é opcional em consulta alguma.
        """
        consulta = select(Clinica).where(
            Clinica.public_id == public_id,
            Clinica.conta_id == conta_id,
        )
        return (await self._sessao.execute(consulta)).scalar_one_or_none()
