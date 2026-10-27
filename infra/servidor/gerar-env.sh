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
