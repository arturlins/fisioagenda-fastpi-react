import { User, UserManager } from "oidc-client-ts";
import { afterEach, describe, expect, it } from "vitest";
import { criarConfiguracaoOidc } from "./oidc";

const config = {
  keycloakUrl: "https://auth.x.sslip.io",
  realm: "fisioagenda",
  clientId: "fisioagenda-web",
  apiUrl: "https://api.x.sslip.io",
};

describe("criarConfiguracaoOidc", () => {
  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it("aponta para o realm e volta pelo /callback", () => {
    const oidc = criarConfiguracaoOidc(config, "https://app.x.sslip.io");

    expect(oidc.authority).toBe("https://auth.x.sslip.io/realms/fisioagenda");
    expect(oidc.client_id).toBe("fisioagenda-web");
    expect(oidc.redirect_uri).toBe("https://app.x.sslip.io/callback");
    expect(oidc.post_logout_redirect_uri).toBe("https://app.x.sslip.io/");
    expect(oidc.response_type).toBe("code");
    expect(oidc.scope).toBe("openid profile email");
  });

  it("guarda os tokens só em memória", async () => {
    const gerenciador = new UserManager(criarConfiguracaoOidc(config, "https://app.x.sslip.io"));

    await gerenciador.storeUser(
      new User({
        access_token: "token-de-acesso",
        refresh_token: "token-de-renovacao",
        token_type: "Bearer",
        profile: { sub: "1", iss: "i", aud: "a", exp: 0, iat: 0 },
      }),
    );

    expect(sessionStorage.length).toBe(0);
    expect(localStorage.length).toBe(0);
    expect((await gerenciador.getUser())?.access_token).toBe("token-de-acesso");
  });
});
