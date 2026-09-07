"""Regras de negócio de clínica e de vínculo com usuários.

Não existe guarda de "última pessoa administradora": `dono_da_conta` administra
todas as clínicas da conta sem depender de vínculo, então nenhuma unidade fica
ingerenciável por falta de administrador local. Uma guarda dessas, além de
desnecessária, criava um impasse — o último vínculo não podia ser removido, e a
clínica não podia ser excluída enquanto tivesse vínculo.
"""

from __future__ import annotations

import logging
import uuid

from app.exceptions.domain import (
    ConflitoDeEstadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
    VinculoJaExisteError,
)
from app.models.acesso import ClinicaUsuario
from app.models.enums import PapelUsuario
from app.models.organizacao import Clinica
from app.repositories.clinica_repository import ClinicaRepository
from app.repositories.usuario_repository import UsuarioRepository

_logger = logging.getLogger("fisioagenda.clinicas")


class ClinicaService:
    def __init__(self, repositorio: ClinicaRepository, usuarios: UsuarioRepository) -> None:
        self._repositorio = repositorio
        self._usuarios = usuarios

    # --- clínicas ------------------------------------------------------------

    async def listar(self, conta_id: int) -> list[Clinica]:
        return await self._repositorio.listar(conta_id)

    async def buscar(self, conta_id: int, public_id: uuid.UUID) -> Clinica:
        clinica = await self._repositorio.buscar_por_public_id(conta_id, public_id)
        if clinica is None:
            raise RecursoNaoEncontradoError.de("Clínica", public_id)
        return clinica

    async def criar(self, conta_id: int, nova: Clinica) -> Clinica:
        if await self._repositorio.existe_nome(conta_id, nova.nome):
            raise ConflitoDeEstadoError(f"Já existe uma clínica chamada {nova.nome} nesta conta.")
        nova.conta_id = conta_id
        return await self._repositorio.adicionar(nova)

    async def atualizar(self, conta_id: int, public_id: uuid.UUID, dados: Clinica) -> Clinica:
        clinica = await self.buscar(conta_id, public_id)
        if dados.nome.lower() != clinica.nome.lower() and await self._repositorio.existe_nome(
            conta_id, dados.nome, ignorando=clinica.id
        ):
            raise ConflitoDeEstadoError(f"Já existe uma clínica chamada {dados.nome} nesta conta.")

        clinica.nome = dados.nome
        clinica.fuso_horario = dados.fuso_horario
        clinica.telefone = dados.telefone
        clinica.endereco = dados.endereco
        clinica.cidade = dados.cidade
        clinica.uf = dados.uf
        clinica.ativa = dados.ativa
        return await self._repositorio.sincronizar(clinica)

    async def excluir(self, conta_id: int, public_id: uuid.UUID) -> None:
        """Remoção física, e por isso mesmo restrita a clínica sem histórico.

        As chaves que apontam para `clinicas` são `ON DELETE CASCADE`: apagar uma
        unidade com agenda levaria os agendamentos junto, em silêncio. Enquanto
        houver alguém vinculado, a exclusão é recusada — desativar é o caminho.
        """
        clinica = await self.buscar(conta_id, public_id)

        if await self._repositorio.listar_vinculos(clinica.id):
            raise RegraDeNegocioError(
                "A clínica ainda tem usuários vinculados. "
                "Remova os vínculos ou desative a clínica em vez de excluí-la."
            )

        await self._repositorio.remover(clinica)
        _logger.info("clínica excluída", extra={"clinica": str(public_id)})

    # --- vínculos ------------------------------------------------------------

    async def listar_vinculos(self, conta_id: int, public_id: uuid.UUID) -> list[ClinicaUsuario]:
        clinica = await self.buscar(conta_id, public_id)
        return await self._repositorio.listar_vinculos(clinica.id)

    async def vincular(
        self,
        conta_id: int,
        public_id: uuid.UUID,
        usuario_public_id: uuid.UUID,
        papel: PapelUsuario,
    ) -> ClinicaUsuario:
        clinica = await self.buscar(conta_id, public_id)
        usuario = await self._usuarios.buscar_por_public_id(conta_id, usuario_public_id)
        if usuario is None:
            # Escopado por conta: usuário de outro tenant é indistinguível de
            # inexistente, que é exatamente o que se quer.
            raise RecursoNaoEncontradoError.de("Usuário", usuario_public_id)

        if await self._repositorio.buscar_vinculo(clinica.id, usuario.id):
            raise VinculoJaExisteError

        vinculo = await self._repositorio.adicionar_vinculo(
            ClinicaUsuario(clinica_id=clinica.id, usuario_id=usuario.id, papel=papel)
        )
        # O mapper lê `vinculo.usuario`, e o relacionamento é `lazy="raise"`.
        vinculo.usuario = usuario
        return vinculo

    async def atualizar_vinculo(
        self,
        conta_id: int,
        public_id: uuid.UUID,
        usuario_public_id: uuid.UUID,
        papel: PapelUsuario,
        ativo: bool,
    ) -> ClinicaUsuario:
        _, vinculo = await self._resolver_vinculo(conta_id, public_id, usuario_public_id)

        vinculo.papel = papel
        vinculo.ativo = ativo
        return vinculo

    async def remover_vinculo(
        self, conta_id: int, public_id: uuid.UUID, usuario_public_id: uuid.UUID
    ) -> None:
        _, vinculo = await self._resolver_vinculo(conta_id, public_id, usuario_public_id)
        await self._repositorio.remover_vinculo(vinculo)

    async def _resolver_vinculo(
        self, conta_id: int, public_id: uuid.UUID, usuario_public_id: uuid.UUID
    ) -> tuple[Clinica, ClinicaUsuario]:
        clinica = await self.buscar(conta_id, public_id)
        usuario = await self._usuarios.buscar_por_public_id(conta_id, usuario_public_id)
        if usuario is None:
            raise RecursoNaoEncontradoError.de("Usuário", usuario_public_id)

        vinculo = await self._repositorio.buscar_vinculo(clinica.id, usuario.id)
        if vinculo is None:
            raise RecursoNaoEncontradoError("Este usuário não está vinculado a esta clínica.")

        vinculo.usuario = usuario
        return clinica, vinculo
