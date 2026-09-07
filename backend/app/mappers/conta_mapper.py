"""Mapper de conta: entidade ⇄ DTO.

Como em `usuario_mapper`, a conversão DTO → entidade acontece na camada web e
produz entidades **transientes**: o `conta_id` do dono só existe depois de a
conta ser persistida, e quem faz esse elo é o Service.
"""

from __future__ import annotations

from app.models.acesso import Usuario
from app.models.organizacao import Conta
from app.schemas.conta import ContaResponse, RegistroContaRequest, RegistroContaResponse
from app.schemas.usuario import UsuarioResponse


def para_conta(dto: RegistroContaRequest) -> Conta:
    return Conta(nome=dto.nome_conta, cnpj=dto.cnpj)


def para_dono(dto: RegistroContaRequest) -> Usuario:
    """O primeiro usuário da conta nasce dono e profissional.

    `dono_da_conta = True` só acontece aqui — nenhuma rota promove alguém a dono
    depois, porque isso daria a conta inteira a quem conseguisse chamá-la.
    """
    return Usuario(
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
