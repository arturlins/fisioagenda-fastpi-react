"""Gera a coleção do Postman a partir desta descrição.

    uv run python -m scripts.gerar_colecao_postman

A coleção é artefato gerado, não arquivo editado à mão: JSON do Postman é
verboso e fácil de quebrar sem perceber. Alterou rota ou caso de erro? Ajuste
aqui e regenere.

Verificada com `npx newman run fisioagenda.postman_collection.json`.
"""

import json
from pathlib import Path
from typing import Any

SAIDA = Path(__file__).resolve().parents[1] / "fisioagenda.postman_collection.json"


def teste(nome: str, *linhas: str) -> dict[str, Any]:
    return {
        "listen": "test",
        "script": {"type": "text/javascript", "exec": list(linhas)},
    }


def antes(*linhas: str) -> dict[str, Any]:
    """Pre-request: gera valores únicos, para a coleção poder rodar mais de uma vez."""
    return {"listen": "prerequest", "script": {"type": "text/javascript", "exec": list(linhas)}}


def espera(codigo: int, extra: list[str] | None = None) -> dict[str, Any]:
    linhas = [
        f'pm.test("status {codigo}", function () {{',
        f"    pm.response.to.have.status({codigo});",
        "});",
    ]
    linhas += extra or []
    return teste("t", *linhas)


