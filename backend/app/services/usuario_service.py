"""Regras de negócio de usuário.

Concentra as decisões: e-mail duplicado, quem pode ser excluído, o que sincroniza
com o Keycloak. O controller não decide nada disso, e o repositório também não.

Recebe e devolve **entidades**, nunca DTOs: a conversão fica na camada web, como
no projeto de referência da aula. É o que mantém este módulo testável sem HTTP e
livre do contrato público da API.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import UsuarioAutenticado
from app.exceptions.domain import (
    EmailJaCadastradoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from app.integrations.keycloak.admin import KeycloakAdmin
from app.models.acesso import Usuario
from app.repositories.usuario_repository import UsuarioRepository

_logger = logging.getLogger("fisioagenda.usuarios")

TAMANHO_MAXIMO_DE_PAGINA = 100


class UsuarioService:
    def __init__(
        self,
        sessao: AsyncSession,
        repositorio: UsuarioRepository,
        keycloak: KeycloakAdmin,
    ) -> None:
        self._sessao = sessao
        self._repositorio = repositorio
        self._keycloak = keycloak

    # --- leitura -------------------------------------------------------------

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
        return await self._repositorio.listar(
            conta_id,
            pagina=pagina,
            tamanho=min(tamanho, TAMANHO_MAXIMO_DE_PAGINA),
            apenas_ativos=apenas_ativos,
            apenas_profissionais=apenas_profissionais,
            busca=busca,
        )

    async def buscar(self, conta_id: int, public_id: uuid.UUID) -> Usuario:
        usuario = await self._repositorio.buscar_por_public_id(conta_id, public_id)
        if usuario is None:
            raise RecursoNaoEncontradoError.de("Usuário", public_id)
        return usuario

    # --- escrita -------------------------------------------------------------

    async def criar(self, conta_id: int, novo: Usuario, senha: SecretStr) -> Usuario:
        """Cria no Keycloak e localmente, compensando se a gravação falhar.

        `senha` chega separada da entidade porque `usuarios` não tem campo de
        senha — a credencial é do Keycloak (ADR-001).

        A checagem de e-mail acontece antes de tocar o Keycloak: evita criar uma
        credencial que já se sabe que não vai ser usada.
        """
        if await self._repositorio.existe_email(conta_id, novo.email):
            raise EmailJaCadastradoError(novo.email)

        keycloak_id = await self._keycloak.criar_usuario(
            email=novo.email, nome=novo.nome, senha=senha.get_secret_value()
        )

        # Campos que o cliente não escolhe são atribuídos aqui, não no mapper.
        novo.conta_id = conta_id
        novo.keycloak_id = keycloak_id

        try:
            usuario = await self._repositorio.adicionar(novo)
            await self._sessao.commit()
        except Exception:
            await self._sessao.rollback()
            await self._compensar_criacao(keycloak_id)
            raise

        _logger.info("usuário criado", extra={"usuario": str(usuario.public_id)})
        return usuario

    async def atualizar(self, conta_id: int, public_id: uuid.UUID, dados: Usuario) -> Usuario:
        """`dados` é uma entidade transiente com os novos valores.

        O Service carrega a entidade persistida e copia os campos editáveis —
        mesmo desenho do `AccountServiceImpl.update` do projeto de referência.
        """
        usuario = await self.buscar(conta_id, public_id)

        email_mudou = dados.email.lower() != usuario.email.lower()
        nome_mudou = dados.nome != usuario.nome

        if email_mudou and await self._repositorio.existe_email(
            conta_id, dados.email, ignorando=usuario.id
        ):
            raise EmailJaCadastradoError(dados.email)

        self._copiar_campos_editaveis(de=dados, para=usuario)
        await self._repositorio.sincronizar(usuario)

        # O Keycloak é atualizado antes do commit: se ele recusar — e-mail já em
        # uso por outra conta, por exemplo — a transação local desfaz junto.
        if email_mudou or nome_mudou:
            await self._keycloak.atualizar_usuario(
                usuario.keycloak_id, email=usuario.email, nome=usuario.nome
            )

        try:
            await self._sessao.commit()
        except Exception:
            await self._sessao.rollback()
            if email_mudou or nome_mudou:
                _logger.critical(
                    "cadastro divergente: Keycloak atualizado e commit local falhou",
                    extra={"usuario": str(public_id)},
                )
            raise

        return usuario

    async def excluir(
        self, conta_id: int, public_id: uuid.UUID, *, ator: UsuarioAutenticado
    ) -> None:
        """Exclusão lógica: a linha permanece, o acesso acaba.

        `usuarios` é referenciado por agendamentos, evoluções e cobranças com
        `ON DELETE RESTRICT` ou `SET NULL` — apagar de verdade destruiria ou
        anonimizaria histórico clínico e financeiro.
        """
        usuario = await self.buscar(conta_id, public_id)

        if usuario.id == ator.usuario.id:
            raise RegraDeNegocioError("Você não pode excluir o próprio usuário.")
        if usuario.dono_da_conta:
            raise RegraDeNegocioError("O dono da conta não pode ser excluído.")

        usuario.excluido_em = datetime.now(UTC)
        usuario.ativo = False
        await self._repositorio.sincronizar(usuario)

        # Desabilitar no IdP encerra o acesso mesmo que o token atual ainda não
        # tenha expirado — sem isso, o excluído continuaria entrando por até 15
        # minutos.
        await self._keycloak.definir_habilitado(usuario.keycloak_id, habilitado=False)
        await self._sessao.commit()

        _logger.info(
            "usuário excluído",
            extra={"usuario": str(public_id), "por": str(ator.usuario.public_id)},
        )

    @staticmethod
    def _copiar_campos_editaveis(*, de: Usuario, para: Usuario) -> None:
        """`conta_id`, `keycloak_id` e `dono_da_conta` ficam de fora: nenhum é
        editável por requisição — quem se autopromovesse a dono levaria a conta."""
        para.nome = de.nome
        para.email = de.email
        para.telefone = de.telefone
        para.e_profissional = de.e_profissional
        para.registro_conselho = de.registro_conselho
        para.especialidade = de.especialidade
        para.cor_agenda = de.cor_agenda
        para.ativo = de.ativo

    async def _compensar_criacao(self, keycloak_id: uuid.UUID) -> None:
        try:
            await self._keycloak.remover_usuario(keycloak_id)
        except Exception:
            _logger.critical(
                "usuário órfão no Keycloak: criado, mas não gravado localmente",
                extra={"keycloak_id": str(keycloak_id)},
                exc_info=True,
            )
