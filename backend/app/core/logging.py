"""Log estruturado com identificador de correlação.

Todo registro carrega o `id_correlacao` da requisição que o originou. É o que
permite ligar um 500 devolvido ao cliente à linha exata do log — sem expor
stack trace na resposta.

Nada de token, senha ou dado clínico entra em log. Quando for preciso registrar
um usuário, registre o `public_id`, nunca e-mail ou CPF.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any, Literal

_id_correlacao: ContextVar[str | None] = ContextVar("id_correlacao", default=None)

# Atributos que o logging põe em todo LogRecord; o que sobrar é campo extra do
# chamador e vai para o JSON.
_CAMPOS_PADRAO = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def definir_id_correlacao(valor: str) -> None:
    _id_correlacao.set(valor)


def obter_id_correlacao() -> str | None:
    return _id_correlacao.get()


class _FiltroCorrelacao(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.id_correlacao = _id_correlacao.get()
        return True


class _FormatadorJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        dados: dict[str, Any] = {
            "horario": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": record.getMessage(),
            "id_correlacao": getattr(record, "id_correlacao", None),
        }
        for chave, valor in record.__dict__.items():
            if chave not in _CAMPOS_PADRAO and chave != "id_correlacao":
                dados[chave] = valor
        if record.exc_info:
            dados["excecao"] = self.formatException(record.exc_info)
        return json.dumps(dados, ensure_ascii=False, default=str)


def configurar_logging(nivel: str = "INFO", formato: Literal["json", "texto"] = "json") -> None:
    """Reconfigura o logger raiz. Idempotente — chamada na criação da aplicação."""
    manipulador = logging.StreamHandler(sys.stdout)
    manipulador.addFilter(_FiltroCorrelacao())
    manipulador.setFormatter(
        _FormatadorJson()
        if formato == "json"
        else logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(id_correlacao)s] %(name)s: %(message)s"
        )
    )

    raiz = logging.getLogger()
    raiz.handlers.clear()
    raiz.addHandler(manipulador)
    raiz.setLevel(nivel)

    # O uvicorn instala handlers próprios; sem isso cada linha sairia duplicada,
    # uma no formato dele e outra no nosso.
    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(nome)
        logger.handlers.clear()
        logger.propagate = True
