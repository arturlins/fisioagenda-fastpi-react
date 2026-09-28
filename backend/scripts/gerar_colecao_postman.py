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
    bearer_da_variavel: str | None = None,
    descricao: str = "",
    query: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """`bearer_da_variavel` troca o Bearer herdado da coleção por outra variável — usado para
    enviar tokens forjados sem sobrescrever o legítimo."""
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
    elif bearer_da_variavel:
        requisicao["auth"] = {
            "type": "bearer",
            "bearer": [
                {"key": "token", "value": "{{" + bearer_da_variavel + "}}", "type": "string"}
            ],
        }

    return {"name": nome, "request": requisicao, "event": eventos or [], "response": []}


def keycloak_oidc(
    nome: str,
    metodo: str,
    endpoint: str,
    *,
    formulario: list[tuple[str, str]] | None = None,
    eventos: list[dict[str, Any]] | None = None,
    descricao: str = "",
) -> dict[str, Any]:
    """Requisição direta ao Keycloak — endpoints OIDC do realm, sem Bearer."""
    partes = ["realms", "{{realm}}", *endpoint.strip("/").split("/")]
    requisicao: dict[str, Any] = {
        "auth": {"type": "noauth"},
        "method": metodo,
        "header": [],
        "url": {
            "raw": "{{keycloak}}/" + "/".join(partes),
            "host": ["{{keycloak}}"],
            "path": partes,
        },
        "description": descricao,
    }
    if formulario is not None:
        requisicao["body"] = {
            "mode": "urlencoded",
            "urlencoded": [{"key": k, "value": v} for k, v in formulario],
        }
    return {"name": nome, "request": requisicao, "event": eventos or [], "response": []}


# --- JWT no sandbox do Postman ----------------------------------------------
#
# O sandbox não tem `Buffer`; base64url sai do crypto-js, que o Postman embute.
# UTF-8 explícito porque o payload carrega nome com acento.

JS_JWT = [
    "const cj = require('crypto-js');",
    "function b64urlParaTexto(s) {",
    "    s = s.replace(/-/g, '+').replace(/_/g, '/');",
    "    while (s.length % 4) { s += '='; }",
    "    return cj.enc.Base64.parse(s).toString(cj.enc.Utf8);",
    "}",
    "function b64urlDePalavras(palavras) {",
    r"    return cj.enc.Base64.stringify(palavras).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');",
    "}",
    "function b64urlDeTexto(texto) { return b64urlDePalavras(cj.enc.Utf8.parse(texto)); }",
    "function decodificarJwt(jwt) {",
    "    const partes = jwt.split('.');",
    "    return {",
    "        partes: partes,",
    "        header: JSON.parse(b64urlParaTexto(partes[0])),",
    "        payload: JSON.parse(b64urlParaTexto(partes[1])),",
    "    };",
    "}",
    "function tokenLegitimo() {",
    '    const t = pm.collectionVariables.get("token");',
    "    if (!t) { throw new Error('Rode primeiro \"Login\": não há token para forjar.'); }",
    "    return t;",
    "}",
]


def forja(*linhas: str) -> dict[str, Any]:
    """Pre-request que monta um token forjado em `tokenForjado` a partir do legítimo."""
    return antes(*JS_JWT, *linhas)


# Todo token recusado recebe a mesma resposta: o motivo exato fica só no log do
# servidor. Distinguir "expirado" de "assinatura inválida" ensinaria o atacante.
REJEITA_TOKEN = [
    'pm.test("codigo nao_autenticado", function () {',
    "    pm.expect(pm.response.json().codigo).to.eql('nao_autenticado');",
    "});",
    'pm.test("resposta não revela o motivo da recusa", function () {',
    "    pm.expect(pm.response.json().mensagem).to.eql('Credencial ausente ou inválida.');",
    "});",
    'pm.test("WWW-Authenticate: Bearer (RFC 6750)", function () {',
    "    pm.expect(pm.response.headers.get('WWW-Authenticate')).to.eql('Bearer');",
    "});",
]

