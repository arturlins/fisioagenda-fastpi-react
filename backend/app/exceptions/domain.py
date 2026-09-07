"""Exceções de domínio.

A camada de serviço levanta estas — nunca `HTTPException`. Quem traduz erro de
negócio em código HTTP é a fronteira (`handlers.py`), não a regra: um serviço que
importa FastAPI deixa de ser testável fora dele e amarra o domínio ao framework.

Cada exceção carrega o status e um `codigo` estável. O cliente programa em cima
do código; a mensagem é para humanos e pode mudar.
"""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID


class DominioError(Exception):
    """Raiz da hierarquia. Tudo que a aplicação levanta conscientemente."""

    status_http: ClassVar[int] = 500
    codigo: ClassVar[str] = "erro_interno"

    def __init__(self, mensagem: str, *, detalhes: dict[str, Any] | None = None) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or {}


# --- 404 ---------------------------------------------------------------------


class RecursoNaoEncontradoError(DominioError):
    status_http = 404
    codigo = "recurso_nao_encontrado"

    @classmethod
    def de(cls, recurso: str, public_id: UUID | str) -> RecursoNaoEncontradoError:
        return cls(f"{recurso} não encontrado: {public_id}")


# --- 409 ---------------------------------------------------------------------


class ConflitoDeEstadoError(DominioError):
    """O pedido é válido, mas colide com o estado atual."""

    status_http = 409
    codigo = "conflito"


class EmailJaCadastradoError(ConflitoDeEstadoError):
    codigo = "email_ja_cadastrado"

    def __init__(self, email: str) -> None:
        # O e-mail volta na mensagem de propósito: quem chama esta rota já é um
        # usuário autenticado da própria conta, administrando os próprios dados.
        super().__init__(f"Já existe usuário com o e-mail {email} nesta conta.")


class VinculoJaExisteError(ConflitoDeEstadoError):
    codigo = "vinculo_ja_existe"

    def __init__(self) -> None:
        super().__init__("Este usuário já está vinculado a esta clínica.")


# --- 422 ---------------------------------------------------------------------


class RegraDeNegocioError(DominioError):
    """Sintaticamente válido, mas proibido pelas regras do domínio."""

    status_http = 422
    codigo = "regra_de_negocio"


# --- 401 / 403 ---------------------------------------------------------------


class NaoAutenticadoError(DominioError):
    status_http = 401
    codigo = "nao_autenticado"

    def __init__(self, mensagem: str = "Credencial ausente ou inválida.") -> None:
        # Mensagem deliberadamente única para token ausente, expirado, com
        # assinatura inválida ou de usuário inexistente: distinguir esses casos
        # entrega informação a quem está sondando.
        super().__init__(mensagem)


class AcessoNegadoError(DominioError):
    status_http = 403
    codigo = "acesso_negado"

    def __init__(self, mensagem: str = "Você não tem permissão para esta operação.") -> None:
        super().__init__(mensagem)


# --- 502 ---------------------------------------------------------------------


class IntegracaoError(DominioError):
    """Dependência externa falhou — hoje, o Keycloak.

    É 502 e não 500: o problema não está nesta aplicação, e a distinção importa
    para quem opera e para a política de retentativa do cliente.
    """

    status_http = 502
    codigo = "integracao_indisponivel"

    def __init__(self, servico: str, mensagem: str | None = None) -> None:
        super().__init__(mensagem or f"Serviço indisponível no momento: {servico}.")
        self.servico = servico
