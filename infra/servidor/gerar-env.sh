#!/usr/bin/env bash
# Monta o .env da pilha de produção no primeiro boot do servidor.
#
# O user_data só leva valores não secretos (.env.base). As seis senhas nascem
# aqui, no próprio servidor: nunca passam pelo Terraform, pelo state nem pelo
# serviço de metadados. Idempotente — se o .env já existe, sai sem tocar nele
# (reboot, re-execução manual). Perder o servidor é perder as senhas, junto com
# o volume do banco que elas protegem.
#
# Uso: gerar-env.sh [diretorio]   (padrão: /opt/fisioagenda)
set -euo pipefail

diretorio="${1:-/opt/fisioagenda}"
base="$diretorio/.env.base"
destino="$diretorio/.env"
# Projeto "fisioagenda-prod" (name: do compose.prod.yaml) + volume postgres-dados.
volume_banco="fisioagenda-prod_postgres-dados"

segredos=(
  POSTGRES_SUPERUSER_PASSWORD
  APP_DB_PASSWORD
  KEYCLOAK_DB_PASSWORD
  KEYCLOAK_ADMIN_PASSWORD
  KEYCLOAK_BACKEND_CLIENT_SECRET
  SEMEAR_SENHA
)

falhar() {
  echo "gerar-env: $*" >&2
  exit 1
}

if [[ -e "$destino" ]]; then
  echo "gerar-env: $destino já existe; nada a fazer."
  exit 0
fi

[[ -r "$base" ]] || falhar "$base ausente."

# .env apagado com o banco ainda de pé: senhas novas não abririam o Postgres nem
# o Keycloak, já inicializados com as antigas. Recusa em vez de quebrar a pilha.
# No primeiro boot o Docker nem está instalado: sem docker, não há volume.
if command -v docker >/dev/null 2>&1; then
  docker info >/dev/null 2>&1 ||
    falhar "Docker instalado mas inacessível: não dá para confirmar que $volume_banco não existe."
  if docker volume inspect "$volume_banco" >/dev/null 2>&1; then
    falhar "$destino ausente, mas o volume $volume_banco existe: senhas novas não abririam o banco já inicializado. Restaure o .env original ou, para recomeçar do zero, 'docker compose --project-directory $diretorio down -v' antes."
  fi
fi
for chave in "${segredos[@]}"; do
  if grep -q "^${chave}=" "$base"; then
    falhar "$base não pode definir $chave: segredo nasce aqui."
  fi
done

# 32 caracteres de [A-Za-z0-9] por escolha uniforme sobre o CSPRNG do kernel
# (secrets usa os.urandom): ~190 bits. O python3 é o mesmo de que o cloud-init
# depende, então está sempre presente. Sem pipeline com /dev/urandom, sem a
# armadilha do SIGPIPE sob pipefail e sem viés de módulo.
gerar_senha() {
  python3 -I -c '
import secrets, string
alfabeto = string.ascii_letters + string.digits
print("".join(secrets.choice(alfabeto) for _ in range(32)))
'
}

umask 077
temporario="$(mktemp "$diretorio/.env.XXXXXXXX")"
trap 'rm -f "$temporario"' EXIT

{
  # awk 1 garante a quebra de linha final mesmo se o .env.base vier sem ela.
  awk 1 "$base"
  for chave in "${segredos[@]}"; do
    senha="$(gerar_senha)"
    [[ "$senha" =~ ^[A-Za-z0-9]{32}$ ]] || falhar "senha gerada fora do formato."
    printf '%s=%s\n' "$chave" "$senha"
  done
} >"$temporario"

chmod 0600 "$temporario"
sync "$temporario"

# link(2) publica o arquivo completo de uma vez e falha se o destino já existir:
# atômico como um mv, mas nunca sobrescreve um .env que apareceu no meio do caminho.
ln "$temporario" "$destino" || falhar "$destino apareceu durante a geração; mantido como está."
echo "gerar-env: $destino gerado."
