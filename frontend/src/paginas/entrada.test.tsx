import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PaginaEntrada } from "./entrada";

const auth = vi.hoisted(() => ({ signinRedirect: vi.fn() }));
vi.mock("react-oidc-context", () => ({ useAuth: () => auth }));

describe("PaginaEntrada", () => {
  it("Entrar leva ao Keycloak", async () => {
    render(<PaginaEntrada />);

    await userEvent.click(screen.getByRole("button", { name: /entrar/i }));

    expect(auth.signinRedirect).toHaveBeenCalledOnce();
  });
});
