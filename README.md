# FisioAgenda

Sistema interno de agendamento de fisioterapia: multi-clínica, com ficha de evolução e controle
de mensalidades. Uso exclusivamente interno — o paciente não acessa o sistema.

- `backend/` — API em FastAPI (SQLAlchemy 2.0 async, Alembic, Pydantic v2)
- `frontend/` — SPA em React 19 + Vite, com login real no Keycloak (Authorization Code + PKCE)
- `keycloak/` — realm versionado e tema de login próprio
- `compose.yaml` — PostgreSQL e Keycloak para desenvolvimento
- `infra/` — pilha de produção, ensaio local, smoke test e Terraform na Hetzner
- `.github/workflows/ci.yaml` — testes, lint, Terraform e imagens no GHCR

## Requisitos

Docker (com Compose v2+), [uv](https://docs.astral.sh/uv/) e [Bun](https://bun.sh) 1.3+ para o
frontend. Para o deploy, também Terraform 1.9+ e uma conta na Hetzner Cloud.

## Subindo a infraestrutura

```bash
cp .env.example .env      # e troque todos os valores
docker compose up -d
```

Isso levanta dois serviços:

| Serviço | Endereço | Observação |
|---|---|---|
| PostgreSQL 18 | `127.0.0.1:5433` | 5433 para não colidir com uma instalação nativa na 5432 |
| Keycloak 26.8 | `127.0.0.1:8080` | console administrativo em `/admin` (só em desenvolvimento) |

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
| `fisioagenda-testes` | confidencial | Direct Access Grant nos testes — **só em desenvolvimento**, removido pelo Terraform |

As URLs do app e da API no realm são placeholders (`${FISIOAGENDA_APP_URL}`,
`${FISIOAGENDA_API_URL}`): o mesmo arquivo serve ao desenvolvimento e à produção. O realm também
ativa o tema de login `fisioagenda`, em `keycloak/themes/`.

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

## Frontend

Com a infraestrutura e a API de pé (seções acima):

```bash
cd frontend
bun install
bun run dev
```

Abra **`http://localhost:5173`** — `localhost`, não `127.0.0.1`: a origem liberada no realm e no
CORS da API é essa, e o Keycloak recusa o redirect de qualquer outra. Os endereços vêm de
`public/config.json`, lido em tempo de execução e validado na carga (inválido → tela
"Configuração inválida").

Entre com qualquer usuário do seed (`uv run python -m scripts.semear`; e-mails e senha no
[`ROTEIRO.md`](ROTEIRO.md)). O Bruno é o melhor para ver o papel por clínica: administrador na
Unidade Centro, comum na Unidade Farol.

O que o SPA faz: página de entrada, login pelo Keycloak com Authorization Code + PKCE (S256),
painel que lê `/api/v1/auth/eu` e logout. Os tokens ficam **só em memória** — ao recarregar a
página, a sessão SSO do Keycloak devolve o usuário sem pedir senha.

```bash
bun run check        # Biome (lint + format)
bun run typecheck    # tsc --noEmit
bun run test         # Vitest + Testing Library
bun run build
bun run e2e          # Playwright: login real, recarga e logout
```

O E2E sobe o Vite sozinho e usa a pilha local. Contra outro ambiente, defina
`E2E_BASE_URL` (e `E2E_SENHA`, se a senha do seed for outra).

## Imagens e CI

São três imagens, cada uma com seu `Dockerfile`:

| Imagem | Contexto | Conteúdo |
|---|---|---|
| `fisioagenda-api` | `backend/` | API, usuário sem privilégio; também roda as migrations e o seed |
| `fisioagenda-web` | `frontend/` | Caddy + SPA compilado; TLS automático e proxy para API e Keycloak |
| `fisioagenda-keycloak` | `keycloak/` | Keycloak 26.8.1 com build otimizado e o tema embutido |

`.github/workflows/ci.yaml` roda em todo push e pull request:

| Job | O que verifica |
|---|---|
| `backend` | ruff, mypy e pytest contra o Postgres do `compose.yaml` |
| `frontend` | Biome, `tsc`, Vitest e build |
| `terraform` | `fmt -check`, `validate`, `terraform test` (provider simulado) e `tflint` |
| `imagens` | depois dos três: build de cada imagem e Trivy — vulnerabilidade **CRITICAL com correção disponível** reprova |

A publicação no GHCR acontece **só em push no `main`**, com SBOM e provenance. A tag é o **SHA
completo do commit** — nunca `latest` —, então o que roda no servidor é exatamente um commit
identificável. Toda action do workflow é fixada pelo SHA do commit, não por tag mutável.

## Deploy

A infraestrutura inteira nasce de um `terraform apply` e é recriada do zero por
`destroy` → `apply`, sem passo manual entre um e outro: IP, firewall, chave SSH e um servidor
cujo cloud-init instala o Docker e sobe a pilha (`infra/compose.prod.yaml`). Migrations e seed
rodam sozinhos, em serviços de execução única, antes da API. Os endereços derivam do IP —
`app.`, `api.` e `auth.<ip-com-traços>.sslip.io` —, com certificado Let's Encrypt emitido pelo
Caddy.

### Pré-requisitos

1. Na Hetzner Cloud, um **projeto próprio** para o FisioAgenda e um API token *Read & Write*
   **criado dentro dele**. O token só enxerga o projeto em que nasceu: nenhum `destroy` alcança
   recurso de outro projeto.
2. O token na variável de ambiente — nunca em arquivo:

   ```bash
   export HCLOUD_TOKEN=...          # PowerShell: $env:HCLOUD_TOKEN="..."
   ```

3. Uma chave SSH (padrão `~/.ssh/id_ed25519.pub`; senão, `ssh-keygen -t ed25519`).
4. Imagens publicadas pelo CI para o commit a implantar, e os pacotes do GHCR públicos.

### Variáveis

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # ignorado pelo Git
```

| Variável | Valor |
|---|---|
| `versao_imagens` | SHA completo do commit do `main` (`git rev-parse origin/main`) |
| `ssh_permitido_cidr` | seu IP público com `/32` — o único que alcança a porta 22 |
| `acme_email` | contato do Let's Encrypt |
| `tipo_servidor`, `localizacao` | opcionais: `cpx22`/`nbg1` por padrão; alternativas `cpx32`/`hel1` se faltar estoque |

Os segredos (banco, Keycloak, senha do seed) **não** são variáveis nem passam pelo Terraform:
nascem no próprio servidor, no primeiro boot. O `user_data` leva só valores públicos (domínio,
imagens, nomes de usuário) e um script que gera as seis senhas localmente e grava o `.env` com
`0600`. Assim nenhuma senha fica no state, nem no serviço de metadados da Hetzner — que qualquer
processo da máquina consegue ler. Esse serviço, além disso, é bloqueado a cada boot, antes do
Docker, para containers e usuários sem privilégio. Perder o servidor é perder as senhas, junto
com o volume que elas protegem: o próximo `apply` gera outras.

### Subir, verificar, derrubar

```bash
terraform init
terraform plan -out plano.tfplan
terraform apply plano.tfplan
terraform output                                   # URLs, IP e comandos SSH
```

A senha dos usuários do seed fica só no servidor. `comando_senha_demonstracao` é o comando
pronto para lê-la por SSH — o mesmo texto funciona no sh e no PowerShell:

```bash
terraform output -raw comando_senha_demonstracao  # ssh deploy@<ip> "sudo sed -n 's/^SEMEAR_SENHA=//p' /opt/fisioagenda/.env"
```

Cole o comando impresso para ver a senha, ou capture direto numa variável:

```bash
SENHA_DEMO="$(eval "$(terraform output -raw comando_senha_demonstracao)")"    # sh
$env:SENHA_DEMO = Invoke-Expression (terraform output -raw comando_senha_demonstracao)  # PowerShell
```

O cloud-init leva alguns minutos depois do fim do `apply`. O smoke test (só biblioteca padrão)
espera a pilha e confere, de fora, nove pontos — da SPA ao console administrativo fechado —,
com a verificação de TLS sempre ligada:

```bash
cd ../..
python -I infra/smoke_test.py "$(terraform -chdir=infra/terraform output -raw dominio_base)" --aguardar 900
```

E o E2E contra o ambiente implantado:

```bash
cd frontend
E2E_BASE_URL="$(terraform -chdir=../infra/terraform output -raw url_app)" \
E2E_SENHA="$(eval "$(terraform -chdir=../infra/terraform output -raw comando_senha_demonstracao)")" bun run e2e
```

Para encerrar: `terraform -chdir=infra/terraform destroy`. O próximo `apply` cria um IP novo — e
tudo funciona nele sem tocar em nada.

> Qualquer mudança em `compose.prod.yaml`, no realm ou no template do cloud-init **recria o
> servidor**, e o volume do banco vai junto. Nesta etapa o dado é de demonstração, recriado pelo
> seed.

### Ensaio local

A pilha de produção roda na própria máquina antes de gastar um `apply`, com as imagens
construídas daqui e certificado da CA interna do Caddy:

```bash
cp infra/.env.ensaio.example infra/.env
docker compose -f infra/compose.prod.yaml -f infra/compose.ensaio.yaml up -d --build
docker compose -f infra/compose.prod.yaml -f infra/compose.ensaio.yaml cp \
  web:/data/caddy/pki/authorities/local/root.crt "${TMPDIR:-/tmp}/caddy-local.crt"
python -I infra/smoke_test.py 127-0-0-1.sslip.io --ca "${TMPDIR:-/tmp}/caddy-local.crt" --aguardar 180
```

O smoke confia na CA local, e só nela — a verificação de TLS nunca é desligada. Para o E2E:
`E2E_BASE_URL=https://app.127-0-0-1.sslip.io E2E_IGNORAR_TLS=1 E2E_SENHA=<SEMEAR_SENHA do infra/.env> bun run e2e`.
Derrubar: `docker compose -f infra/compose.prod.yaml -f infra/compose.ensaio.yaml down -v`.

Exige as portas 80 e 443 livres. Se o roteador bloquear DNS que responde `127.0.0.1`, acrescente
ao arquivo `hosts`:
`127.0.0.1 app.127-0-0-1.sslip.io api.127-0-0-1.sslip.io auth.127-0-0-1.sslip.io`.
A única diferença para produção: o ensaio importa o realm do repositório inteiro, com o client
de testes, cujo segredo ele libera na allowlist do Keycloak.

### Diagnóstico no servidor

```bash
ssh deploy@<ip>                                     # terraform output ssh
sudo cloud-init status --wait                       # bootstrap terminou? (--long para detalhes)
sudo docker compose --project-directory /opt/fisioagenda ps -a
sudo docker compose --project-directory /opt/fisioagenda logs <serviço>
```

`migracao` e `semeadura` devem estar `Exited (0)`; os demais, `healthy` ou `running`. Root e
senha estão desligados no SSH; só o usuário `deploy`, por chave.

## Recomeçando do zero

```bash
docker compose down -v    # apaga os volumes: banco e Keycloak voltam ao estado inicial
docker compose up -d
```

## Documentação

O esquema do banco, o plano de implementação, a arquitetura da implantação e os registros de
decisão arquitetural (ADR) ficam em `.claude/`, fora do controle de versão.
