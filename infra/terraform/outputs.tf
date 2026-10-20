output "url_app" {
  description = "Aplicação."
  value       = "https://app.${local.dominio_base}"
}

output "url_documentacao" {
  description = "Swagger da API."
  value       = "https://api.${local.dominio_base}/docs"
}

output "url_keycloak" {
  description = "Emissor dos tokens."
  value       = "https://auth.${local.dominio_base}/realms/fisioagenda"
}

output "dominio_base" {
  description = "Argumento do smoke test."
  value       = local.dominio_base
}

output "ip" {
  value = hcloud_primary_ip.ipv4.ip_address
}

output "ssh" {
  value = "ssh deploy@${hcloud_primary_ip.ipv4.ip_address}"
}

output "clients_do_realm" {
  description = "Clients importados em produção — o de testes não pode aparecer."
  value       = [for client in local.realm_producao.clients : client.clientId]
}

output "usuarios_demonstracao" {
  value = [
    "ana@clinicamovimento.com.br (responsável pela conta)",
    "bruno@clinicamovimento.com.br (admin da Centro, comum na Farol)",
    "carla@clinicamovimento.com.br",
    "diego@clinicamovimento.com.br",
  ]
}

output "senha_demonstracao" {
  description = "Senha dos usuários de demonstração: terraform output -raw senha_demonstracao"
  value       = random_password.segredo["demonstracao"].result
  sensitive   = true
}
