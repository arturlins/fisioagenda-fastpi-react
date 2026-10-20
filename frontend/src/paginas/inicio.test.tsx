import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfiguracaoProvider } from "../contexto-config";
import { MARCADOR_RELOGIN, PaginaInicio } from "./inicio";

// Emissor do token diferente do da config: o cartão tem de mostrar o `iss` do token.
const EMISSOR_DO_TOKEN = "https://auth.token.sslip.io/realms/fisioagenda";

const auth = vi.hoisted(() => ({
  user: {
    access_token: "abc",
    expires_at: Math.floor(Date.now() / 1000) + 900,
    profile: { iss: "https://auth.token.sslip.io/realms/fisioagenda" } as { iss?: string },
  },
  signinRedirect: vi.fn(),
  signoutRedirect: vi.fn(),
}));
vi.mock("react-oidc-context", () => ({ useAuth: () => auth }));

const config = {
  keycloakUrl: "https://auth.x.sslip.io",
  realm: "fisioagenda",
  clientId: "fisioagenda-web",
  apiUrl: "https://api.x.sslip.io",
};

const usuario = {
  public_id: "3f1c9a52-6a0e-4c1f-9d7b-2a4b8e9c0d11",
  nome: "Bruno Carvalho Lima",
  email: "bruno@clinicamovimento.com.br",
  dono_da_conta: false,
  e_profissional: true,
  especialidade: null,
};

function responderCom(corpo: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(corpo), { status })),
  );
}

function renderizar() {
  const consultas = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={consultas}>
      <ConfiguracaoProvider valor={config}>
        <PaginaInicio />
      </ConfiguracaoProvider>
    </QueryClientProvider>,
  );
}

describe("PaginaInicio", () => {
  beforeEach(() => {
    auth.user.profile.iss = EMISSOR_DO_TOKEN;
    auth.signinRedirect.mockReset();
    auth.signoutRedirect.mockReset();
    sessionStorage.clear();
  });

  it("mostra o papel em cada clínica", async () => {
    responderCom({
      usuario,
      vinculos: [
        {
          clinica_public_id: "8a2d4f60-1b3c-4e5f-8a9b-0c1d2e3f4a5b",
          clinica_nome: "Unidade Centro",
          papel: "administrador",
          ativo: true,
        },
        {
          clinica_public_id: "1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d",
          clinica_nome: "Unidade Farol",
          papel: "comum",
          ativo: true,
        },
      ],
    });

    renderizar();

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Bruno");
    const centro = screen.getByRole("listitem", { name: /unidade centro/i });
    expect(within(centro).getByText("Administrador")).toBeInTheDocument();
    const farol = screen.getByRole("listitem", { name: /unidade farol/i });
    expect(within(farol).getByText("Comum")).toBeInTheDocument();
    expect(screen.getByText(EMISSOR_DO_TOKEN)).toBeInTheDocument();
  });

  it("token sem iss mostra o emissor como ausente", async () => {
    // O beforeEach devolve o iss para os outros testes.
    delete auth.user.profile.iss;
    responderCom({ usuario, vinculos: [] });
    renderizar();

    const emissor = (await screen.findByText("Emissor do token")).nextElementSibling;
    expect(emissor).toHaveTextContent("—");
    expect(screen.queryByText(/realms\/fisioagenda/)).not.toBeInTheDocument();
  });

  it("responsável pela conta sem vínculo vê que administra tudo", async () => {
    responderCom({
      usuario: { ...usuario, nome: "Ana Ribeiro Souza", dono_da_conta: true },
      vinculos: [],
    });

    renderizar();

    expect(await screen.findAllByText(/todas as clínicas/)).not.toHaveLength(0);
  });

  it("erro da API mostra o id de correlação", async () => {
    responderCom(
      { codigo: "erro_interno", mensagem: "Erro interno.", id_correlacao: "abc-123" },
      500,
    );

    renderizar();

    expect(await screen.findByText(/abc-123/)).toBeInTheDocument();
  });

  it("401 manda de volta ao Keycloak", async () => {
    responderCom({}, 401);

    renderizar();

    await vi.waitFor(() => expect(auth.signinRedirect).toHaveBeenCalled());
    expect(sessionStorage.getItem(MARCADOR_RELOGIN)).toBe("1");
  });

  it("segundo 401 seguido mostra o erro em vez de redirecionar sem fim", async () => {
    sessionStorage.setItem(MARCADOR_RELOGIN, "1");
    responderCom({}, 401);

    renderizar();

    expect(await screen.findByText("A API recusou sua sessão.")).toBeInTheDocument();
    expect(auth.signinRedirect).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Entrar de novo" }));

    expect(auth.signinRedirect).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(MARCADOR_RELOGIN)).toBeNull();
  });

  it("perfil carregado limpa a marca de novo login", async () => {
    sessionStorage.setItem(MARCADOR_RELOGIN, "1");
    responderCom({ usuario, vinculos: [] });

    renderizar();

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Bruno");
    expect(sessionStorage.getItem(MARCADOR_RELOGIN)).toBeNull();
  });

  it("Sair encerra a sessão no Keycloak", async () => {
    responderCom({ usuario, vinculos: [] });
    renderizar();

    await userEvent.click(screen.getByRole("button", { name: "Sair" }));

    expect(auth.signoutRedirect).toHaveBeenCalledOnce();
  });
});
