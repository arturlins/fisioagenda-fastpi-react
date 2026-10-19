# syntax=docker/dockerfile:1

# --- dependências -------------------------------------------------------------
FROM python:3.13-slim-trixie AS construtor
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app
# Dependências antes do código: mudança de código não invalida a camada pesada.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
COPY . .

# --- execução -----------------------------------------------------------------
FROM python:3.13-slim-trixie

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY --from=construtor --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HTTP_HOST=0.0.0.0 \
    HTTP_PORTA=8000

WORKDIR /app
USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=3)"]

CMD ["python", "servidor.py"]
