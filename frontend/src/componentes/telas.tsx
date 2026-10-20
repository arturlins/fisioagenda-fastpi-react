export function TelaCarregando() {
  return (
    <div role="status" aria-live="polite" className="grid min-h-dvh place-items-center">
      <span className="text-sm tracking-wide text-suave">Carregando…</span>
    </div>
  );
}

export function TelaErro({
  titulo,
  detalhe,
  acao,
}: {
  titulo: string;
  detalhe: string;
  acao?: { rotulo: string; aoClicar: () => void } | undefined;
}) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center px-6">
      <p className="text-xs uppercase tracking-[0.2em] text-perigo">Algo não saiu como previsto</p>
      <h1 className="mt-4 font-display text-4xl tracking-tight">{titulo}</h1>
      <p className="mt-4 text-suave">{detalhe}</p>
      {acao && (
        <button
          type="button"
          onClick={acao.aoClicar}
          className="mt-10 w-fit rounded-full border border-borda px-6 py-3 text-sm transition hover:border-suave focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-acento"
        >
          {acao.rotulo}
        </button>
      )}
    </main>
  );
}
