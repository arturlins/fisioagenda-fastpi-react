# Roteiro de avaliação — FisioAgenda

Guia para exercitar a API e localizar cada requisito no código. Leva cerca de dez minutos.

O sistema é um agendamento de fisioterapia multi-clínica, de uso interno. O paciente não acessa
o sistema — não existe credencial de paciente em lugar nenhum do modelo.

---

## 1. Subir o ambiente

Requisitos: Docker com Compose, [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env          # troque os valores; qualquer senha serve em desenvolvimento
docker compose up -d          # PostgreSQL 18 e Keycloak 26

cd backend
cp .env.example .env          # BANCO_SENHA e KEYCLOAK_CLIENT_SECRET = os mesmos do .env da raiz
uv sync
uv run alembic upgrade head   # cria as 18 tabelas, constraints e triggers
uv run python -m scripts.semear   # dados de demonstração
uv run python servidor.py     # API em http://127.0.0.1:8000
```

Confirme com `GET http://127.0.0.1:8000/saude/pronto` — ele reporta banco e Keycloak
separadamente e devolve 503 se algum estiver fora.

| Serviço | Endereço |
|---|---|
| API | `http://127.0.0.1:8000` — documentação interativa em `/docs` |
| PostgreSQL | `127.0.0.1:5433` |
| Keycloak | `http://127.0.0.1:8080` |

## 2. Credenciais criadas pelo seed

Senha de todos: `FisioAgenda#2026`

| E-mail | Papel |
|---|---|
| `ana@clinicamovimento.com.br` | dona da conta — acesso irrestrito a todas as clínicas |
| `bruno@clinicamovimento.com.br` | **administrador** da Unidade Centro · **comum** na Unidade Farol |
| `carla@clinicamovimento.com.br` | comum na Unidade Centro (profissional) |
| `diego@clinicamovimento.com.br` | comum na Unidade Centro (recepção, não atende) |

O Bruno existe para mostrar a decisão mais importante do modelo de acesso: **o papel é por
clínica, não global**. A mesma pessoa administra uma unidade e é usuária comum em outra.

---

## 3. Exercitar pelo Postman

Importe `backend/fisioagenda.postman_collection.json`.

1. Nas variáveis da coleção, preencha **`segredoTestes`** com o `KEYCLOAK_TESTES_CLIENT_SECRET`
   do `.env` da raiz.
2. Rode a pasta **1 · Autenticação JWT (Keycloak)**. O **Login** grava o access token e o
   refresh token; todas as demais requisições passam a ir com `Authorization: Bearer <jwt>`.
3. Rode as pastas na ordem, ou cada requisição individualmente. Todas têm asserções: o painel
   *Test Results* mostra o que foi verificado.

São 40 requisições e 83 asserções, cobrindo os quatro verbos e também os casos de erro. A
coleção pode ser executada quantas vezes quiser — nomes e e-mails são gerados a cada rodada.

### Demonstração do JWT (pasta 1)

| Requisição | O que mostra |
|---|---|
| Descoberta OIDC | Emissor (`iss`) e endereço das chaves públicas (`jwks_uri`) |
| JWKS | Chave pública RSA de assinatura; nenhum material privado exposto |
| **Login** | O Keycloak emite o JWT RS256. A aba **Visualize** da resposta mostra header, payload e assinatura decodificados, com o que a API confere em cada claim |
| `/auth/eu` com token | A API valida o JWT localmente e usa o `sub` para achar o usuário no banco |
| Sem token, malformado | 401 |
| Payload adulterado | E-mail trocado, papel `admin` adicionado, `exp` estendido, assinatura original mantida → 401 |
| Assinatura corrompida | 401 |
| `alg: none` | Token sem assinatura → 401 |
| Confusão HS256 | Assinado com HMAC usando a chave *pública* do realm → 401 |
| Refresh | Novo access token sem a senha, aceito pela API |

Toda recusa devolve a mesma resposta: o motivo fica só no log do servidor. O **logout** está na
pasta 5, no fim, para não derrubar a sessão das pastas intermediárias: ele encerra a sessão no
Keycloak e o refresh passa a falhar, mas o access token já emitido vale até o `exp` — a API
valida o JWT sem consultar o Keycloak, e a vida curta do token (15 min) limita essa janela.

Rodar tudo sem abrir o Postman:

```bash
cd backend
npx newman run fisioagenda.postman_collection.json --env-var "segredoTestes=<KEYCLOAK_TESTES_CLIENT_SECRET>"
```

Alternativa sem Postman: `backend/exemplos.http` (REST Client do VS Code ou cliente do
JetBrains), ou o `/docs`, que autentica de verdade via Authorization Code + PKCE.

---

## 4. Onde cada requisito está

Detalhamento e justificativa de cada decisão em `.claude/arquitetura.md`.

| Requisito | Onde ver | Como comprovar |
|---|---|---|
| **MVC** | `backend/app/api/v1/` → `app/services/` → `app/models/` | Controller não consulta banco; Service não importa FastAPI |
| **Repository** | `backend/app/repositories/` | Única camada que monta consulta. `grep -r "select(" app/ --include=*.py` só acusa `repositories/` |
| **DTO** | `backend/app/schemas/` | Request e Response separados; a entidade do ORM nunca é serializada |
| **Mapper** | `backend/app/mappers/` | Funções puras, chamadas pelo Controller |
| **GET/POST/PUT/DELETE** | `usuarios_controller.py`, `clinicas_controller.py` | Pastas 2, 3 e 4 da coleção |
| **ORM** | SQLAlchemy 2.0 em `app/models/` | SQL cru existe apenas nas migrations |
| **Controle de exceção** | `backend/app/exceptions/` | Erros de domínio + handlers globais; toda falha sai no mesmo formato |
| **Keycloak** | `app/integrations/keycloak/`, `app/core/seguranca.py` | Pasta 1 da coleção: JWT RS256 real, decodificado, e cinco formas de forjá-lo recusadas com 401 |

### Verificações rápidas

```bash
cd backend
uv run pytest        # 82 testes
uv run ruff check .  # lint, incluindo regras de segurança
uv run mypy app servidor.py tests alembic/env.py   # tipagem estrita
```

---

## 5. Sequência que demonstra o essencial

Se o tempo for curto, estas seis chamadas cobrem tudo:

1. **Login** → token do Keycloak; aba **Visualize** mostra o JWT decodificado. Em seguida,
   **Payload adulterado** → 401: editar o token invalida a assinatura.
2. **GET `/api/v1/auth/eu`** → identidade e vínculos com papel por clínica.
3. **GET `/api/v1/auth/eu` sem o cabeçalho** → 401 no formato padronizado de erro.
4. **POST `/api/v1/usuarios`** → 201 com `Location`. Repita a mesma chamada: 409 com
   `codigo: email_ja_cadastrado`.
5. **PUT `/api/v1/usuarios/{id}`** trocando o e-mail → o usuário passa a logar com o novo, porque
   a alteração é propagada ao Keycloak.
6. **DELETE `/api/v1/usuarios/{id}`** → 204. O `GET` seguinte devolve 404, mas a linha continua no
   banco: é exclusão lógica, porque histórico clínico e financeiro aponta para ela.

---

## 6. Comportamentos que podem surpreender

Nenhum é defeito; todos são decisão, com o motivo ao lado.

| Situação | Resposta | Por quê |
|---|---|---|
| Falha de validação do corpo | **422**, não 400 | Idiomático do FastAPI, e é o equivalente ao `MethodArgumentNotValidException` estabelecido no guia da disciplina |
| E-mail em `.local`, `localhost` ou `.test` | 422 | São domínios reservados, que não recebem e-mail |
| Senha com menos de 10 caracteres | 422 apontando o campo | Espelha a política do realm — melhor que um 502 vindo do Keycloak depois |
| Recurso de outra conta | **404**, não 403 | Confirmar que o recurso existe já seria informação demais |
| Erro 500 | Mensagem genérica + `id_correlacao` | Mensagem de exceção carrega caminho de arquivo e trecho de SQL. O identificador liga a resposta à linha exata do log |
| `DELETE` | 204 sem corpo | Resposta vazia é o esperado |

---

## 7. Estado do projeto

Esta entrega cobre a fundação e o módulo de acesso: contas, usuários, clínicas e vínculos, com
autenticação delegada ao Keycloak.

O banco, porém, já nasce com as **18 tabelas** do sistema completo — agenda, prontuário e
financeiro incluídos —, com os enums nativos, a constraint de exclusão que impede sobreposição
de horário do profissional e as triggers de capacidade e de recálculo financeiro. Os módulos
seguintes serão construídos sobre esse esquema, sem migração destrutiva.
