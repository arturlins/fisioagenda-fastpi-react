import "@fontsource-variable/fraunces";
import "@fontsource-variable/inter";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Aplicacao } from "./aplicacao";
import { TelaErro } from "./componentes/telas";
import { carregarConfiguracao } from "./config";

const elemento = document.getElementById("root");
if (!elemento) throw new Error("Elemento #root ausente em index.html.");
const raiz = createRoot(elemento);

carregarConfiguracao().then(
  (config) =>
    raiz.render(
      <StrictMode>
        <Aplicacao config={config} />
      </StrictMode>,
    ),
  (erro: unknown) =>
    raiz.render(
      <TelaErro
        titulo="Configuração inválida"
        detalhe={erro instanceof Error ? erro.message : String(erro)}
      />,
    ),
);
