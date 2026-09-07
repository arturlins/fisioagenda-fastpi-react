"""Mapper de conta: entidade ⇄ DTO."""

from __future__ import annotations

import uuid

from app.models.acesso import Usuario
from app.models.organizacao import Conta
from app.schemas.conta import ContaResponse, RegistroContaRequest, RegistroContaResponse
from app.schemas.usuario import UsuarioResponse


def de_registro_para_conta(dto: RegistroContaRequest) -> Conta:
    return Conta(nome=dto.nome_conta, cnpj=dto.cnpj)


def de_registro_para_dono(
    dto: RegistroContaRequest, *, conta_id: int, keycloak_id: uuid.UUID
) -> Usuario:
    """O primeiro usuário da conta nasce dono e profissional.

    `dono_da_conta = True` só acontece aqui — nenhuma rota promove alguém a dono
    depois, porque isso daria a conta inteira a quem conseguisse chamá-la.
    """
    return Usuario(
        conta_id=conta_id,
        keycloak_id=keycloak_id,
        nome=dto.nome_responsavel,
        email=str(dto.email),
        e_profissional=True,
        dono_da_conta=True,
    )


def para_resposta(conta: Conta) -> ContaResponse:
    return ContaResponse.model_validate(conta)


def para_resposta_de_registro(conta: Conta, dono: Usuario) -> RegistroContaResponse:
    return RegistroContaResponse(
        conta=para_resposta(conta),
        usuario=UsuarioResponse.model_validate(dono),
    )
