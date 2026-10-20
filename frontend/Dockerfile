# syntax=docker/dockerfile:1
FROM oven/bun:1.3.10-slim AS construtor
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
# O config.json de desenvolvimento não vai para a imagem: em produção quem o
# responde é o Caddy.
RUN bun run build && rm -f dist/config.json

FROM caddy:2.11.7-alpine
COPY Caddyfile /etc/caddy/Caddyfile
RUN DOMINIO_BASE=exemplo.sslip.io TLS_MODO=internal \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
COPY --from=construtor /app/dist /srv
