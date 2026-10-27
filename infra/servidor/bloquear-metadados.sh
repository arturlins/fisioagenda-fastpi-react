#!/usr/bin/env bash
# Fecha o serviço de metadados da Hetzner (169.254.169.254) para tudo que não é
# root no host. Defesa em profundidade: o user_data já não leva segredo, mas um
# SSRF na API ou no Keycloak não deve nem enxergar o que o servidor sabe de si.
#
# Idempotente (iptables -C antes de -I): roda a cada boot, antes do Docker,
# pela unit fisioagenda-bloqueio-metadados.service.
set -euo pipefail

metadados=169.254.169.254/32

# Containers: o tráfego deles atravessa a FORWARD, que o Docker desvia para a
# DOCKER-USER — a chain que ele cria se faltar, mas nunca reescreve.
iptables -w -n -L DOCKER-USER >/dev/null 2>&1 || iptables -w -N DOCKER-USER
iptables -w -C DOCKER-USER -d "$metadados" -j DROP 2>/dev/null ||
  iptables -w -I DOCKER-USER 1 -d "$metadados" -j DROP

# Host: só root alcança — o cloud-init roda como root e consulta o metadata a
# cada boot; root já lê o .env de qualquer forma.
iptables -w -C OUTPUT -d "$metadados" -m owner ! --uid-owner 0 -j DROP 2>/dev/null ||
  iptables -w -I OUTPUT 1 -d "$metadados" -m owner ! --uid-owner 0 -j DROP

echo "bloqueio-metadados: regras aplicadas em DOCKER-USER e OUTPUT."
