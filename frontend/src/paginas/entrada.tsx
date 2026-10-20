import { useAuth } from "react-oidc-context";

export function PaginaEntrada() {
  const auth = useAuth();

  return (
    <main className="relative min-h-dvh overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(1200px_600px_at_15%_-10%,rgb(180_228_200/0.10),transparent_60%)]"
      />
      <div className="relative mx-auto flex min-h-dvh max-w-6xl flex-col justify-between px-6 py-10 sm:px-10">
        <header className="flex items-center justify-between text-sm text-suave">
          <span className="font-display text-xl tracking-tight text-texto">FisioAgenda</span>
          <span>Uso interno</span>
        </header>

        <section className="max-w-4xl py-20">
          <p className="text-xs uppercase tracking-[0.24em] text-acento">
            Agenda · Evolução · Mensalidades
          </p>
          <h1 className="mt-8 font-display text-5xl leading-[1.02] tracking-[-0.03em] sm:text-7xl">
            O cuidado acontece na clínica. <span className="text-suave">A organização, aqui.</span>
          </h1>
          <button
            type="button"
            onClick={() => void auth.signinRedirect()}
            className="group mt-14 inline-flex items-center gap-3 rounded-full bg-acento px-8 py-4 text-sm font-semibold text-fundo transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-acento"
          >
            Entrar
            <span aria-hidden className="transition group-hover:translate-x-0.5">
              →
            </span>
          </button>
        </section>

        <footer className="flex flex-wrap gap-x-10 gap-y-2 text-xs text-suave">
          <span>OpenID Connect · Authorization Code + PKCE</span>
          <span>Identidade gerida pelo Keycloak</span>
        </footer>
      </div>
    </main>
  );
}
