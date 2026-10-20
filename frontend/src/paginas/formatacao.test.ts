import { describe, expect, it } from "vitest";
import {
  formatarRestante,
  primeiroNome,
  resumoDoAcesso,
  rotuloDoPapel,
  saudacao,
} from "./formatacao";

describe("formatação do painel", () => {
  it.each([
    [5, "Bom dia"],
    [11, "Bom dia"],
    [12, "Boa tarde"],
    [17, "Boa tarde"],
    [18, "Boa noite"],
    [2, "Boa noite"],
  ])("às %ih a saudação é %s", (hora, esperado) => {
    expect(saudacao(hora)).toBe(esperado);
  });

  it("usa o primeiro nome", () => {
    expect(primeiroNome("  Bruno Carvalho Lima ")).toBe("Bruno");
  });

  it("rotula os papéis", () => {
    expect(rotuloDoPapel("administrador")).toBe("Administrador");
    expect(rotuloDoPapel("comum")).toBe("Comum");
  });

  it("resume o acesso", () => {
    expect(resumoDoAcesso(true, 0)).toMatch(/todas as clínicas/);
    expect(resumoDoAcesso(false, 1)).toBe("Você atua em 1 clínica desta conta.");
    expect(resumoDoAcesso(false, 2)).toBe("Você atua em 2 clínicas desta conta.");
    expect(resumoDoAcesso(false, 0)).toMatch(/nenhuma clínica/);
  });

  it("formata o tempo restante do token", () => {
    expect(formatarRestante(905)).toBe("15:05");
    expect(formatarRestante(59)).toBe("00:59");
    expect(formatarRestante(0)).toBe("renovando…");
    expect(formatarRestante(-3)).toBe("renovando…");
  });
});
