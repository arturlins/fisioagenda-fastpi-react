import { z } from "zod";

// A mesma imagem roda em qualquer ambiente: os endereços chegam em tempo de
// execução por /config.json, que o Caddy monta a partir do domínio do servidor.
const esquema = z.object({
  keycloakUrl: z.url(),
  realm: z.string().min(1),
  clientId: z.string().min(1),
  apiUrl: z.url(),
});

export type Configuracao = z.infer<typeof esquema>;

export class ConfiguracaoInvalidaError extends Error {
  override name = "ConfiguracaoInvalidaError";
}

const semBarraFinal = (url: string) => url.replace(/\/+$/, "");

export async function carregarConfiguracao(buscar: typeof fetch = fetch): Promise<Configuracao> {
  let resposta: Response;
  try {
    resposta = await buscar("/config.json", { cache: "no-store" });
  } catch {
    throw new ConfiguracaoInvalidaError("Não foi possível obter /config.json.");
  }
  if (!resposta.ok) {
    throw new ConfiguracaoInvalidaError(`/config.json respondeu ${resposta.status}.`);
  }

  let corpo: unknown;
  try {
    corpo = await resposta.json();
  } catch {
    throw new ConfiguracaoInvalidaError("/config.json não é JSON — o servidor não o publicou.");
  }

  const resultado = esquema.safeParse(corpo);
  if (!resultado.success) {
    const campos = resultado.error.issues.map((problema) => problema.path.join(".")).join(", ");
    throw new ConfiguracaoInvalidaError(`/config.json com campos inválidos: ${campos}.`);
  }

  return {
    ...resultado.data,
    keycloakUrl: semBarraFinal(resultado.data.keycloakUrl),
    apiUrl: semBarraFinal(resultado.data.apiUrl),
  };
}
