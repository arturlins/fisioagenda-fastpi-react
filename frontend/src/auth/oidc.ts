import { InMemoryWebStorage, type UserManagerSettings, WebStorageStateStore } from "oidc-client-ts";
import type { Configuracao } from "../config";

/**
 * Authorization Code + PKCE (S256) contra o client público do realm.
 *
 * Os tokens ficam só em memória: nada para um XSS ler do storage. Ao recarregar
 * a página, a guarda de rota volta ao Keycloak, que responde na hora pela sessão
 * SSO — sem senha. Só o estado transitório do PKCE usa sessionStorage, e é
 * removido no callback.
 */
export function criarConfiguracaoOidc(config: Configuracao, origem: string): UserManagerSettings {
  return {
    authority: `${config.keycloakUrl}/realms/${config.realm}`,
    client_id: config.clientId,
    redirect_uri: `${origem}/callback`,
    post_logout_redirect_uri: `${origem}/`,
    response_type: "code",
    scope: "openid profile email",
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    automaticSilentRenew: true,
    monitorSession: false,
  };
}