def req(
    nome: str,
    metodo: str,
    caminho: str,
    *,
    corpo: dict[str, Any] | None = None,
    eventos: list[dict[str, Any]] | None = None,
    sem_auth: bool = False,
    descricao: str = "",
    query: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    partes = [p for p in caminho.strip("/").split("/") if p]
    url: dict[str, Any] = {
        "raw": "{{api}}/" + caminho.strip("/"),
        "host": ["{{api}}"],
        "path": partes,
    }
    if query:
        url["query"] = query
        url["raw"] += "?" + "&".join(f"{q['key']}={q['value']}" for q in query)

    requisicao: dict[str, Any] = {
        "method": metodo,
        "header": [],
        "url": url,
        "description": descricao,
    }
    if corpo is not None:
        requisicao["header"].append({"key": "Content-Type", "value": "application/json"})
        requisicao["body"] = {
            "mode": "raw",
            "raw": json.dumps(corpo, indent=2, ensure_ascii=False),
            "options": {"raw": {"language": "json"}},
        }
    if sem_auth:
        requisicao["auth"] = {"type": "noauth"}

    return {"name": nome, "request": requisicao, "event": eventos or [], "response": []}


# --- pastas ------------------------------------------------------------------

saude = {
    "name": "0 · Saúde",
    "description": "Liveness não toca em dependência; readiness verifica banco e Keycloak.",
    "item": [
        req("GET /saude — liveness", "GET", "saude", sem_auth=True, eventos=[espera(200)]),
        req(
            "GET /saude/pronto — readiness",
            "GET",
            "saude/pronto",
            sem_auth=True,
            descricao="Reporta banco e Keycloak separadamente. 503 quando algum está fora.",
            eventos=[espera(200)],
        ),
    ],
}

autenticacao = {
    "name": "1 · Autenticação",
    "description": (
        "Rode o **Login** primeiro: ele grava o token nas variáveis da coleção e todas as "
        "demais requisições passam a ir autenticadas.\n\n"
        "Se o banco foi semeado (`uv run python -m scripts.semear`), o login já funciona com "
        "as credenciais padrão. Senão, rode antes o **Registro de conta**."
    ),
    "item": [
        {
            "name": "Login (obtém o token)",
            "request": {
                "auth": {"type": "noauth"},
                "method": "POST",
                "header": [],
                "body": {
                    "mode": "urlencoded",
                    "urlencoded": [
                        {"key": "grant_type", "value": "password"},
                        {"key": "client_id", "value": "{{clientTestes}}"},
                        {"key": "client_secret", "value": "{{segredoTestes}}"},
                        {"key": "username", "value": "{{email}}"},
                        {"key": "password", "value": "{{senha}}"},
                    ],
                },
                "url": {
                    "raw": "{{keycloak}}/realms/{{realm}}/protocol/openid-connect/token",
                    "host": ["{{keycloak}}"],
                    "path": ["realms", "{{realm}}", "protocol", "openid-connect", "token"],
                },
                "description": (
                    "Direct Access Grant no client `fisioagenda-testes`, que existe apenas no "
                    "realm de desenvolvimento. Em produção o fluxo é Authorization Code + PKCE "
                    "pelo frontend.\n\n"
                    "Preencha `segredoTestes` com o `KEYCLOAK_TESTES_CLIENT_SECRET` do `.env` "
                    "da raiz do projeto."
                ),
            },
            "event": [
                teste(
                    "t",
                    'pm.test("login bem-sucedido", function () {',
                    "    pm.response.to.have.status(200);",
                    "});",
                    "const corpo = pm.response.json();",
                    "if (corpo.access_token) {",
                    '    pm.collectionVariables.set("token", corpo.access_token);',
                    '    console.log("token gravado; as demais requisições já vão autenticadas");',
                    "}",
                ),
            ],
            "response": [],
        },
        req(
            "GET /auth/eu — perfil e vínculos",
            "GET",
            "api/v1/auth/eu",
            descricao="Quem sou e em quais clínicas atuo, com o papel em cada uma.",
            eventos=[
                espera(
                    200,
                    [
                        'pm.test("traz usuário e vínculos", function () {',
                        "    const c = pm.response.json();",
                        "    pm.expect(c).to.have.property('usuario');",
                        "    pm.expect(c).to.have.property('vinculos');",
                        "});",
                    ],
                )
            ],
        ),
        req(
            "GET /auth/eu sem token → 401",
            "GET",
            "api/v1/auth/eu",
            sem_auth=True,
            descricao="Erro no formato padronizado, com `codigo`, `caminho` e `id_correlacao`.",
            eventos=[
                espera(
                    401,
                    [
                        'pm.test("codigo nao_autenticado", function () {',
                        "    pm.expect(pm.response.json().codigo).to.eql('nao_autenticado');",
                        "});",
                    ],
                )
            ],
        ),
        req(
            "POST /auth/registro-conta — única rota pública",
            "POST",
            "api/v1/auth/registro-conta",
            sem_auth=True,
            corpo={
                "nome_conta": "{{nomeContaNova}}",
                "cnpj": "98765432000188",
                "nome_responsavel": "Paula Souza Andrade",
                "email": "{{emailContaNova}}",
                "senha": "OutraSenhaForte#2026",
            },
            descricao=(
                "Cria a conta, registra a credencial no Keycloak e grava o primeiro usuário, "
                "que nasce dono. Daqui em diante, usuário é criado por quem já está dentro.\n\n"
                "O nome e o e-mail da conta são gerados a cada execução, então esta "
                "requisição pode ser repetida à vontade."
            ),
            eventos=[
                antes(
                    "const s = Date.now();",
                    'pm.collectionVariables.set("nomeContaNova", "Clinica Nova " + s);',
                    'pm.collectionVariables.set("emailContaNova", "paula." + s + "@clinicanova.com.br");',
                ),
                espera(201),
            ],
        ),
    ],
}

usuarios = {
    "name": "2 · Usuários (os quatro verbos)",
    "item": [
        req(
            "POST /usuarios → 201 + Location",
            "POST",
            "api/v1/usuarios",
            corpo={
                "nome": "Eduardo Nunes Reis",
                "email": "{{emailUsuario}}",
                "senha": "SenhaDoEduardo#2026",
                "telefone": "82999990010",
                "e_profissional": True,
                "registro_conselho": "CREFITO-3 24680-F",
                "especialidade": "Reabilitação Esportiva",
                "cor_agenda": "#F59E0B",
            },
            descricao="Cria no Keycloak e localmente. O `public_id` é guardado para os próximos passos.",
            eventos=[
                antes(
                    "const s = Date.now();",
                    'pm.collectionVariables.set("emailUsuario", "eduardo." + s + "@clinicamovimento.com.br");',
                    'pm.collectionVariables.set("emailUsuarioNovo", "eduardo.reis." + s + "@clinicamovimento.com.br");',
                ),
                espera(
                    201,
                    [
                        'pm.test("devolve Location", function () {',
                        "    pm.expect(pm.response.headers.get('Location')).to.be.a('string');",
                        "});",
                        'pm.test("nao expoe id interno nem credencial", function () {',
                        "    const c = pm.response.json();",
                        "    pm.expect(c).to.not.have.property('id');",
                        "    pm.expect(c).to.not.have.property('keycloak_id');",
                        "    pm.expect(c).to.not.have.property('senha');",
                        "});",
                        "const corpo = pm.response.json();",
                        "if (corpo.public_id) {",
                        '    pm.collectionVariables.set("usuarioId", corpo.public_id);',
                        "}",
                    ],
                ),
            ],
        ),
        req(
            "POST com e-mail repetido → 409",
            "POST",
            "api/v1/usuarios",
            corpo={
                "nome": "Outra Pessoa",
                "email": "{{emailUsuario}}",
                "senha": "SenhaQualquer#2026",
            },
            eventos=[
                espera(
                    409,
                    [
                        'pm.test("codigo email_ja_cadastrado", function () {',
                        "    pm.expect(pm.response.json().codigo).to.eql('email_ja_cadastrado');",
                        "});",
                    ],
                )
            ],
        ),
        req(
            "POST com senha curta → 422 apontando o campo",
            "POST",
            "api/v1/usuarios",
            corpo={
                "nome": "Pessoa Teste",
                "email": "curta@clinicamovimento.com.br",
                "senha": "123",
            },
            descricao=(
                "A política do realm exige 10 caracteres. Validar aqui devolve 422 com o campo "
                "apontado, em vez de um 502 vindo do Keycloak."
            ),
            eventos=[
                espera(
                    422,
                    [
                        'pm.test("aponta o campo senha", function () {',
                        "    const campos = pm.response.json().detalhes.map(d => d.campo);",
                        "    pm.expect(campos.join(',')).to.include('senha');",
                        "});",
                    ],
                )
            ],
        ),
        req(
            "GET /usuarios — lista paginada",
            "GET",
            "api/v1/usuarios",
            query=[{"key": "pagina", "value": "1"}, {"key": "tamanho", "value": "20"}],
            eventos=[
                espera(
                    200,
                    [
                        'pm.test("pagina com total", function () {',
                        "    const c = pm.response.json();",
                        "    pm.expect(c).to.have.property('total');",
                        "    pm.expect(c.itens).to.be.an('array');",
                        "});",
                    ],
                )
            ],
        ),
        req(
            "GET /usuarios — com filtros",
            "GET",
            "api/v1/usuarios",
            query=[
                {"key": "e_profissional", "value": "true"},
                {"key": "ativo", "value": "true"},
                {"key": "busca", "value": "Bruno"},
            ],
            descricao="`busca` casa nome ou e-mail. `%` e `_` são escapados: um curinga digitado não devolve a conta inteira.",
            eventos=[espera(200)],
        ),
        req(
            "GET /usuarios/{id}",
            "GET",
            "api/v1/usuarios/{{usuarioId}}",
            eventos=[espera(200)],
        ),
        req(
            "GET /usuarios/{id} inexistente → 404",
            "GET",
            "api/v1/usuarios/00000000-0000-0000-0000-000000000000",
            eventos=[
                espera(
                    404,
                    [
                        'pm.test("codigo recurso_nao_encontrado", function () {',
                        "    pm.expect(pm.response.json().codigo).to.eql('recurso_nao_encontrado');",
                        "});",
                    ],
                )
            ],
        ),
        req(
            "PUT /usuarios/{id}",
            "PUT",
            "api/v1/usuarios/{{usuarioId}}",
            corpo={
                "nome": "Eduardo Nunes Reis",
                "email": "{{emailUsuarioNovo}}",
                "telefone": "82999990011",
                "e_profissional": True,
                "especialidade": "Reabilitação Esportiva e Pós-operatório",
                "ativo": True,
            },
            descricao=(
                "Substitui os campos editáveis. Trocar o e-mail sincroniza com o Keycloak — o "
                "usuário passa a logar com o novo.\n\n"
                "`dono_da_conta` não está no DTO: quem se autopromovesse levaria a conta inteira."
            ),
            eventos=[
                espera(
                    200,
                    [
                        'pm.test("e-mail atualizado", function () {',
                        '    pm.expect(pm.response.json().email).to.eql(pm.collectionVariables.get("emailUsuarioNovo"));',
                        "});",
                    ],
                )
            ],
        ),
        req(
            "DELETE /usuarios/{id} → 204 (exclusão lógica)",
            "DELETE",
            "api/v1/usuarios/{{usuarioId}}",
            descricao=(
                "A linha permanece no banco — histórico clínico e financeiro aponta para ela — "
                "mas o usuário some da API e é desabilitado no Keycloak."
            ),
            eventos=[espera(204)],
        ),
        req(
            "GET do excluído → 404",
            "GET",
            "api/v1/usuarios/{{usuarioId}}",
            eventos=[espera(404)],
        ),
    ],
}

clinicas = {
    "name": "3 · Clínicas",
    "item": [
        req(
            "POST /clinicas → 201 + Location",
            "POST",
            "api/v1/clinicas",
            corpo={
                "nome": "{{nomeClinica}}",
                "fuso_horario": "America/Maceio",
                "telefone": "8233330003",
                "endereco": "Rua Epaminondas Gracindo, 45",
                "cidade": "Maceió",
                "uf": "AL",
            },
            eventos=[
                antes(
                    'pm.collectionVariables.set("nomeClinica", "Unidade Jatiuca " + Date.now());',
                ),
                espera(
                    201,
                    [
                        "const corpo = pm.response.json();",
                        "if (corpo.public_id) {",
                        '    pm.collectionVariables.set("clinicaId", corpo.public_id);',
                        "}",
                    ],
                ),
            ],
        ),
        req(
            "POST com fuso inexistente → 422",
            "POST",
            "api/v1/clinicas",
            corpo={"nome": "Unidade Inválida", "fuso_horario": "Marte/Olimpo"},
            descricao=(
                "O fuso converte o horário da grade semanal em instante absoluto na "
                "materialização da agenda. Um valor inválido só apareceria como atendimento na "
                "hora errada, muito depois."
            ),
            eventos=[espera(422)],
        ),
        req(
            "POST com nome repetido → 409",
            "POST",
            "api/v1/clinicas",
            corpo={"nome": "{{nomeClinica}}", "fuso_horario": "America/Maceio"},
            eventos=[espera(409)],
        ),
        req("GET /clinicas", "GET", "api/v1/clinicas", eventos=[espera(200)]),
        req("GET /clinicas/{id}", "GET", "api/v1/clinicas/{{clinicaId}}", eventos=[espera(200)]),
        req(
            "PUT /clinicas/{id}",
            "PUT",
            "api/v1/clinicas/{{clinicaId}}",
            corpo={
                "nome": "{{nomeClinica}}",
                "fuso_horario": "America/Sao_Paulo",
                "telefone": "8233330004",
                "cidade": "Maceió",
                "uf": "AL",
                "ativa": True,
            },
            eventos=[espera(200)],
        ),
    ],
}

vinculos = {
    "name": "4 · Vínculos (papel por clínica)",
    "description": (
        "O papel é **por clínica**, não global: a mesma pessoa administra uma unidade e é "
        "usuária comum em outra. No banco semeado, Bruno demonstra exatamente isso."
    ),
    "item": [
        req(
            "Cria um usuário para vincular",
            "POST",
            "api/v1/usuarios",
            corpo={
                "nome": "Fernanda Lopes Dias",
                "email": "{{emailVinculo}}",
                "senha": "SenhaDaFernanda#2026",
                "e_profissional": True,
            },
            descricao="Deixa a pasta autossuficiente: dá para rodá-la inteira no Runner.",
            eventos=[
                antes(
                    'pm.collectionVariables.set("emailVinculo", "fernanda." + Date.now() + "@clinicamovimento.com.br");',
                ),
                espera(
                    201,
                    [
                        "const corpo = pm.response.json();",
                        "if (corpo.public_id) {",
                        '    pm.collectionVariables.set("usuarioVinculo", corpo.public_id);',
                        "}",
                    ],
                ),
            ],
        ),
        req(
            "POST — vincula usuário com papel",
            "POST",
            "api/v1/clinicas/{{clinicaId}}/usuarios",
            corpo={"usuario_public_id": "{{usuarioVinculo}}", "papel": "administrador"},
            eventos=[espera(201)],
        ),
        req(
            "POST repetido → 409",
            "POST",
            "api/v1/clinicas/{{clinicaId}}/usuarios",
            corpo={"usuario_public_id": "{{usuarioVinculo}}", "papel": "comum"},
            eventos=[
                espera(
                    409,
                    [
                        'pm.test("codigo vinculo_ja_existe", function () {',
                        "    pm.expect(pm.response.json().codigo).to.eql('vinculo_ja_existe');",
                        "});",
                    ],
                )
            ],
        ),
        req(
            "GET — quem atua na clínica",
            "GET",
            "api/v1/clinicas/{{clinicaId}}/usuarios",
            eventos=[espera(200)],
        ),
        req(
            "PUT — altera o papel",
            "PUT",
            "api/v1/clinicas/{{clinicaId}}/usuarios/{{usuarioVinculo}}",
            corpo={"papel": "comum", "ativo": True},
            eventos=[espera(200)],
        ),
        req(
            "DELETE — remove o vínculo",
            "DELETE",
            "api/v1/clinicas/{{clinicaId}}/usuarios/{{usuarioVinculo}}",
            eventos=[espera(204)],
        ),
        req(
            "DELETE /clinicas/{id} → 204",
            "DELETE",
            "api/v1/clinicas/{{clinicaId}}",
            descricao=(
                "Só remove clínica sem vínculos: as chaves apontando para `clinicas` são "
                "`ON DELETE CASCADE`, e apagar uma unidade com agenda levaria os agendamentos "
                "junto, em silêncio. Com vínculo, devolve 422."
            ),
            eventos=[espera(204)],
        ),
    ],
}

colecao: dict[str, Any] = {
    "info": {
        "name": "FisioAgenda — API",
        "description": (
            "# FisioAgenda\n\n"
            "API de agendamento de fisioterapia. Multi-clínica, uso interno, autenticação "
            "delegada ao Keycloak.\n\n"
            "## Antes de começar\n\n"
            "1. Na raiz do projeto: `docker compose up -d`\n"
            "2. Em `backend/`: `uv run alembic upgrade head`\n"
            "3. Dados de demonstração: `uv run python -m scripts.semear`\n"
            "4. Suba a API: `uv run python servidor.py`\n"
            "5. Preencha a variável **segredoTestes** desta coleção com o "
            "`KEYCLOAK_TESTES_CLIENT_SECRET` do `.env` da raiz\n"
            "6. Rode **1 · Autenticação → Login**. O token é gravado automaticamente e as "
            "demais requisições já vão autenticadas.\n\n"
            "## Ordem sugerida\n\n"
            "As pastas estão numeradas. Cada uma pode ser executada inteira pelo *Runner*; as "
            "requisições encadeiam `public_id` entre si por variáveis de coleção.\n\n"
            "## Detalhes que evitam surpresa\n\n"
            "- Falha de validação devolve **422**, não 400 — é o idiomático do FastAPI, "
            "equivalente ao `MethodArgumentNotValidException` do Spring.\n"
            "- E-mail em domínio reservado (`.local`, `localhost`, `.test`) é recusado: são "
            "domínios que não recebem e-mail.\n"
            "- Senha exige no mínimo 10 caracteres, espelhando a política do realm.\n"
            "- Recurso de outra conta responde **404**, não 403: confirmar que existe já seria "
            "informação demais.\n"
            "- `DELETE` devolve 204 sem corpo — resposta vazia é o esperado."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {
        "type": "bearer",
        "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}],
    },
    "item": [saude, autenticacao, usuarios, clinicas, vinculos],
    "variable": [
        {"key": "api", "value": "http://127.0.0.1:8000", "type": "string"},
        {"key": "keycloak", "value": "http://127.0.0.1:8080", "type": "string"},
        {"key": "realm", "value": "fisioagenda", "type": "string"},
        {"key": "clientTestes", "value": "fisioagenda-testes", "type": "string"},
        {
            "key": "segredoTestes",
            "value": "",
            "type": "string",
            "description": "KEYCLOAK_TESTES_CLIENT_SECRET do .env da raiz",
        },
        {"key": "email", "value": "ana@clinicamovimento.com.br", "type": "string"},
        {"key": "senha", "value": "FisioAgenda#2026", "type": "string"},
        {"key": "token", "value": "", "type": "string"},
        {"key": "usuarioId", "value": "", "type": "string"},
        {"key": "clinicaId", "value": "", "type": "string"},
        {"key": "usuarioVinculo", "value": "", "type": "string"},
        {"key": "emailUsuario", "value": "", "type": "string"},
        {"key": "emailUsuarioNovo", "value": "", "type": "string"},
        {"key": "emailVinculo", "value": "", "type": "string"},
        {"key": "nomeClinica", "value": "", "type": "string"},
        {"key": "nomeContaNova", "value": "", "type": "string"},
        {"key": "emailContaNova", "value": "", "type": "string"},
    ],
}


def main() -> None:
    SAIDA.write_text(json.dumps(colecao, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Relê o que foi escrito: JSON inválido precisa falhar aqui, e não no import
    # do Postman na frente de quem está avaliando.
    with SAIDA.open(encoding="utf-8") as arquivo:
        json.load(arquivo)

    pastas: list[dict[str, Any]] = colecao["item"]
    total = sum(len(pasta["item"]) for pasta in pastas)
    print(f"coleção gerada: {SAIDA}")
    print(f"{len(pastas)} pastas, {total} requisições")


if __name__ == "__main__":
    main()
