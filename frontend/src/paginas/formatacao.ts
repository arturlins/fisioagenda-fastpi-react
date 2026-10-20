import type { Papel } from "../api/perfil";

export function saudacao(hora: number): string {
  if (hora >= 5 && hora < 12) return "Bom dia";
  if (hora >= 12 && hora < 18) return "Boa tarde";
  return "Boa noite";
}

export function primeiroNome(nome: string): string {
  return nome.trim().split(/\s+/)[0] ?? nome;
}

const ROTULOS: Record<Papel, string> = { administrador: "Administrador", comum: "Comum" };

export function rotuloDoPapel(papel: Papel): string {
  return ROTULOS[papel];
}

export function resumoDoAcesso(responsavelPelaConta: boolean, clinicas: number): string {
  if (responsavelPelaConta) return "Responsável pela conta — administra todas as clínicas.";
  if (clinicas === 0) return "Você ainda não atua em nenhuma clínica desta conta.";
  return `Você atua em ${clinicas} ${clinicas === 1 ? "clínica" : "clínicas"} desta conta.`;
}

export function formatarRestante(segundos: number): string {
  if (segundos <= 0) return "renovando…";
  const minutos = Math.floor(segundos / 60);
  const resto = segundos % 60;
  return `${String(minutos).padStart(2, "0")}:${String(resto).padStart(2, "0")}`;
}
