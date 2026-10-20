import "@fontsource-variable/fraunces";
import "@fontsource-variable/inter";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

const raiz = document.getElementById("root");
if (!raiz) throw new Error("Elemento #root ausente em index.html.");

createRoot(raiz).render(
  <StrictMode>
    <p className="p-10 font-display text-4xl">FisioAgenda</p>
  </StrictMode>,
);
