import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useMemo } from "react";
import { AuthProvider, useAuth } from "react-oidc-context";
import { criarConfiguracaoOidc } from "./auth/oidc";
import { TelaCarregando, TelaErro } from "./componentes/telas";
import type { Configuracao } from "./config";
import { ConfiguracaoProvider } from "./contexto-config";
import { roteador } from "./roteador";

const consultas = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

// Tira code e state da URL antes do roteador montar: o histórico não guarda o
// código de autorização, e o usuário cai direto no painel.
function aposLogin(): void {
  window.history.replaceState({}, document.title, "/inicio");
}

export function Aplicacao({ config }: { config: Configuracao }) {
  const oidc = useMemo(() => criarConfiguracaoOidc(config, window.location.origin), [config]);

  return (
    <AuthProvider {...oidc} onSigninCallback={aposLogin}>
      <QueryClientProvider client={consultas}>
        <ConfiguracaoProvider valor={config}>
          <Roteamento />
        </ConfiguracaoProvider>
      </QueryClientProvider>
    </AuthProvider>
  );
}

function Roteamento() {
  const auth = useAuth();

  if (auth.isLoading) return <TelaCarregando />;
  if (auth.error && !auth.isAuthenticated) {
    return (
      <TelaErro
        titulo="Não foi possível concluir o login"
        detalhe={auth.error.message}
        acao={{ rotulo: "Tentar de novo", aoClicar: () => void auth.signinRedirect() }}
      />
    );
  }
  return <RouterProvider router={roteador} context={{ auth }} />;
}
