"""Repository de clínicas e dos vínculos com usuários.

Toda consulta é escopada por `conta_id`: sem isso, um `public_id` adivinhado
alcançaria a clínica de outro tenant. O escopo não é opcional na assinatura.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.acesso import ClinicaUsuario, Usuario
from app.models.organizacao import Clinica


class ClinicaRepository:
    def __init__(self, sessao: AsyncSession) -> None:
        self._sessao = sessao

    # --- clínicas ------------------------------------------------------------

    async def buscar_por_public_id(self, conta_id: int, public_id: uuid.UUID) -> Clinica | None:
        consulta = select(Clinica).where(
            Clinica.public_id == public_id,
            Clinica.conta_id == conta_id,
        )
        return (await self._sessao.execute(consulta)).scalar_one_or_none()

    async def listar(self, conta_id: int) -> list[Clinica]:
        consulta = select(Clinica).where(Clinica.conta_id == conta_id).order_by(Clinica.nome)
        return list((await self._sessao.execute(consulta)).scalars())

    async def existe_nome(self, conta_id: int, nome: str, *, ignorando: int | None = None) -> bool:
        consulta = select(Clinica.id).where(
            Clinica.conta_id == conta_id,
            func.lower(Clinica.nome) == nome.lower(),
        )
        if ignorando is not None:
            consulta = consulta.where(Clinica.id != ignorando)
        return (await self._sessao.execute(consulta)).first() is not None

    async def adicionar(self, clinica: Clinica) -> Clinica:
        self._sessao.add(clinica)
        await self._sessao.flush()
        await self._sessao.refresh(clinica)
        return clinica

    async def sincronizar(self, clinica: Clinica) -> Clinica:
        await self._sessao.flush()
        await self._sessao.refresh(clinica)
        return clinica

    async def remover(self, clinica: Clinica) -> None:
        """Exclusão física — `clinicas` não tem soft delete no esquema.

        As chaves estrangeiras que apontam para cá são `ON DELETE CASCADE`, então
        remover a clínica leva junto agenda e financeiro dela. Quem chama precisa
        ter verificado que isso é o desejado.
        """
        await self._sessao.delete(clinica)
        await self._sessao.flush()

    # --- vínculos ------------------------------------------------------------

    async def buscar_vinculo(self, clinica_id: int, usuario_id: int) -> ClinicaUsuario | None:
        consulta = select(ClinicaUsuario).where(
            ClinicaUsuario.clinica_id == clinica_id,
            ClinicaUsuario.usuario_id == usuario_id,
        )
        return (await self._sessao.execute(consulta)).scalar_one_or_none()

    async def listar_vinculos(self, clinica_id: int) -> list[ClinicaUsuario]:
        consulta = (
            select(ClinicaUsuario)
            .where(ClinicaUsuario.clinica_id == clinica_id)
            .options(selectinload(ClinicaUsuario.usuario))
            .join(Usuario, Usuario.id == ClinicaUsuario.usuario_id)
            .where(Usuario.excluido_em.is_(None))
            .order_by(Usuario.nome)
        )
        return list((await self._sessao.execute(consulta)).scalars())

    async def adicionar_vinculo(self, vinculo: ClinicaUsuario) -> ClinicaUsuario:
        self._sessao.add(vinculo)
        await self._sessao.flush()
        await self._sessao.refresh(vinculo)
        return vinculo

    async def remover_vinculo(self, vinculo: ClinicaUsuario) -> None:
        await self._sessao.delete(vinculo)
        await self._sessao.flush()
