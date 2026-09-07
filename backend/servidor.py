"""Ponto de entrada do servidor.

    uv run python servidor.py

Existe porque o uvicorn escolhe o `ProactorEventLoop` no Windows, e o psycopg
assíncrono não funciona sobre ele. Aqui o loop é criado explicitamente antes de
o servidor começar a servir.

Em Linux nada muda: `fabrica_de_loop()` devolve `None` e o uvicorn segue com a
escolha dele — inclusive uvloop, quando disponível.

Para desenvolvimento com recarga automática, `uv run uvicorn app.main:app
--reload` também funciona no Windows: o modo reload roda o servidor em
subprocesso, e nesse caminho o próprio uvicorn já escolhe o loop compatível.
"""

from __future__ import annotations

import asyncio

import uvicorn

from app.core.config import obter_configuracao
from app.core.plataforma import fabrica_de_loop


def main() -> None:
    config = obter_configuracao()
    servidor = uvicorn.Server(
        uvicorn.Config(
            "app.main:app",
            host=config.http_host,
            port=config.http_porta,
            # A aplicação já configura o logging; deixar o uvicorn reconfigurar
            # devolveria as linhas ao formato dele, sem id de correlação.
            log_config=None,
            access_log=False,
            server_header=False,
            date_header=False,
        )
    )
    asyncio.run(servidor.serve(), loop_factory=fabrica_de_loop())


if __name__ == "__main__":
    main()
