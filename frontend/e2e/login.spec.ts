import { expect, type Page, test } from "@playwright/test";

const email = process.env.E2E_EMAIL ?? "bruno@clinicamovimento.com.br";
const senha = process.env.E2E_SENHA ?? "FisioAgenda#2026";

async function entrar(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page).toHaveURL(/\/realms\/fisioagenda\/protocol\/openid-connect\/auth/);
  await page.locator("#username").fill(email);
  await page.locator("#password").fill(senha);
  await page.locator("#kc-login").click();
  await expect(page).toHaveURL(/\/inicio$/);
}

test("login pelo Keycloak leva ao painel com o papel por clínica", async ({ page }) => {
  await entrar(page);

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Bruno");
  await expect(page.getByRole("listitem", { name: "Unidade Centro" })).toContainText(
    "Administrador",
  );
  await expect(page.getByRole("listitem", { name: "Unidade Farol" })).toContainText("Comum");
});

test("recarregar mantém a sessão sem senha e sem token em storage", async ({ page }) => {
  await entrar(page);

  await page.reload();

  await expect(page).toHaveURL(/\/inicio$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Bruno");
  const armazenado = await page.evaluate(() =>
    [...Object.values(sessionStorage), ...Object.values(localStorage)].join(" "),
  );
  expect(armazenado).not.toMatch(/eyJ[\w-]+\.[\w-]+\./);
});

test("sair encerra a sessão no Keycloak", async ({ page }) => {
  await entrar(page);

  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.goto("/inicio");
  await expect(page.locator("#username")).toBeVisible();
});
