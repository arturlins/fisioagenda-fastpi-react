"""DTO de erro — o formato único de toda resposta de falha da API.

Equivale ao `ErrorResponseDto` do projeto da aula, com três acréscimos que a
prática pede: um `codigo` estável para o cliente programar em cima, o
`id_correlacao` para ligar a resposta ao log, e `detalhes` para erro de
validação campo a campo.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DetalheCampo(BaseModel):
    """Uma falha de validação, no campo onde ela ocorreu."""

    campo: str = Field(description="Caminho do campo, ex.: 'corpo.email'")
    mensagem: str


class ErroResposta(BaseModel):
    horario: datetime
    status: int = Field(description="Código HTTP")
    erro: str = Field(description="Nome do status HTTP, ex.: 'Not Found'")
    codigo: str = Field(
        description="Código estável do erro, ex.: 'recurso_nao_encontrado'. "
        "É o que o cliente deve inspecionar — a mensagem pode mudar."
    )
    mensagem: str
    caminho: str
    id_correlacao: str | None = Field(
        default=None, description="Mesmo identificador da linha de log correspondente"
    )
    detalhes: list[DetalheCampo] | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "horario": "2026-09-06T22:31:04.512Z",
                "status": 409,
                "erro": "Conflict",
                "codigo": "email_ja_cadastrado",
                "mensagem": "Já existe usuário com o e-mail informado nesta conta.",
                "caminho": "/api/v1/usuarios",
                "id_correlacao": "9380a0cc-0df5-4870-89f1-07ea57789f58",
                "detalhes": None,
            }
        }
    }
