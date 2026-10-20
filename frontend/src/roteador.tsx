import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router";
import type { AuthContextProps } from "react-oidc-context";
import { exigirSessao } from "./auth/guarda";
import { TelaCarregando, TelaErro } from "./componentes/telas";
import { PaginaEntrada } from "./paginas/entrada";
import { PaginaInicio } from "./paginas/inicio";

export interface ContextoDoRoteador {
  auth: AuthContextProps;
}

const raiz = createRootRouteWithContext<ContextoDoRoteador>()({ component: Outlet });

const entrada = createRoute({
  getParentRoute: () => raiz,
  path: "/",
  beforeLoad: ({ context }) => {
    if (context.auth.isAuthenticated) throw redirect({ to: "/inicio" });
  },
  component: PaginaEntrada,
});

const inicio = createRoute({
  getParentRoute: () => raiz,
  path: "/inicio",
  beforeLoad: ({ context }) => exigirSessao(context.auth),
  component: PaginaInicio,
});

// O AuthProvider troca /callback por /inicio antes do roteador montar; chegar
// aqui sem código de autorização é endereço digitado à mão.
const callback = createRoute({
  getParentRoute: () => raiz,
  path: "/callback",
  beforeLoad: () => {
    throw redirect({ to: "/" });
  },
});

export const roteador = createRouter({
  routeTree: raiz.addChildren([entrada, inicio, callback]),
  // O contexto real chega pelo RouterProvider, a cada render.
  context: { auth: undefined as unknown as AuthContextProps },
  defaultPendingComponent: TelaCarregando,
  defaultErrorComponent: ({ error }) => (
    <TelaErro
      titulo="Não foi possível abrir esta página"
      detalhe={error instanceof Error ? error.message : String(error)}
    />
  ),
  defaultNotFoundComponent: () => (
    <TelaErro titulo="Página não encontrada" detalhe="Este endereço não existe no FisioAgenda." />
  ),
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof roteador;
  }
}
