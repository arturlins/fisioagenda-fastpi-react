import { describe, expect, it, vi } from "vitest";
import { exigirSessao } from "./guarda";

const pendente = Symbol("pendente");
const emAte = <T>(promessa: Promise<T>, ms = 50) =>
  Promise.race([promessa, new Promise<typeof pendente>((r) => setTimeout(() => r(pendente), ms))]);

describe("exigirSessao", () => {
  it("libera quem tem sessão", async () => {
    const signinRedirect = vi.fn();

    await expect(exigirSessao({ isAuthenticated: true, signinRedirect })).resolves.toBeUndefined();
    expect(signinRedirect).not.toHaveBeenCalled();
  });

  it("sem sessão, manda ao Keycloak e não libera a rota", async () => {
    const signinRedirect = vi.fn().mockResolvedValue(undefined);

    const resultado = await emAte(exigirSessao({ isAuthenticated: false, signinRedirect }));

    expect(resultado).toBe(pendente);
    expect(signinRedirect).toHaveBeenCalledOnce();
  });

  it("propaga a falha quando o Keycloak não responde", async () => {
    const signinRedirect = vi.fn().mockRejectedValue(new Error("Keycloak fora do ar"));

    await expect(exigirSessao({ isAuthenticated: false, signinRedirect })).rejects.toThrow(
      "Keycloak fora do ar",
    );
  });
});
