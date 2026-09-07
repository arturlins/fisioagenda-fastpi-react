"""Popula o banco com dados de demonstração.

    uv run python -m scripts.semear
    uv run python -m scripts.semear --recriar   # apaga a conta de exemplo antes

Passa pelos **serviços da aplicação**, não por INSERT direto: as mesmas regras de
negócio, a mesma criação de credencial no Keycloak. Se o seed roda, o caminho de
escrita da API está de pé — e os usuários criados conseguem logar de verdade.

Os vínculos são desenhados para mostrar a decisão mais interessante do modelo:
o papel é **por clínica**. Bruno administra a Unidade Centro e é usuário comum na
Unidade Farol.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass

import httpx
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Configuracao, obter_configuracao
from app.core.plataforma import configurar_loop_de_eventos
from app.db.session import obter_fabrica_sessao
from app.integrations.keycloak.admin import KeycloakAdmin
from app.models.acesso import ClinicaUsuario, Usuario
from app.models.enums import PapelUsuario
from app.models.organizacao import Clinica, Conta
from app.repositories.clinica_repository import ClinicaRepository
from app.repositories.conta_repository import ContaRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.services.clinica_service import ClinicaService
from app.services.conta_service import ContaService
from app.services.usuario_service import UsuarioService

# Senha única para todos, para facilitar a demonstração. Atende à política do
# realm: 10+ caracteres, diferente do nome de usuário e do e-mail.
SENHA = "FisioAgenda#2026"
DOMINIO = "clinicamovimento.com.br"
NOME_DA_CONTA = "Clínica Movimento"


@dataclass(frozen=True)
class PessoaDeExemplo:
    nome: str
    usuario: str
    e_profissional: bool
    registro_conselho: str | None = None
    especialidade: str | None = None
    cor_agenda: str | None = None

    @property
    def email(self) -> str:
        return f"{self.usuario}@{DOMINIO}"


DONA = PessoaDeExemplo(
    nome="Ana Ribeiro Souza",
    usuario="ana",
    e_profissional=True,
    registro_conselho="CREFITO-3 10001-F",
    especialidade="Fisioterapia Ortopédica",
    cor_agenda="#8B5CF6",
)

EQUIPE = (
    PessoaDeExemplo(
        nome="Bruno Carvalho Lima",
        usuario="bruno",
        e_profissional=True,
        registro_conselho="CREFITO-3 12345-F",
        especialidade="Ortopedia e Traumatologia",
        cor_agenda="#3B82F6",
    ),
    PessoaDeExemplo(
        nome="Carla Mendes Rocha",
        usuario="carla",
        e_profissional=True,
        registro_conselho="CREFITO-3 67890-F",
        especialidade="Pilates e Neurofuncional",
        cor_agenda="#10B981",
    ),
    # Recepção: não recebe agendamentos. É o que a flag `e_profissional` separa.
    PessoaDeExemplo(nome="Diego Alves Pinto", usuario="diego", e_profissional=False),
)

CLINICAS = (
    ("Unidade Centro", "Rua do Comércio, 120", "Maceió", "AL", "8233330001"),
    ("Unidade Farol", "Av. Fernandes Lima, 900", "Maceió", "AL", "8233330002"),
)


async def _apagar_conta_anterior(sessao: AsyncSession, keycloak: KeycloakAdmin) -> bool:
    """Remove a conta de exemplo e as credenciais dela no Keycloak.

    O `ON DELETE CASCADE` leva clínicas, usuários e vínculos junto; o Keycloak
    precisa ser limpo à parte, senão o e-mail continua ocupado no IdP e a próxima
    semeadura falha com 409.
    """
    conta = await sessao.scalar(select(Conta).where(Conta.nome == NOME_DA_CONTA))
    if conta is None:
        return False

    emails = list(
        (await sessao.execute(select(Usuario.email).where(Usuario.conta_id == conta.id))).scalars()
    )
    for email in emails:
        keycloak_id = await keycloak.buscar_por_email(email)
        if keycloak_id is not None:
            await keycloak.remover_usuario(keycloak_id)

    await sessao.execute(delete(Conta).where(Conta.id == conta.id))
    await sessao.commit()
    return True


async def _semear(config: Configuracao, recriar: bool) -> None:
    async with httpx.AsyncClient(timeout=config.keycloak_timeout_segundos) as http:
        keycloak = KeycloakAdmin(config, http)

        async with obter_fabrica_sessao()() as sessao:
            if recriar and await _apagar_conta_anterior(sessao, keycloak):
                print("conta de exemplo anterior removida")

            if await sessao.scalar(select(Conta).where(Conta.nome == NOME_DA_CONTA)):
                print(
                    f'A conta "{NOME_DA_CONTA}" já existe. Rode com --recriar para começar do zero.'
                )
                return

            contas = ContaRepository(sessao)
            usuarios = UsuarioRepository(sessao)
            clinicas = ClinicaRepository(sessao)

            servico_conta = ContaService(sessao, contas, usuarios, keycloak)
            servico_usuario = UsuarioService(sessao, usuarios, keycloak)
            servico_clinica = ClinicaService(clinicas, usuarios)

            # --- conta e dona ---------------------------------------------
            conta, dona = await servico_conta.registrar(
                Conta(nome=NOME_DA_CONTA, cnpj="12345678000199"),
                Usuario(
                    nome=DONA.nome,
                    email=DONA.email,
                    e_profissional=True,
                    registro_conselho=DONA.registro_conselho,
                    especialidade=DONA.especialidade,
                    cor_agenda=DONA.cor_agenda,
                    dono_da_conta=True,
                ),
                SecretStr(SENHA),
            )
            print(f"conta criada: {conta.nome}  ({conta.public_id})")

            # --- clínicas -------------------------------------------------
            criadas: list[Clinica] = []
            for nome, endereco, cidade, uf, telefone in CLINICAS:
                criadas.append(
                    await servico_clinica.criar(
                        conta.id,
                        Clinica(
                            nome=nome,
                            endereco=endereco,
                            cidade=cidade,
                            uf=uf,
                            telefone=telefone,
                            fuso_horario="America/Maceio",
                        ),
                    )
                )
            await sessao.commit()
            for clinica in criadas:
                print(f"clínica criada: {clinica.nome}  ({clinica.public_id})")

            # --- equipe ---------------------------------------------------
            equipe: dict[str, Usuario] = {}
            for pessoa in EQUIPE:
                equipe[pessoa.usuario] = await servico_usuario.criar(
                    conta.id,
                    Usuario(
                        nome=pessoa.nome,
                        email=pessoa.email,
                        e_profissional=pessoa.e_profissional,
                        registro_conselho=pessoa.registro_conselho,
                        especialidade=pessoa.especialidade,
                        cor_agenda=pessoa.cor_agenda,
                    ),
                    SecretStr(SENHA),
                )
                print(f"usuário criado: {pessoa.nome}")

            # --- vínculos: o papel é POR CLÍNICA --------------------------
            centro, farol = criadas
            vinculos = (
                (equipe["bruno"], centro, PapelUsuario.ADMINISTRADOR),
                (equipe["bruno"], farol, PapelUsuario.COMUM),
                (equipe["carla"], centro, PapelUsuario.COMUM),
                (equipe["diego"], centro, PapelUsuario.COMUM),
            )
            for usuario, clinica, papel in vinculos:
                sessao.add(
                    ClinicaUsuario(clinica_id=clinica.id, usuario_id=usuario.id, papel=papel)
                )
            await sessao.commit()

            _resumo(conta, dona, criadas, equipe)


def _resumo(
    conta: Conta, dona: Usuario, clinicas: list[Clinica], equipe: dict[str, Usuario]
) -> None:
    print()
    print("=" * 72)
    print(f"  Conta: {conta.nome}")
    print(f"  Senha de todos: {SENHA}")
    print("=" * 72)
    print()
    print("  ACESSO                                    PAPEL")
    print(f"  {dona.email:<40}  dona da conta (todas as clínicas)")
    print(f"  {equipe['bruno'].email:<40}  admin da Centro · comum na Farol")
    print(f"  {equipe['carla'].email:<40}  comum na Centro (profissional)")
    print(f"  {equipe['diego'].email:<40}  comum na Centro (recepção)")
    print()
    print("  CLÍNICAS")
    for clinica in clinicas:
        print(f"  {clinica.nome:<40}  {clinica.public_id}")
    print()
    print("  Bruno tem papel diferente em cada clínica — é o que demonstra que o")
    print("  privilégio é por unidade, e não global.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Popula o banco com dados de demonstração.")
    parser.add_argument(
        "--recriar",
        action="store_true",
        help="apaga a conta de exemplo (e as credenciais dela no Keycloak) antes de semear",
    )
    argumentos = parser.parse_args()

    configurar_loop_de_eventos()
    config = obter_configuracao()
    print(f"banco: {config.banco_host}:{config.banco_porta}/{config.banco_nome}")
    print(f"keycloak: {config.keycloak_emissor}")
    print()

    try:
        asyncio.run(_semear(config, argumentos.recriar))
    except Exception as erro:
        print(f"\nfalhou: {erro}", file=sys.stderr)
        raise SystemExit(1) from erro


if __name__ == "__main__":
    main()
