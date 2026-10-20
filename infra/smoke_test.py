"""Smoke test pós-deploy do FisioAgenda.

    python -I infra/smoke_test.py 203-0-113-10.sslip.io --aguardar 600
    python -I infra/smoke_test.py 127-0-0-1.sslip.io --ca caddy-local.crt   # ensaio local

A verificação de TLS nunca é desligada. No ensaio, o Caddy assina com uma CA
local; --ca passa a confiar nela, e só nela.

Só biblioteca padrão: roda em qualquer máquina com Python, sem instalar nada.
Com --aguardar, repete até tudo passar ou o prazo acabar — entre o fim do
`terraform apply` e a pilha de pé, o cloud-init leva alguns minutos.

São 9 verificações, da SPA ao console administrativo; duas delas abrem a
página de login do Keycloak como o navegador abriria (PKCE, redirect do app e
do Swagger), o que prova a allowlist de produção com os placeholders resolvidos
e o tema carregado — não só que o Keycloak está de pé.

É a resposta a "a queda ocorreu sem alertas" do caso AbacatePay: o deploy só
é dado como pronto quando cada peça responde como deve, vista de fora.
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Resposta:
    status: int
    corpo: bytes

    def json(self) -> object:
        return json.loads(self.corpo)


Buscar = Callable[[str], Resposta]
Verificacao = Callable[[Buscar], str | None]  # None = passou; texto = motivo da falha

# Desafio PKCE fixo (43 caracteres base64url, o mínimo do RFC 7636): a página de login só
# precisa recebê-lo bem formado; o fluxo nunca chega à troca do código.
DESAFIO_PKCE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _cliente(contexto: ssl.SSLContext) -> Buscar:
    # Toda URL vem de verificacoes(), sempre com prefixo https:// fixo — nunca file: nem esquema
    # vindo de fora; por isso o S310 do ruff não se aplica.
    def buscar(url: str) -> Resposta:
        requisicao = urllib.request.Request(url, headers={"User-Agent": "fisioagenda-smoke/1"})  # noqa: S310
        try:
            with urllib.request.urlopen(requisicao, timeout=10, context=contexto) as resposta:  # noqa: S310
                return Resposta(resposta.status, resposta.read())
        except urllib.error.HTTPError as erro:
            return Resposta(erro.code, erro.read())

    return buscar


def verificacoes(dominio: str) -> list[tuple[str, Verificacao]]:
    app, api, auth = (f"https://{prefixo}.{dominio}" for prefixo in ("app", "api", "auth"))
    emissor = f"{auth}/realms/fisioagenda"

    def spa(buscar: Buscar) -> str | None:
        r = buscar(f"{app}/")
        return None if r.status == 200 and b'id="root"' in r.corpo else f"HTTP {r.status}"

    def configuracao(buscar: Buscar) -> str | None:
        r = buscar(f"{app}/config.json")
        try:
            dados = r.json()
        except ValueError:
            return f"HTTP {r.status}, corpo não é JSON"
        esperado = {"keycloakUrl": auth, "apiUrl": api}
        if not isinstance(dados, dict) or any(dados.get(k) != v for k, v in esperado.items()):
            return f"conteúdo inesperado: {dados}"
        return None

    def prontidao(buscar: Buscar) -> str | None:
        r = buscar(f"{api}/saude/pronto")
        return None if r.status == 200 else f"HTTP {r.status}: {r.corpo[:200]!r}"

    def descoberta_oidc(buscar: Buscar) -> str | None:
        r = buscar(f"{emissor}/.well-known/openid-configuration")
        if r.status != 200:
            return f"HTTP {r.status}"
        dados = r.json()
        emitido = dados.get("issuer") if isinstance(dados, dict) else None
        return None if emitido == emissor else f"issuer {emitido!r}, esperado {emissor!r}"

    def documentacao(buscar: Buscar) -> str | None:
        r = buscar(f"{api}/docs")
        return None if r.status == 200 else f"HTTP {r.status}"

    def rota_protegida(buscar: Buscar) -> str | None:
        r = buscar(f"{api}/api/v1/auth/eu")
        return None if r.status == 401 else f"HTTP {r.status}, esperado 401"

    def pagina_login(redirect_uri: str) -> Verificacao:
        parametros = urllib.parse.urlencode(
            {
                "client_id": "fisioagenda-web",
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": redirect_uri,
                "code_challenge": DESAFIO_PKCE,
                "code_challenge_method": "S256",
                "state": "smoke",
            }
        )

        def verificar(buscar: Buscar) -> str | None:
            r = buscar(f"{emissor}/protocol/openid-connect/auth?{parametros}")
            if r.status != 200:
                causa = "redirect não liberado" if b"redirect_uri" in r.corpo else "sem login"
                return f"HTTP {r.status}, {causa}: {redirect_uri}"
            if b'id="username"' not in r.corpo:
                return "HTTP 200, mas sem o formulário de login"
            if b"fisioagenda.css" not in r.corpo:
                return "formulário sem o tema fisioagenda"
            return None

        return verificar

    def console_fechado(buscar: Buscar) -> str | None:
        r = buscar(f"{auth}/admin/master/console/")
        return None if r.status == 404 else f"HTTP {r.status}, esperado 404"

    return [
        ("SPA publicado", spa),
        ("config.json derivado do domínio", configuracao),
        ("API pronta (banco e Keycloak)", prontidao),
        ("descoberta OIDC com o emissor público", descoberta_oidc),
        ("Swagger publicado", documentacao),
        ("rota protegida recusa sem token", rota_protegida),
        ("login do Keycloak (redirect do app aceito)", pagina_login(f"{app}/callback")),
        (
            "login do Keycloak (redirect do Swagger aceito)",
            pagina_login(f"{api}/docs/oauth2-redirect"),
        ),
        ("console admin fora da internet", console_fechado),
    ]


def _rodar(verificacao: Verificacao, buscar: Buscar) -> str | None:
    try:
        return verificacao(buscar)
    except urllib.error.URLError as erro:
        return f"inacessível: {erro.reason}"
    # HTTPException: resposta truncada ou malformada (IncompleteRead, BadStatusLine).
    # OSError: TLS (ssl.SSLError), conexão e timeout durante o read(). Nenhuma pode
    # derrubar o laço do --aguardar: é só mais uma tentativa que falhou.
    except (http.client.HTTPException, OSError, ValueError) as erro:
        return f"{type(erro).__name__}: {erro}"


def executar(dominio: str, ca: str | None, aguardar: float) -> int:
    contexto = ssl.create_default_context(cafile=ca)
    buscar = _cliente(contexto)
    prazo = time.monotonic() + aguardar

    while True:
        resultados = [(nome, _rodar(v, buscar)) for nome, v in verificacoes(dominio)]
        falhas = [nome for nome, motivo in resultados if motivo is not None]
        if not falhas or time.monotonic() >= prazo:
            break
        print(f"... {len(falhas)} pendente(s): {', '.join(falhas)} — nova tentativa em 10 s")
        time.sleep(10)

    for nome, motivo in resultados:
        print(
            f"[{'OK' if motivo is None else 'FALHOU'}] {nome}" + (f" — {motivo}" if motivo else "")
        )
    print("\nTudo verde." if not falhas else f"\n{len(falhas)} verificação(ões) falhando.")
    return 0 if not falhas else 1


def main() -> None:
    # A saída vira print de slide: acentos certos mesmo no console do Windows.
    # `python -I` ignora PYTHONUTF8, então tem de ser aqui.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Smoke test pós-deploy do FisioAgenda.")
    parser.add_argument("dominio", help="domínio base, ex.: 203-0-113-10.sslip.io")
    parser.add_argument("--ca", help="PEM de uma CA a confiar no lugar das do sistema (ensaio)")
    parser.add_argument("--aguardar", type=float, default=0, help="segundos de espera pela pilha")
    argumentos = parser.parse_args()
    sys.exit(executar(argumentos.dominio, argumentos.ca, argumentos.aguardar))


if __name__ == "__main__":
    main()
