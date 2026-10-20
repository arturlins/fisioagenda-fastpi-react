import type { AuthContextProps } from "react-oidc-context";

/**
 * Guarda das rotas protegidas. Sem sessão, o navegador sai para o Keycloak e a
 * rota nunca termina de carregar — nada protegido chega a renderizar.
 */
export async function exigirSessao(
  auth: Pick<AuthContextProps, "isAuthenticated" | "signinRedirect">,
): Promise<void> {
  if (auth.isAuthenticated) return;
  await auth.signinRedirect();
  await new Promise<never>(() => {});
}
