import { createContext, type ReactNode, useContext } from "react";
import type { Configuracao } from "./config";

const Contexto = createContext<Configuracao | null>(null);

export function ConfiguracaoProvider({
  valor,
  children,
}: {
  valor: Configuracao;
  children: ReactNode;
}) {
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useConfiguracao(): Configuracao {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useConfiguracao fora de ConfiguracaoProvider.");
  return valor;
}