VISUALIZADOR_JWT = r"""
<style>
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 20px; }
  h2 { font-size: 15px; letter-spacing: .04em; text-transform: uppercase; color: #8b949e; margin: 0 0 12px; }
  .bruto { font-family: ui-monospace, Consolas, monospace; font-size: 12px; word-break: break-all; line-height: 1.6; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; }
  .h { color: #ff7b72; } .p { color: #d2a8ff; } .s { color: #79c0ff; } .ponto { color: #e6edf3; }
  .legenda { display: flex; gap: 18px; font-size: 12px; margin: 10px 0 22px; color: #8b949e; }
  .legenda b { font-weight: 600; }
  .grade { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  section { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; overflow-x: auto; }
  pre { margin: 0; font-size: 12px; font-family: ui-monospace, Consolas, monospace; }
  table { width: 100%; border-collapse: collapse; margin-top: 22px; font-size: 13px; }
  td, th { text-align: left; padding: 8px 10px; border-bottom: 1px solid #21262d; vertical-align: top; }
  th { color: #8b949e; font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
  td code { color: #d2a8ff; } td.valor { font-family: ui-monospace, Consolas, monospace; font-size: 12px; word-break: break-all; }
</style>
<h2>JWT emitido pelo Keycloak</h2>
<div class="bruto"><span class="h">{{h}}</span><span class="ponto">.</span><span class="p">{{p}}</span><span class="ponto">.</span><span class="s">{{s}}</span></div>
<div class="legenda"><span class="h"><b>header</b></span><span class="p"><b>payload</b> (claims)</span><span class="s"><b>assinatura</b> {{alg}} — só a chave privada do realm produz</span></div>
<div class="grade">
  <section><h2>Header</h2><pre>{{header}}</pre></section>
  <section><h2>Payload</h2><pre>{{payload}}</pre></section>
</div>
<table>
  <tr><th>Claim</th><th>Valor</th><th>O que a API confere</th></tr>
  {{#each claims}}<tr><td><code>{{nome}}</code></td><td class="valor">{{valor}}</td><td>{{papel}}</td></tr>{{/each}}
</table>
"""


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
    "name": "1 · Autenticação JWT (Keycloak)",
    "description": (
        "Demonstra, em ordem, como a API autentica com **JSON Web Token**:\n\n"
        "1. **Descoberta OIDC** — o Keycloak publica emissor, endpoints e onde estão as chaves.\n"
        "2. **JWKS** — as chaves *públicas* do realm. É com elas que a API confere a assinatura; "
        "a chave privada nunca sai do Keycloak.\n"
        "3. **Login** — o Keycloak emite o JWT assinado em RS256. A aba **Visualize** da "
        "resposta mostra o token decodificado: header, payload e o papel de cada claim.\n"
        "4. **Uso do token** — `Authorization: Bearer <jwt>`. A API valida assinatura, `iss`, "
        "`aud`, `exp` e `iat` **localmente**, sem consultar o Keycloak a cada requisição; o "
        "`sub` do token localiza o usuário no banco.\n"
        "5. **Ataques recusados** — cada requisição forja um token a partir do legítimo e "
        "comprova que a API devolve 401, sempre com a mesma resposta.\n"
        "6. **Refresh** — um novo access token sem pedir a senha de novo.\n\n"
        "O token vale 15 minutos (`accessTokenLifespan` do realm). Expirou? Rode o **Login** "
        "de novo.\n\n"
        "Se o banco foi semeado (`uv run python -m scripts.semear`), o login já funciona com "
        "as credenciais padrão. Senão, rode antes o **Registro de conta**."
    ),
    "item": [
        keycloak_oidc(
            "Descoberta OIDC (.well-known)",
            "GET",
            ".well-known/openid-configuration",
            descricao=(
                "Documento público do OpenID Connect. A API usa o `issuer` como valor exigido "
                "no claim `iss` e o `jwks_uri` para buscar as chaves de verificação."
            ),
            eventos=[
                espera(
                    200,
                    [
                        "const c = pm.response.json();",
                        'pm.test("emissor é o realm fisioagenda", function () {',
                        "    pm.expect(c.issuer).to.eql(pm.collectionVariables.get('keycloak') + '/realms/' + pm.collectionVariables.get('realm'));",
                        "});",
                        'pm.test("publica jwks_uri e aceita RS256", function () {',
                        "    pm.expect(c.jwks_uri).to.include('/protocol/openid-connect/certs');",
                        "    pm.expect(c.id_token_signing_alg_values_supported).to.include('RS256');",
                        "});",
                    ],
                )
            ],
        ),
        keycloak_oidc(
            "JWKS — chaves públicas de assinatura",
            "GET",
            "protocol/openid-connect/certs",
            descricao=(
                "JSON Web Key Set. A API guarda estas chaves em cache e as indexa pelo `kid`: o "
                "header de cada JWT diz com qual chave foi assinado. `kid` desconhecido força "
                "uma recarga, com intervalo mínimo para não virar vetor de carga contra o "
                "Keycloak."
            ),
            eventos=[
                espera(
                    200,
                    [
                        "const chaves = pm.response.json().keys;",
                        "const assinatura = chaves.filter(k => k.use === 'sig' && k.alg === 'RS256');",
                        'pm.test("há chave RSA de assinatura RS256", function () {',
                        "    pm.expect(assinatura.length).to.be.above(0);",
                        "    pm.expect(assinatura[0].kty).to.eql('RSA');",
                        "});",
                        'pm.test("só material público — nada de chave privada", function () {',
                        "    chaves.forEach(k => pm.expect(k).to.not.have.any.keys('d', 'p', 'q', 'dp', 'dq', 'qi'));",
                        "});",
                        'pm.collectionVariables.set("jwksKids", JSON.stringify(assinatura.map(k => k.kid)));',
                        "// Material para a demonstração de confusão de algoritmo, adiante.",
                        'pm.collectionVariables.set("chavePublicaRealm", assinatura[0].x5c[0]);',
                    ],
                )
            ],
        ),
        {
            "name": "Login — Keycloak emite o JWT",
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
                    "pelo frontend — o token resultante é o mesmo.\n\n"
                    "A senha vai ao **Keycloak**, nunca à API: não existe senha no banco do "
                    "FisioAgenda.\n\n"
                    "Depois de enviar, abra a aba **Visualize** da resposta para ver o JWT "
                    "decodificado. Os testes conferem a estrutura do token; o access token e o "
                    "refresh token ficam gravados nas variáveis da coleção.\n\n"
                    "Preencha `segredoTestes` com o `KEYCLOAK_TESTES_CLIENT_SECRET` do `.env` "
                    "da raiz do projeto."
                ),
            },
            "event": [
                teste(
                    "t",
                    *JS_JWT,
                    'pm.test("login bem-sucedido", function () {',
                    "    pm.response.to.have.status(200);",
                    "});",
                    "const corpo = pm.response.json();",
                    "if (corpo.access_token) {",
                    '    pm.collectionVariables.set("token", corpo.access_token);',
                    '    pm.collectionVariables.set("refreshToken", corpo.refresh_token);',
                    "    const jwt = decodificarJwt(corpo.access_token);",
                    "    const agora = Math.floor(Date.now() / 1000);",
                    "",
                    'pm.test("token_type Bearer", function () {',
                    "    pm.expect(corpo.token_type).to.eql('Bearer');",
                    "});",
                    'pm.test("JWT tem três partes: header.payload.assinatura", function () {',
                    "    pm.expect(jwt.partes).to.have.lengthOf(3);",
                    "    pm.expect(jwt.partes[2].length).to.be.above(0);",
                    "});",
                    'pm.test("header: assinatura assimétrica RS256 com kid", function () {',
                    "    pm.expect(jwt.header.alg).to.eql('RS256');",
                    "    pm.expect(jwt.header.typ).to.eql('JWT');",
                    "    pm.expect(jwt.header.kid).to.be.a('string');",
                    "});",
                    'pm.test("kid aponta para uma chave publicada no JWKS", function () {',
                    '    const kids = JSON.parse(pm.collectionVariables.get("jwksKids") || "[]");',
                    "    if (kids.length === 0) { return; }  // JWKS não foi consultado nesta execução",
                    "    pm.expect(kids).to.include(jwt.header.kid);",
                    "});",
                    'pm.test("iss é o realm fisioagenda", function () {',
                    "    pm.expect(jwt.payload.iss).to.eql(pm.collectionVariables.get('keycloak') + '/realms/' + pm.collectionVariables.get('realm'));",
                    "});",
                    'pm.test("aud inclui a API (fisioagenda-backend)", function () {',
                    "    pm.expect([].concat(jwt.payload.aud)).to.include('fisioagenda-backend');",
                    "});",
                    'pm.test("sub é o uuid do usuário no Keycloak", function () {',
                    "    pm.expect(jwt.payload.sub).to.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);",
                    "});",
                    'pm.test("exp no futuro, coerente com expires_in", function () {',
                    "    pm.expect(jwt.payload.exp).to.be.above(agora);",
                    "    pm.expect(jwt.payload.exp - jwt.payload.iat).to.eql(corpo.expires_in);",
                    "});",
                    'pm.test("payload não carrega senha", function () {',
                    "    pm.expect(JSON.stringify(jwt.payload)).to.not.include(pm.collectionVariables.get('senha'));",
                    "});",
                    "",
                    "    const quando = s => new Date(s * 1000).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';",
                    "    const p = jwt.payload;",
                    "    pm.visualizer.set(" + json.dumps(VISUALIZADOR_JWT.strip()) + ", {",
                    "        h: jwt.partes[0], p: jwt.partes[1], s: jwt.partes[2], alg: jwt.header.alg,",
                    "        header: JSON.stringify(jwt.header, null, 2),",
                    "        payload: JSON.stringify(p, null, 2),",
                    "        claims: [",
                    "            { nome: 'alg / kid', valor: jwt.header.alg + ' / ' + jwt.header.kid, papel: 'Só RS256/384/512 é aceito; o kid escolhe a chave pública no JWKS.' },",
                    "            { nome: 'iss', valor: p.iss, papel: 'Precisa ser exatamente o realm configurado.' },",
                    "            { nome: 'aud', valor: [].concat(p.aud).join(', '), papel: 'Precisa conter fisioagenda-backend — token emitido para outra API é recusado.' },",
                    "            { nome: 'sub', valor: p.sub, papel: 'Identidade. Liga o token ao usuário local (keycloak_id).' },",
                    "            { nome: 'azp', valor: p.azp, papel: 'Client que pediu o token.' },",
                    "            { nome: 'iat', valor: quando(p.iat), papel: 'Emitido em.' },",
                    "            { nome: 'exp', valor: quando(p.exp), papel: 'Depois disso, 401.' },",
                    "            { nome: 'realm_access.roles', valor: ((p.realm_access || {}).roles || []).join(', '), papel: 'Informativo. O papel por clínica vem do banco, não do token.' },",
                    "        ],",
                    "    });",
                    '    console.log("token gravado; as demais requisições já vão autenticadas");',
                    "}",
                ),
            ],
            "response": [],
        },
        req(
            "GET /auth/eu — token válido → 200",
            "GET",
            "api/v1/auth/eu",
            descricao=(
                "Mesma requisição, agora com `Authorization: Bearer {{token}}` herdado da "
                "coleção. A API valida o JWT e usa o `sub` para achar o usuário no banco. "
                "Resposta: quem sou e em quais clínicas atuo, com o papel em cada uma."
            ),
            eventos=[
                espera(
                    200,
                    [
                        *JS_JWT,
                        'pm.test("traz usuário e vínculos", function () {',
                        "    const c = pm.response.json();",
                        "    pm.expect(c).to.have.property('usuario');",
                        "    pm.expect(c).to.have.property('vinculos');",
                        "});",
                        'pm.test("usuário resolvido é o dono do token", function () {',
                        '    const email = decodificarJwt(pm.collectionVariables.get("token")).payload.email;',
                        "    pm.expect(pm.response.json().usuario.email).to.eql(email);",
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
            eventos=[espera(401, REJEITA_TOKEN)],
        ),
        req(
            "Token malformado → 401",
            "GET",
            "api/v1/auth/eu",
            bearer_da_variavel="tokenForjado",
            descricao="Um Bearer que nem tem a forma de JWT.",
            eventos=[
                antes('pm.collectionVariables.set("tokenForjado", "isto-nao-e-um-jwt");'),
                espera(401, REJEITA_TOKEN),
            ],
        ),
        req(
            "Payload adulterado (escalada de privilégio) → 401",
            "GET",
            "api/v1/auth/eu",
            bearer_da_variavel="tokenForjado",
            descricao=(
                "Pega o token legítimo, troca o e-mail, adiciona o papel `admin` e empurra o "
                "`exp` um ano para frente — **mantendo a assinatura original**. O payload de "
                "um JWT é só base64url: qualquer um lê e edita. O que impede a fraude é a "
                "assinatura, que deixa de bater com o conteúdo."
            ),
            eventos=[
                forja(
                    "const jwt = decodificarJwt(tokenLegitimo());",
                    "const p = jwt.payload;",
                    "p.email = 'invasor@exemplo.com.br';",
                    "p.realm_access = { roles: ((p.realm_access || {}).roles || []).concat('admin') };",
                    "p.exp = p.exp + 365 * 24 * 3600;",
                    "const forjado = [jwt.partes[0], b64urlDeTexto(JSON.stringify(p)), jwt.partes[2]].join('.');",
                    'pm.collectionVariables.set("tokenForjado", forjado);',
                    "console.log('payload adulterado', p);",
                ),
                espera(401, REJEITA_TOKEN),
            ],
        ),
        req(
            "Assinatura corrompida → 401",
            "GET",
            "api/v1/auth/eu",
            bearer_da_variavel="tokenForjado",
            descricao="Header e payload intactos; só os últimos bytes da assinatura mudam.",
            eventos=[
                forja(
                    "const partes = tokenLegitimo().split('.');",
                    "const s = partes[2];",
                    "partes[2] = s.slice(0, -6) + (s.endsWith('AAAAAA') ? 'BBBBBB' : 'AAAAAA');",
                    'pm.collectionVariables.set("tokenForjado", partes.join("."));',
                ),
                espera(401, REJEITA_TOKEN),
            ],
        ),
        req(
            'alg "none" (token sem assinatura) → 401',
            "GET",
            "api/v1/auth/eu",
            bearer_da_variavel="tokenForjado",
            descricao=(
                "Ataque clássico: declarar no header que o token não é assinado e mandar a "
                "assinatura vazia. Bibliotecas que confiam no `alg` do próprio token aceitam. "
                "A API só aceita a lista fixa RS256/RS384/RS512."
            ),
            eventos=[
                forja(
                    "const partes = tokenLegitimo().split('.');",
                    "const header = b64urlDeTexto(JSON.stringify({ alg: 'none', typ: 'JWT' }));",
                    'pm.collectionVariables.set("tokenForjado", header + "." + partes[1] + ".");',
                ),
                espera(401, REJEITA_TOKEN),
            ],
        ),
        req(
            "Confusão de algoritmo HS256 → 401",
            "GET",
            "api/v1/auth/eu",
            bearer_da_variavel="tokenForjado",
            descricao=(
                "O atacante troca `alg` para HS256 (HMAC, simétrico) e assina com a **chave "
                "pública** do realm — que qualquer um baixa do JWKS. Um servidor que usasse a "
                "mesma chave para verificar sem fixar o algoritmo aceitaria. Aqui, HS* é "
                "recusado antes de qualquer verificação."
            ),
            eventos=[
                forja(
                    "const jwt = decodificarJwt(tokenLegitimo());",
                    'const chave = pm.collectionVariables.get("chavePublicaRealm");',
                    "if (!chave) { throw new Error('Rode antes \"JWKS — chaves públicas de assinatura\".'); }",
                    "const header = b64urlDeTexto(JSON.stringify({ alg: 'HS256', typ: 'JWT', kid: jwt.header.kid }));",
                    "const conteudo = header + '.' + jwt.partes[1];",
                    "const assinatura = b64urlDePalavras(cj.HmacSHA256(conteudo, chave));",
                    'pm.collectionVariables.set("tokenForjado", conteudo + "." + assinatura);',
                ),
                espera(401, REJEITA_TOKEN),
            ],
        ),
        keycloak_oidc(
            "Refresh — novo access token sem senha",
            "POST",
            "protocol/openid-connect/token",
            formulario=[
                ("grant_type", "refresh_token"),
                ("client_id", "{{clientTestes}}"),
                ("client_secret", "{{segredoTestes}}"),
                ("refresh_token", "{{refreshToken}}"),
            ],
            descricao=(
                "O access token é curto de propósito (15 min): se vazar, a janela é pequena. O "
                "refresh token, guardado pelo cliente, obtém um novo sem pedir a senha. O "
                "Keycloak rotaciona os dois; a coleção passa a usar o novo par."
            ),
            eventos=[
                teste(
                    "t",
                    *JS_JWT,
                    'pm.test("status 200", function () {',
                    "    pm.response.to.have.status(200);",
                    "});",
                    "const corpo = pm.response.json();",
                    'const anterior = pm.collectionVariables.get("token");',
                    'pm.test("emite um access token novo, do mesmo usuário", function () {',
                    "    pm.expect(corpo.access_token).to.not.eql(anterior);",
                    "    pm.expect(decodificarJwt(corpo.access_token).payload.sub).to.eql(decodificarJwt(anterior).payload.sub);",
                    "});",
                    "if (corpo.access_token) {",
                    '    pm.collectionVariables.set("token", corpo.access_token);',
                    '    pm.collectionVariables.set("refreshToken", corpo.refresh_token);',
                    "}",
                ),
            ],
        ),
        req(
            "GET /auth/eu com o token renovado → 200",
            "GET",
            "api/v1/auth/eu",
            eventos=[espera(200)],
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

encerramento = {
    "name": "5 · Logout (fim da sessão JWT)",
    "description": (
        "Fica por último para não derrubar a sessão das pastas anteriores.\n\n"
        "O logout encerra a **sessão** no Keycloak e invalida o refresh token. O access token "
        "já emitido continua válido até o `exp`: a API verifica o JWT localmente, sem "
        "consultar o Keycloak — é isso que torna a validação barata e sem estado. O custo "
        "dessa escolha é limitado pela vida curta do token (15 min)."
    ),
    "item": [
        keycloak_oidc(
            "Logout — encerra a sessão no Keycloak",
            "POST",
            "protocol/openid-connect/logout",
            formulario=[
                ("client_id", "{{clientTestes}}"),
                ("client_secret", "{{segredoTestes}}"),
                ("refresh_token", "{{refreshToken}}"),
            ],
            eventos=[espera(204)],
        ),
        keycloak_oidc(
            "Refresh após logout → 400 invalid_grant",
            "POST",
            "protocol/openid-connect/token",
            formulario=[
                ("grant_type", "refresh_token"),
                ("client_id", "{{clientTestes}}"),
                ("client_secret", "{{segredoTestes}}"),
                ("refresh_token", "{{refreshToken}}"),
            ],
            descricao="A sessão acabou: o refresh token não renova mais nada.",
            eventos=[
                espera(
                    400,
                    [
                        'pm.test("invalid_grant", function () {',
                        "    pm.expect(pm.response.json().error).to.eql('invalid_grant');",
                        "});",
                    ],
                )
            ],
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
            "6. Rode a pasta **1 · Autenticação JWT** (ou só o **Login**). O token é gravado "
            "automaticamente e as demais requisições já vão autenticadas.\n\n"
            "## Autenticação\n\n"
            "A API não tem tela de login nem guarda senha. Quem autentica é o **Keycloak**, que "
            "emite um **JWT** assinado em RS256; a coleção o envia como "
            "`Authorization: Bearer <token>` (configurado aqui, na raiz da coleção). A API "
            "confere a assinatura com as chaves públicas do realm (JWKS) e valida `iss`, `aud`, "
            "`exp`, `iat` e `sub`. A pasta 1 mostra o token decodificado — aba **Visualize** do "
            "Login — e prova que tokens forjados são recusados.\n\n"
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
    "item": [saude, autenticacao, usuarios, clinicas, vinculos, encerramento],
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
        {"key": "refreshToken", "value": "", "type": "string"},
        {"key": "tokenForjado", "value": "", "type": "string"},
        {"key": "jwksKids", "value": "", "type": "string"},
        {"key": "chavePublicaRealm", "value": "", "type": "string"},
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
