import { z } from "zod";

const vinculoEsquema = z.object({
  clinica_public_id: z.uuid(),
  clinica_nome: z.string(),
  papel: z.enum(["administrador", "comum"]),
  ativo: z.boolean(),
});

// Espelha PerfilResponse da API (GET /api/v1/auth/eu); só os campos usados.
const perfilEsquema = z.object({
  usuario: z.object({
    public_id: z.uuid(),
    nome: z.string(),
    email: z.string(),
    dono_da_conta: z.boolean(),
    e_profissional: z.boolean(),
    especialidade: z.string().nullable(),
  }),
  vinculos: z.array(vinculoEsquema),
});

const erroEsquema = z.object({
  codigo: z.string(),
  mensagem: z.string(),
  id_correlacao: z.string().nullable(),
});

export type Perfil = z.infer<typeof perfilEsquema>;
export type Papel = z.infer<typeof vinculoEsquema>["papel"];

export class NaoAutenticadoError extends Error {
  override name = "NaoAutenticadoError";
}

export class ErroDaApi extends Error {
  override name = "ErroDaApi";

  constructor(
    readonly status: number,
    readonly codigo: string,
    readonly idCorrelacao: string | null,
    mensagem: string,
  ) {
    super(mensagem);
  }
}

export async function buscarPerfil(
  apiUrl: string,
  token: string,
  buscar: typeof fetch = fetch,
): Promise<Perfil> {
  let resposta: Response;
  try {
    resposta = await buscar(`${apiUrl}/api/v1/auth/eu`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    });
  } catch {
    throw new ErroDaApi(0, "rede_indisponivel", null, "Não foi possível falar com a API.");
  }

  if (resposta.status === 401) throw new NaoAutenticadoError("Sessão expirada.");

  const corpo: unknown = await resposta.json().catch(() => null);

  if (!resposta.ok) {
    const erro = erroEsquema.safeParse(corpo);
    if (erro.success) {
      throw new ErroDaApi(
        resposta.status,
        erro.data.codigo,
        erro.data.id_correlacao,
        erro.data.mensagem,
      );
    }
    throw new ErroDaApi(
      resposta.status,
      "erro_desconhecido",
      null,
      `A API respondeu ${resposta.status}.`,
    );
  }

  const perfil = perfilEsquema.safeParse(corpo);
  if (!perfil.success) {
    throw new ErroDaApi(
      resposta.status,
      "resposta_invalida",
      null,
      "Resposta da API fora do contrato.",
    );
  }
  return perfil.data;
}
