import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { buscarPerfil, ErroDaApi, NaoAutenticadoError, type Perfil } from "../api/perfil";
import { useConfiguracao } from "../contexto-config";
import {
  formatarRestante,
  primeiroNome,
  resumoDoAcesso,
  rotuloDoPapel,
  saudacao,
} from "./formatacao";

// Só vale repetir o que pode passar sozinho: rede fora ou gateway sem a API.
// Erro com id de correlação é determinístico e aparece na hora.
const STATUS_TRANSITORIOS = new Set([0, 502, 503, 504]);

function falhaTransitoria(erro: Error): boolean {
  return erro instanceof ErroDaApi && STATUS_TRANSITORIOS.has(erro.status);
}

/**
 * Marca, por aba, que já houve um novo login automático depois de um 401. Não
 * guarda nada sensível — só "1". Sem ela, uma API que recusa todo token emitido
 * pelo realm (emissor, audiência ou relógio divergentes) faria o navegador
 * oscilar entre o SPA e o Keycloak para sempre.
 */
export const MARCADOR_RELOGIN = "fisioagenda:relogin-apos-401";

// Storage indisponível conta como marca presente: sem como limitar o laço,
// mostrar o erro é o caminho seguro.
function jaTentouRelogin(): boolean {
  try {
    return sessionStorage.getItem(MARCADOR_RELOGIN) !== null;
  } catch {
    return true;
  }
}

function marcarRelogin(): boolean {
  try {
    sessionStorage.setItem(MARCADOR_RELOGIN, "1");
    return true;
  } catch {
    return false;
  }
}

function limparRelogin(): void {
  try {
    sessionStorage.removeItem(MARCADOR_RELOGIN);
  } catch {
    // Nada a limpar se o storage não existe.
  }
}

export function PaginaInicio() {
  const auth = useAuth();
  const config = useConfiguracao();
  const token = auth.user?.access_token;
  const [sessaoRecusada, definirSessaoRecusada] = useState(false);

  const perfil = useQuery({
    queryKey: ["perfil"],
    queryFn: () => buscarPerfil(config.apiUrl, token ?? ""),
    enabled: token !== undefined,
    retry: (falhas, erro) => falhaTransitoria(erro) && falhas < 2,
  });

  // Token recusado pela API: uma única volta automática ao Keycloak por aba (a
  // sessão SSO decide se pede senha). Um segundo 401 seguido vira erro visível.
  useEffect(() => {
    if (!(perfil.error instanceof NaoAutenticadoError)) return;
    if (!jaTentouRelogin() && marcarRelogin()) {
      void auth.signinRedirect();
    } else {
      definirSessaoRecusada(true);
    }
  }, [perfil.error, auth]);

  useEffect(() => {
    if (perfil.data) limparRelogin();
  }, [perfil.data]);

  function entrarDeNovo(): void {
    limparRelogin();
    void auth.signinRedirect();
  }

  return (
    <div className="min-h-dvh">
      <Cabecalho nome={perfil.data?.usuario.nome} aoSair={() => void auth.signoutRedirect()} />
      <main className="mx-auto grid max-w-6xl gap-12 px-6 py-14 sm:px-10 lg:grid-cols-[1fr_320px]">
        {perfil.data ? (
          <Painel perfil={perfil.data} />
        ) : sessaoRecusada ? (
          <SessaoRecusada aoEntrar={entrarDeNovo} />
        ) : perfil.error && !(perfil.error instanceof NaoAutenticadoError) ? (
          <ErroDoPerfil erro={perfil.error} />
        ) : (
          <p role="status" className="text-sm text-suave">
            Carregando seu painel…
          </p>
        )}
        <CartaoSessao
          emissor={`${config.keycloakUrl}/realms/${config.realm}`}
          expiraEm={auth.user?.expires_at}
        />
      </main>
    </div>
  );
}

function Cabecalho({ nome, aoSair }: { nome: string | undefined; aoSair: () => void }) {
  return (
    <header className="border-b border-borda">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5 sm:px-10">
        <span className="font-display text-xl tracking-tight">FisioAgenda</span>
        <div className="flex items-center gap-5 text-sm">
          {nome && <span className="hidden text-suave sm:inline">{nome}</span>}
          <button
            type="button"
            onClick={aoSair}
            className="rounded-full border border-borda px-4 py-2 transition hover:border-suave focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-acento"
          >
            Sair
          </button>
        </div>
      </div>
    </header>
  );
}

