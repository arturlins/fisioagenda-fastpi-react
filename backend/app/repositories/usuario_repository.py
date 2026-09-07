"""Repository de usuários.

Isola o ORM do resto da aplicação: nenhuma camada acima daqui monta `select`.
Não faz commit — a unidade de trabalho é a requisição (ADR-004).

Toda consulta é escopada por `conta_id`. Um `public_id` adivinhado não pode
alcançar o tenant vizinho, e a única forma de garantir isso é o escopo não ser
opcional na assinatura dos métodos.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.acesso import ClinicaUsuario, Usuario


class UsuarioRepository:
    def __init__(self, sessao: AsyncSession) -> None:
        self._sessao = sessao

    # --- leitura -------------------------------------------------------------

    async def buscar_por_keycloak_id(self, keycloak_id: uuid.UUID) -> Usuario | None:
        """Resolve o portador do token para o usuário do domínio.

        Carrega vínculos e clínicas junto: os relacionamentos são `lazy="raise"`,
        e a autorização precisa dos papéis por clínica na mesma requisição.
        """
        consulta = (
            select(Usuario)
            .where(Usuario.keycloak_id == keycloak_id, Usuario.excluido_em.is_(None))
            .options(selectinload(Usuario.vinculos).selectinload(ClinicaUsuario.clinica))
        )
        return (await self._sessao.execute(consulta)).scalar_one_or_none()

    async def buscar_por_public_id(self, conta_id: int, public_id: uuid.UUID) -> Usuario | None:
        consulta = self._base(conta_id).where(Usuario.public_id == public_id)
        return (await self._sessao.execute(consulta)).scalar_one_or_none()

    async def existe_email(
        self, conta_id: int, email: str, *, ignorando: int | None = None
    ) -> bool:
        """`ignorando` permite que uma edição mantenha o próprio e-mail."""
        consulta = select(Usuario.id).where(
            Usuario.conta_id == conta_id,
            func.lower(Usuario.email) == email.lower(),
            Usuario.excluido_em.is_(None),
        )
        if ignorando is not None:
            consulta = consulta.where(Usuario.id != ignorando)
        return (await self._sessao.execute(consulta)).first() is not None

    async def listar(
        self,
        conta_id: int,
        *,
        pagina: int,
        tamanho: int,
        apenas_ativos: bool | None = None,
        apenas_profissionais: bool | None = None,
        busca: str | None = None,
    ) -> tuple[list[Usuario], int]:
        """Devolve a página e o total que casa com os filtros.

        Paginação não é enfeite: `GET /usuarios` sem limite vira transferência do
        cadastro inteiro no dia em que a conta crescer.
        """
        consulta = self._base(conta_id)
        consulta = self._aplicar_filtros(consulta, apenas_ativos, apenas_profissionais, busca)

        total = await self._sessao.scalar(select(func.count()).select_from(consulta.subquery()))

        pagina_de_dados = (
            consulta.order_by(Usuario.nome).offset((pagina - 1) * tamanho).limit(tamanho)
        )
        itens = list((await self._sessao.execute(pagina_de_dados)).scalars())
        return itens, int(total or 0)

    # --- escrita -------------------------------------------------------------

    async def adicionar(self, usuario: Usuario) -> Usuario:
        self._sessao.add(usuario)
        await self._sessao.flush()
        await self._sessao.refresh(usuario)
        return usuario

    async def sincronizar(self, usuario: Usuario) -> Usuario:
        """Persiste alterações de uma entidade já gerenciada pela sessão."""
        await self._sessao.flush()
        await self._sessao.refresh(usuario)
        return usuario

    # --- montagem de consulta ------------------------------------------------

    @staticmethod
    def _base(conta_id: int) -> Select[tuple[Usuario]]:
        return select(Usuario).where(
            Usuario.conta_id == conta_id,
            Usuario.excluido_em.is_(None),
        )

    @staticmethod
    def _aplicar_filtros(
        consulta: Select[tuple[Usuario]],
        apenas_ativos: bool | None,
        apenas_profissionais: bool | None,
        busca: str | None,
    ) -> Select[tuple[Usuario]]:
        if apenas_ativos is not None:
            consulta = consulta.where(Usuario.ativo.is_(apenas_ativos))
        if apenas_profissionais is not None:
            consulta = consulta.where(Usuario.e_profissional.is_(apenas_profissionais))
        if busca:
            # `escape` explícito: sem ele, um `%` digitado na busca casaria com
            # tudo, e um `_` com qualquer caractere.
            termo = busca.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            padrao = f"%{termo}%"
            consulta = consulta.where(
                Usuario.nome.ilike(padrao, escape="\\") | Usuario.email.ilike(padrao, escape="\\")
            )
        return consulta
