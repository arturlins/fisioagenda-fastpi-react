import { defineConfig, devices } from "@playwright/test";

// Sem E2E_BASE_URL: pilha local de desenvolvimento, com o Vite subido aqui.
// Com ela: ensaio local ou o servidor implantado.
const alvo = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: alvo ?? "http://localhost:5173",
    ignoreHTTPSErrors: process.env.E2E_IGNORAR_TLS === "1",
    trace: "retain-on-failure",
    locale: "pt-BR",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  ...(alvo
    ? {}
    : {
        webServer: {
          command: "bun run dev",
          url: "http://localhost:5173",
          reuseExistingServer: true,
        },
      }),
});
