"""Repository de contas."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organizacao import Conta


class ContaRepository:
    def __init__(self, sessao: AsyncSession) -> None:
        self._sessao = sessao

    async def adicionar(self, conta: Conta) -> Conta:
        """`flush` e não `commit`: a transação fecha no fim da requisição.

        O flush é necessário porque o `id` gerado pelo banco é usado logo em
        seguida, para vincular o usuário dono à conta.
        """
        self._sessao.add(conta)
        await self._sessao.flush()
        await self._sessao.refresh(conta)
        return conta

    async def existe_cnpj(self, cnpj: str) -> bool:
        consulta = select(Conta.id).where(Conta.cnpj == cnpj)
        return (await self._sessao.execute(consulta)).first() is not None
