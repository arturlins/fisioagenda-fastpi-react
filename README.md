# FisioAgenda

Sistema interno de agendamento de fisioterapia: multi-clínica, com ficha de evolução e controle
de mensalidades. Uso exclusivamente interno — o paciente não acessa o sistema.

- `backend/` — API em FastAPI (SQLAlchemy 2.0 async, Alembic, Pydantic v2)
- `frontend/` — aplicação React (fase posterior)
- `compose.yaml` — PostgreSQL e Keycloak para desenvolvimento

## Requisitos

Docker (com Compose v2+), [uv](https://docs.astral.sh/uv/) e Node 20+ para o frontend.

## Subindo a infraestrutura

```bash
cp .env.example .env      # e troque todos os valores
docker compose up -d
```

Isso levanta dois serviços:

| Serviço | Endereço | Observação |
|---|---|---|
| PostgreSQL 18 | `127.0.0.1:5433` | 5433 para não colidir com uma instalação nativa na 5432 |
| Keycloak 26 | `127.0.0.1:8080` | console administrativo em `/admin` |

Ambos ficam presos a `127.0.0.1` — nada é exposto na rede.

Na primeira subida, `db/init/` cria três bancos, cada um com seu role de login (nenhum
superusuário), e habilita as extensões `pgcrypto` e `btree_gist`:

| Banco | Uso |
|---|---|
| `fisioagenda` | aplicação |
| `fisioagenda_test` | suíte de testes |
| `keycloak` | persistência do próprio Keycloak |

Acompanhe até os dois ficarem saudáveis:

```bash
docker compose ps
```

## Keycloak

O realm `fisioagenda` é **importado de `keycloak/realm-fisioagenda.json`** na subida, com três
clients:

| Client | Tipo | Uso |
|---|---|---|
| `fisioagenda-web` | público | frontend React — Authorization Code + PKCE (S256) |
| `fisioagenda-backend` | confidencial | service account da API para a Admin API do Keycloak |
| `fisioagenda-testes` | confidencial | Direct Access Grant nos testes — **só no realm de desenvolvimento** |

> **O realm é código.** Toda mudança de client, papel ou política feita pelo console
> administrativo precisa voltar para o JSON e ser commitada. Configuração clicada não sobrevive
> a um `docker compose down -v`, nem à próxima pessoa que clonar o repositório.

Para conferir que o service account do backend está de pé:

```bash
curl -s -X POST http://127.0.0.1:8080/realms/fisioagenda/protocol/openid-connect/token \
  -d grant_type=client_credentials \
  -d client_id=fisioagenda-backend \
  -d client_secret="$KEYCLOAK_BACKEND_CLIENT_SECRET"
```

## Recomeçando do zero

```bash
docker compose down -v    # apaga os volumes: banco e Keycloak voltam ao estado inicial
docker compose up -d
```

## Documentação

O esquema do banco, o plano de implementação e os registros de decisão arquitetural (ADR) ficam
em `.claude/`, fora do controle de versão.
