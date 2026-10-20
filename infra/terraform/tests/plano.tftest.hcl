# Testa a lógica do módulo sem criar nada: o provider da Hetzner é simulado.
mock_provider "hcloud" {
  mock_resource "hcloud_primary_ip" {
    defaults = { id = "101", ip_address = "203.0.113.10" }
  }
  mock_resource "hcloud_firewall" {
    defaults = { id = "102" }
  }
  mock_resource "hcloud_ssh_key" {
    defaults = { id = "103" }
  }
  mock_resource "hcloud_server" {
    defaults = { id = "104" }
  }
}

variables {
  versao_imagens            = "0123456789abcdef0123456789abcdef01234567"
  ssh_chave_publica_arquivo = "tests/fixtures/chave_teste.pub"
  ssh_permitido_cidr        = "198.51.100.7/32"
  acme_email                = "ci@exemplo.com"
}

run "enderecos_derivam_do_ip" {
  command = apply

  assert {
    condition     = output.url_app == "https://app.203-0-113-10.sslip.io"
    error_message = "url_app não deriva do IP: ${output.url_app}"
  }
  assert {
    condition     = output.url_documentacao == "https://api.203-0-113-10.sslip.io/docs"
    error_message = "url_documentacao errada: ${output.url_documentacao}"
  }
  assert {
    condition     = output.url_keycloak == "https://auth.203-0-113-10.sslip.io/realms/fisioagenda"
    error_message = "url_keycloak errada: ${output.url_keycloak}"
  }
}

run "realm_de_producao_sem_client_de_testes" {
  command = apply

  assert {
    condition     = !contains(output.clients_do_realm, "fisioagenda-testes")
    error_message = "O client de testes (Direct Access Grant) vazou para produção."
  }
  assert {
    condition     = contains(output.clients_do_realm, "fisioagenda-web") && contains(output.clients_do_realm, "fisioagenda-backend")
    error_message = "Clients de produção ausentes: ${jsonencode(output.clients_do_realm)}"
  }
}

run "versao_latest_e_recusada" {
  command = plan

  variables {
    versao_imagens = "latest"
  }

  expect_failures = [var.versao_imagens]
}

run "ssh_aberto_ao_mundo_e_recusado" {
  command = plan

  variables {
    ssh_permitido_cidr = "0.0.0.0/0"
  }

  expect_failures = [var.ssh_permitido_cidr]
}