function Painel({ perfil }: { perfil: Perfil }) {
  const { usuario } = perfil;
  const vinculos = perfil.vinculos.filter((vinculo) => vinculo.ativo);

  return (
    <section>
      <p className="text-xs uppercase tracking-[0.24em] text-acento">Painel</p>
      <h1 className="mt-5 font-display text-5xl leading-[1.04] tracking-[-0.03em] sm:text-6xl">
        {saudacao(new Date().getHours())}, {primeiroNome(usuario.nome)}.
      </h1>
      <p className="mt-5 max-w-xl text-suave">
        {resumoDoAcesso(usuario.dono_da_conta, vinculos.length)}
      </p>

      <h2 className="mt-16 text-sm font-medium text-suave">Suas clínicas</h2>
      {vinculos.length === 0 ? (
        <p className="mt-4 border-y border-borda py-6 text-suave">
          {usuario.dono_da_conta
            ? "Como responsável pela conta, você administra todas as clínicas."
            : "Nenhum vínculo ativo."}
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-borda border-y border-borda">
          {vinculos.map((vinculo) => (
            <li
              key={vinculo.clinica_public_id}
              aria-label={vinculo.clinica_nome}
              className="flex items-center justify-between gap-6 py-6"
            >
              <span className="font-display text-2xl tracking-tight">{vinculo.clinica_nome}</span>
              <span
                className={
                  vinculo.papel === "administrador"
                    ? "rounded-full border border-acento/50 px-3 py-1 text-xs text-acento"
                    : "rounded-full border border-borda px-3 py-1 text-xs text-suave"
                }
              >
                {rotuloDoPapel(vinculo.papel)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ErroDoPerfil({ erro }: { erro: Error }) {
  return (
    <section role="alert">
      <p className="text-xs uppercase tracking-[0.2em] text-perigo">Não foi possível carregar</p>
      <p className="mt-4 text-lg">{erro.message}</p>
      {erro instanceof ErroDaApi && erro.idCorrelacao && (
        <p className="mt-2 font-mono text-xs text-suave">id de correlação: {erro.idCorrelacao}</p>
      )}
    </section>
  );
}

function SessaoRecusada({ aoEntrar }: { aoEntrar: () => void }) {
  return (
    <section role="alert">
      <p className="text-xs uppercase tracking-[0.2em] text-perigo">Não foi possível carregar</p>
      <p className="mt-4 text-lg">A API recusou sua sessão.</p>
      <p className="mt-2 max-w-xl text-sm text-suave">
        O login no Keycloak deu certo, mas a API não aceitou o token — mesmo depois de uma nova
        tentativa.
      </p>
      <button
        type="button"
        onClick={aoEntrar}
        className="mt-8 rounded-full border border-borda px-6 py-3 text-sm transition hover:border-suave focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-acento"
      >
        Entrar de novo
      </button>
    </section>
  );
}

function useAgora(intervaloMs = 1000): number {
  const [agora, definirAgora] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => definirAgora(Date.now()), intervaloMs);
    return () => clearInterval(id);
  }, [intervaloMs]);
  return agora;
}

function CartaoSessao({ emissor, expiraEm }: { emissor: string; expiraEm: number | undefined }) {
  const agora = useAgora();
  const restante = expiraEm === undefined ? undefined : expiraEm - Math.floor(agora / 1000);

  return (
    <aside className="h-fit rounded-2xl border border-borda bg-superficie p-6">
      <p className="text-xs uppercase tracking-[0.2em] text-suave">Sessão</p>
      <dl className="mt-6 space-y-5 text-sm">
        <div>
          <dt className="text-suave">Emissor do token</dt>
          <dd className="mt-1 break-all font-mono text-xs">{emissor}</dd>
        </div>
        <div>
          <dt className="text-suave">Expira em</dt>
          <dd className="mt-1 font-display text-4xl tabular-nums tracking-tight">
            {restante === undefined ? "—" : formatarRestante(restante)}
          </dd>
        </div>
        <div>
          <dt className="text-suave">Validação</dt>
          <dd className="mt-1">Assinatura RS256 conferida pela API a cada requisição.</dd>
        </div>
      </dl>
    </aside>
  );
}
