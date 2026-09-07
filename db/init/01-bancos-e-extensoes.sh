#!/bin/bash
# Executado uma única vez, na primeira inicialização do volume do Postgres.
#
# Cria os bancos da aplicação, dos testes e do Keycloak, cada um com seu próprio
# role de login — nenhum deles superusuário. O Keycloak não compartilha credencial
# com a aplicação.
#
# É script e não .sql porque as senhas chegam por variável de ambiente e não devem
# ficar escritas no repositório.

set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE ROLE "${APP_DB_USER}" LOGIN PASSWORD '${APP_DB_PASSWORD}';
	CREATE ROLE "${KEYCLOAK_DB_USER}" LOGIN PASSWORD '${KEYCLOAK_DB_PASSWORD}';

	CREATE DATABASE fisioagenda_test OWNER "${APP_DB_USER}";
	CREATE DATABASE keycloak OWNER "${KEYCLOAK_DB_USER}";

	ALTER DATABASE fisioagenda OWNER TO "${APP_DB_USER}";
EOSQL

# pgcrypto  -> gen_random_uuid(), usado no default de todo public_id
# btree_gist -> constraint de exclusão contra sobreposição de agenda do profissional
for banco in fisioagenda fisioagenda_test; do
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$banco" <<-EOSQL
		CREATE EXTENSION IF NOT EXISTS pgcrypto;
		CREATE EXTENSION IF NOT EXISTS btree_gist;

		ALTER SCHEMA public OWNER TO "${APP_DB_USER}";
		REVOKE ALL ON SCHEMA public FROM PUBLIC;
		GRANT ALL ON SCHEMA public TO "${APP_DB_USER}";
	EOSQL
done

echo "[init] bancos fisioagenda, fisioagenda_test e keycloak prontos"
