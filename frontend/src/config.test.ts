import { describe, expect, it } from "vitest";
import { ConfiguracaoInvalidaError, carregarConfiguracao } from "./config";

const valida = {
  keycloakUrl: "https://auth.203-0-113-10.sslip.io/",
  realm: "fisioagenda",
  clientId: "fisioagenda-web",
  apiUrl: "https://api.203-0-113-10.sslip.io",
};

const responder =
  (corpo: unknown, status = 200): typeof fetch =>
  async () =>
    new Response(typeof corpo === "string" ? corpo : JSON.stringify(corpo), { status });

describe("carregarConfiguracao", () => {
  it("carrega e tira a barra final das URLs", async () => {
    const config = await carregarConfiguracao(responder(valida));

    expect(config.keycloakUrl).toBe("https://auth.203-0-113-10.sslip.io");
    expect(config.apiUrl).toBe("https://api.203-0-113-10.sslip.io");
  });

  it("recusa campo ausente dizendo qual", async () => {
    const semApi = Object.fromEntries(
      Object.entries(valida).filter(([campo]) => campo !== "apiUrl"),
    );

    await expect(carregarConfiguracao(responder(semApi))).rejects.toThrow(/apiUrl/);
  });

  it("recusa URL inválida", async () => {
    await expect(
      carregarConfiguracao(responder({ ...valida, keycloakUrl: "auth sem esquema" })),
    ).rejects.toBeInstanceOf(ConfiguracaoInvalidaError);
  });

  it("recusa resposta de erro", async () => {
    await expect(carregarConfiguracao(responder("", 404))).rejects.toThrow(/404/);
  });

  // O fallback do SPA devolve index.html com 200 quando /config.json não existe.
  it("recusa corpo HTML com mensagem clara", async () => {
    await expect(
      carregarConfiguracao(responder("<!doctype html><div id=root></div>")),
    ).rejects.toThrow(/não é JSON/);
  });

  it("recusa falha de rede", async () => {
    const semRede: typeof fetch = async () => {
      throw new TypeError("Failed to fetch");
    };

    await expect(carregarConfiguracao(semRede)).rejects.toBeInstanceOf(ConfiguracaoInvalidaError);
  });
});
