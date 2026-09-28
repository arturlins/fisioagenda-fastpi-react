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

## Backend

```bash
cd backend
cp .env.example .env      # BANCO_SENHA = APP_DB_PASSWORD do .env da raiz
uv sync
uv run python servidor.py
```

A API sobe em `http://127.0.0.1:8000`, com documentação interativa em `/docs`.

| Rota | Resposta |
|---|---|
| `GET /saude` | liveness — não toca em dependência nenhuma |
| `GET /saude/pronto` | readiness — verifica o banco; 503 quando indisponível |

Desenvolvimento com recarga automática: `uv run uvicorn app.main:app --reload`.

> **Por que existe o `servidor.py`.** No Windows o uvicorn escolhe o
> `ProactorEventLoop`, sobre o qual o psycopg assíncrono não funciona. O
> `servidor.py` cria o loop compatível antes de servir. Em Linux o
> comportamento não muda. O modo `--reload` também funciona, porque roda em
> subprocesso e nesse caminho o uvicorn já escolhe o loop certo.

Migrações do banco:

```bash
uv run alembic upgrade head      # aplica
uv run alembic current           # revisão atual
```

> Depois de `docker compose down -v`, reaplique as migrações: o volume foi embora junto.

### API

Rotas sob `/api/v1`. A única pública é `POST /auth/registro-conta`, que cria a conta e o
primeiro usuário — daí em diante, usuário é criado por quem já está dentro.

| Recurso | Verbos |
|---|---|
| `/usuarios` | POST, GET (paginado, com filtros), GET por id, PUT, DELETE (lógico) |
| `/clinicas` | POST, GET, GET por id, PUT, DELETE |
| `/clinicas/{id}/usuarios` | POST, GET, PUT, DELETE — vínculo com papel por clínica |
| `/auth/eu` | GET — quem sou e em quais clínicas atuo |

Três formas de exercitar, na ordem de menor atrito:

| Ferramenta | Arquivo |
|---|---|
| **Postman** | `backend/fisioagenda.postman_collection.json` — 40 requisições; o login grava o token sozinho e a pasta 1 demonstra o JWT |
| VS Code / JetBrains | `backend/exemplos.http` |
| Navegador | `/docs`, com login real via Authorization Code + PKCE |

**[`ROTEIRO.md`](ROTEIRO.md)** é o passo a passo completo: subir o ambiente, credenciais, o que
rodar e onde cada requisito da disciplina está no código.

### Dados de demonstração

```bash
uv run python -m scripts.semear             # conta, 2 clínicas, 4 usuários com vínculos
uv run python -m scripts.semear --recriar   # apaga a conta de exemplo antes
```

Passa pelos serviços da aplicação, não por `INSERT` direto: os usuários criados logam de verdade
no Keycloak. Um deles é administrador de uma clínica e usuário comum em outra — que é a forma
mais direta de ver que o papel é **por clínica**, não global.

A coleção do Postman é gerada, não editada à mão:

```bash
uv run python -m scripts.gerar_colecao_postman
```

### Testes e verificações

```bash
uv run ruff format . && uv run ruff check .
uv run mypy app servidor.py tests alembic/env.py
uv run pytest
```

Os testes rodam contra o PostgreSQL de verdade, no banco `fisioagenda_test`: o esquema depende
de enum nativo, `timestamptz` e constraint de exclusão, e testar em SQLite testaria outro
sistema. Cada teste roda dentro de uma transação revertida ao final, então a ordem não importa
e nada precisa ser truncado.

O Keycloak é dublê na maioria dos testes — o que se verifica ali é a nossa lógica. A integração
real tem suíte própria:

```bash
uv run pytest -m keycloak        # exige `docker compose up -d`
uv run pytest -m "not keycloak"  # ignora o IdP
```

## Recomeçando do zero

```bash
docker compose down -v    # apaga os volumes: banco e Keycloak voltam ao estado inicial
docker compose up -d
```

## Documentação

O esquema do banco, o plano de implementação e os registros de decisão arquitetural (ADR) ficam
em `.claude/`, fora do controle de versão.
