"""Ajustes dependentes de sistema operacional.

O psycopg em modo assíncrono não funciona sobre o `ProactorEventLoop`, que é o
padrão do asyncio no Windows desde o Python 3.8: a conexão falha com
`InterfaceError` já no primeiro `connect`.

Há dois pontos de controle, porque nem todo mundo cria o loop do mesmo jeito:

- Onde *nós* chamamos `asyncio.run` (Alembic, pytest), a política de loop
  resolve — é o que `configurar_loop_de_eventos` faz.
- O uvicorn 0.36+ não usa a política: passa um `loop_factory` para o
  `asyncio.run`, e no Windows esse factory devolve `ProactorEventLoop`
  explicitamente. Ali a única saída é criar o loop nós mesmos, com
  `fabrica_de_loop` — ver `servidor.py`.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import Callable

# As ramificações por plataforma comparam `sys.platform` diretamente, e não via
# constante: é a única forma que o mypy reconhece para estreitar por plataforma.
# Com uma constante, o checker rodando no Linux (CI) não encontra
# `WindowsSelectorEventLoopPolicy`.


def configurar_loop_de_eventos() -> None:
    """Política de loop compatível com o psycopg. Fora do Windows, não faz nada."""
    if sys.platform == "win32":
        politica = asyncio.WindowsSelectorEventLoopPolicy
        if not isinstance(asyncio.get_event_loop_policy(), politica):
            # `set_event_loop_policy` caminha para a depreciação (3.14+), mas é o
            # que o pytest-asyncio e o asyncio.run do Alembic consultam hoje.
            asyncio.set_event_loop_policy(politica())


def fabrica_de_loop() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """Factory de loop para passar ao `asyncio.run`.

    `None` fora do Windows: deixa quem chama manter o padrão (inclusive uvloop).
    """
    if sys.platform == "win32":
        return lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    else:
        return None
