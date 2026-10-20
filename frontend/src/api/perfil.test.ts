import { describe, expect, it, vi } from "vitest";
import { buscarPerfil, ErroDaApi, NaoAutenticadoError } from "./perfil";

const perfil = {
  usuario: {
    public_id: "3f1c9a52-6a0e-4c1f-9d7b-2a4b8e9c0d11",
    nome: "Bruno Carvalho Lima",
    email: "bruno@clinicamovimento.com.br",
    dono_da_conta: false,
    e_profissional: true,
    especialidade: "Ortopedia e Traumatologia",
  },
  vinculos: [
    {
      clinica_public_id: "8a2d4f60-1b3c-4e5f-8a9b-0c1d2e3f4a5b",
      clinica_nome: "Unidade Centro",
      papel: "administrador",
      ativo: true,
    },
  ],
};

const json = (corpo: unknown, status = 200) =>
  vi.fn<typeof fetch>(async () => new Response(JSON.stringify(corpo), { status }));

describe("buscarPerfil", () => {
  it("envia o token como Bearer e devolve o perfil", async () => {
    const buscar = json(perfil);

    const resultado = await buscarPerfil("https://api.x", "abc", buscar);

    expect(resultado.vinculos[0]?.papel).toBe("administrador");
    const [url, init] = buscar.mock.calls[0] ?? [];
    expect(url).toBe("https://api.x/api/v1/auth/eu");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer abc");
  });

  it("401 vira NaoAutenticadoError", async () => {
    await expect(buscarPerfil("https://api.x", "abc", json({}, 401))).rejects.toBeInstanceOf(
      NaoAutenticadoError,
    );
  });

  it("erro da API preserva código e id de correlação", async () => {
    const erro = {
      codigo: "erro_interno",
      mensagem: "Erro interno.",
      id_correlacao: "9380a0cc-0df5-4870-89f1-07ea57789f58",
    };

    await expect(buscarPerfil("https://api.x", "abc", json(erro, 500))).rejects.toMatchObject({
      status: 500,
      codigo: "erro_interno",
      idCorrelacao: "9380a0cc-0df5-4870-89f1-07ea57789f58",
    });
  });

  it("resposta fora do contrato não passa", async () => {
    await expect(
      buscarPerfil("https://api.x", "abc", json({ usuario: null })),
    ).rejects.toMatchObject({ codigo: "resposta_invalida" });
  });

  it("API inacessível vira erro legível", async () => {
    const semRede = vi.fn<typeof fetch>(async () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(buscarPerfil("https://api.x", "abc", semRede)).rejects.toBeInstanceOf(ErroDaApi);
  });
});
