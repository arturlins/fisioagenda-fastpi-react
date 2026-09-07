"""Fixtures compartilhadas.

Três decisões que valem explicar:

**Banco real, não SQLite.** O esquema depende de enum nativo, `timestamptz`,
`ARRAY` e constraint de exclusão com `btree_gist` — nada disso existe em SQLite.
Testar contra outro banco testaria outro sistema. Os testes rodam em
`fisioagenda_test`, criado pelo compose.

**Cada teste dentro de uma transação revertida.** A conexão abre uma transação
externa e a sessão entra nela com `join_transaction_mode="create_savepoint"`.
Assim o `commit()` que os serviços fazem de verdade vira commit de savepoint, e o
rollback ao fim do teste descarta tudo. Sem truncar tabela e sem ordem de teste
importando.

**Keycloak dublê por padrão.** Os testes de API exercitam a nossa lógica, não o
IdP. A integração real tem suíte própria, marcada `keycloak`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

# Antes de qualquer import da aplicação: a configuração é lida uma vez e cacheada.
os.environ["BANCO_NOME"] = "fisioagenda_test"

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import obter_configuracao
from app.core.plataforma import configurar_loop_de_eventos
from app.core.seguranca import TokenVerificado, UsuarioAutenticado
from app.db.session import obter_sessao
from app.dependencies import obter_keycloak_admin
from app.models.acesso import ClinicaUsuario, Usuario
from app.models.enums import PapelUsuario
from app.models.organizacao import Clinica, Conta

configurar_loop_de_eventos()

RAIZ = Path(__file__).resolve().parents[1]


# --- banco -------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def migrar_banco_de_teste() -> None:
    """Aplica as migrations uma vez por sessão.

    Em subprocesso porque o Alembic cria o próprio event loop, e criar um loop
    dentro de uma sessão de teste assíncrona é pedir conflito.
    """
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=RAIZ,
        env={**os.environ, "BANCO_NOME": "fisioagenda_test"},
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        pytest.fail(f"migrations falharam no banco de teste:\n{resultado.stderr}")


@pytest.fixture
async def sessao() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(obter_configuracao().banco_url, poolclass=None)
    async with engine.connect() as conexao:
        transacao = await conexao.begin()
        fabrica = async_sessionmaker(
            bind=conexao,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        async with fabrica() as sessao:
            yield sessao
        await transacao.rollback()
    await engine.dispose()


# --- Keycloak dublê ----------------------------------------------------------


class KeycloakFalso:
    """Dublê da Admin API. Guarda o que foi pedido, para os testes conferirem."""

    def __init__(self) -> None:
        self.usuarios: dict[uuid.UUID, dict[str, Any]] = {}
        self.emails: dict[str, uuid.UUID] = {}
        self.removidos: list[uuid.UUID] = []
        self.desabilitados: list[uuid.UUID] = []
        self.falhar_ao_criar = False

    async def criar_usuario(self, *, email: str, nome: str, senha: str) -> uuid.UUID:
        if self.falhar_ao_criar:
            from app.exceptions.domain import IntegracaoError

            raise IntegracaoError("Keycloak")
        if email.lower() in self.emails:
            from app.integrations.keycloak.admin import UsuarioJaExisteNoIdpError

            raise UsuarioJaExisteNoIdpError(email)
        keycloak_id = uuid.uuid4()
        self.usuarios[keycloak_id] = {"email": email, "nome": nome, "habilitado": True}
        self.emails[email.lower()] = keycloak_id
        return keycloak_id

    async def buscar_por_email(self, email: str) -> uuid.UUID | None:
        return self.emails.get(email.lower())

    async def atualizar_usuario(self, keycloak_id: uuid.UUID, *, email: str, nome: str) -> None:
        registro = self.usuarios[keycloak_id]
        self.emails.pop(registro["email"].lower(), None)
        registro.update(email=email, nome=nome)
        self.emails[email.lower()] = keycloak_id

    async def definir_habilitado(self, keycloak_id: uuid.UUID, *, habilitado: bool) -> None:
        self.usuarios[keycloak_id]["habilitado"] = habilitado
        if not habilitado:
            self.desabilitados.append(keycloak_id)

    async def remover_usuario(self, keycloak_id: uuid.UUID) -> None:
        registro = self.usuarios.pop(keycloak_id, None)
        if registro:
            self.emails.pop(registro["email"].lower(), None)
        self.removidos.append(keycloak_id)


@pytest.fixture
def keycloak() -> KeycloakFalso:
    return KeycloakFalso()


# --- dados ------------------------------------------------------------------


@pytest.fixture
async def conta(sessao: AsyncSession) -> Conta:
    registro = Conta(nome=f"Clínica Teste {uuid.uuid4().hex[:8]}")
    sessao.add(registro)
    await sessao.flush()
    return registro


@pytest.fixture
async def dono(sessao: AsyncSession, conta: Conta) -> Usuario:
    usuario = Usuario(
        conta_id=conta.id,
        keycloak_id=uuid.uuid4(),
        nome="Ana Ribeiro",
        email=f"ana-{uuid.uuid4().hex[:8]}@clinicateste.com.br",
        dono_da_conta=True,
    )
    sessao.add(usuario)
    await sessao.flush()
    return usuario


@pytest.fixture
async def usuario_comum(sessao: AsyncSession, conta: Conta) -> Usuario:
    usuario = Usuario(
        conta_id=conta.id,
        keycloak_id=uuid.uuid4(),
        nome="Bruno Terapeuta",
        email=f"bruno-{uuid.uuid4().hex[:8]}@clinicateste.com.br",
    )
    sessao.add(usuario)
    await sessao.flush()
    return usuario


@pytest.fixture
async def clinica(sessao: AsyncSession, conta: Conta) -> Clinica:
    registro = Clinica(conta_id=conta.id, nome=f"Unidade {uuid.uuid4().hex[:6]}")
    sessao.add(registro)
    await sessao.flush()
    return registro


def autenticado(usuario: Usuario, vinculos: tuple[ClinicaUsuario, ...] = ()) -> UsuarioAutenticado:
    return UsuarioAutenticado(
        usuario=usuario,
        token=TokenVerificado(
            sub=usuario.keycloak_id,
            email=usuario.email,
            nome_de_usuario=usuario.email,
            cliente_de_origem="fisioagenda-web",
            papeis_de_realm=frozenset({"fisio-usuario"}),
        ),
        vinculos=vinculos,
    )


# --- aplicação ---------------------------------------------------------------


@pytest.fixture
def app(sessao: AsyncSession, keycloak: KeycloakFalso) -> Iterator[FastAPI]:
    from app.main import criar_app

    aplicacao = criar_app()

    async def _sessao_de_teste() -> AsyncIterator[AsyncSession]:
        yield sessao

    aplicacao.dependency_overrides[obter_sessao] = _sessao_de_teste
    aplicacao.dependency_overrides[obter_keycloak_admin] = lambda: keycloak
    yield aplicacao
    aplicacao.dependency_overrides.clear()


@pytest.fixture
async def cliente(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente sem credencial — é com ele que se testa 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://teste",
    ) as cliente:
        yield cliente


@pytest.fixture
def como(app: FastAPI):  # type: ignore[no-untyped-def]
    """Injeta um usuário autenticado, sem passar por token nem pelo Keycloak.

    A verificação do token tem suíte própria (`test_seguranca.py`); aqui o que
    interessa é o comportamento das rotas para cada tipo de usuário.
    """
    from app.api.v1.deps import obter_usuario_atual

    def definir(usuario: Usuario, vinculos: tuple[ClinicaUsuario, ...] = ()) -> None:
        principal = autenticado(usuario, vinculos)
        app.dependency_overrides[obter_usuario_atual] = lambda: principal

    return definir


@pytest.fixture
def vinculo_admin(clinica: Clinica, usuario_comum: Usuario) -> ClinicaUsuario:
    return ClinicaUsuario(
        clinica_id=clinica.id,
        usuario_id=usuario_comum.id,
        papel=PapelUsuario.ADMINISTRADOR,
        ativo=True,
    )
