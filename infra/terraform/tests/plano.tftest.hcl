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

# O user_data é legível de dentro do servidor (serviço de metadados) e imutável
# durante a vida dele: não pode carregar segredo nenhum. Os arquivos vão em
# base64, então as asserções decodificam cada um antes de procurar.
run "user_data_sem_segredo" {
  command = apply

  assert {
    condition = strcontains(
      base64decode(regex("path: /opt/fisioagenda/[.]env[.]base\\n\\s+encoding: b64\\n\\s+content: ([A-Za-z0-9+/=]+)", hcloud_server.fisioagenda.user_data)[0]),
      "DOMINIO_BASE=203-0-113-10.sslip.io\n"
    )
    error_message = "O .env.base não traz o domínio derivado do IP."
  }
  assert {
    condition = alltrue([
      for proibido in ["PASSWORD", "SECRET", "SEMEAR_SENHA"] : !strcontains(
        base64decode(regex("path: /opt/fisioagenda/[.]env[.]base\\n\\s+encoding: b64\\n\\s+content: ([A-Za-z0-9+/=]+)", hcloud_server.fisioagenda.user_data)[0]),
        proibido
      )
    ])
    error_message = "O .env.base carrega chave de segredo."
  }
  assert {
    # Nenhum arquivo entregue atribui valor literal a um segredo, em nenhum dos
    # formatos que viajam: NOME=valor (.env, shell), "secret": "valor" (JSON do
    # realm), CHAVE: valor (YAML do compose), PASSWORD 'valor' (SQL do db_init).
    # Referências como ${APP_DB_PASSWORD} não casam: depois do separador vem "$".
    condition = alltrue([
      for grupo in regexall("content: ([A-Za-z0-9+/=]+)", hcloud_server.fisioagenda.user_data) :
      !can(regex("(?i)(password|secret|senha)\"?(\\s*[:=]\\s*['\"]?|\\s+['\"])[A-Za-z0-9]", base64decode(grupo[0])))
    ])
    error_message = "Algum arquivo do user_data atribui valor literal a um segredo."
  }
  assert {
    condition     = !can(regex("(?i)(password|secret|senha)\"?(\\s*[:=]\\s*['\"]?|\\s+['\"])[A-Za-z0-9]", hcloud_server.fisioagenda.user_data))
    error_message = "O user_data atribui valor literal a um segredo."
  }
  assert {
    # Todo client do realm de produção com secret o recebe por placeholder,
    # resolvido pelo Keycloak a partir do .env gerado no servidor.
    condition = alltrue([
      for client in jsondecode(base64decode(regex("path: /opt/fisioagenda/keycloak/realm-fisioagenda[.]json\\n\\s+encoding: b64\\n\\s+content: ([A-Za-z0-9+/=]+)", hcloud_server.fisioagenda.user_data)[0])).clients :
      !can(client.secret) || startswith(client.secret, "$${")
    ])
    error_message = "Um client do realm de produção traz secret literal em vez de placeholder."
  }
  assert {
    # Sem isto, um regex que não casa nada faria as duas asserções acima passarem no vazio.
    condition     = length(regexall("content: ([A-Za-z0-9+/=]+)", hcloud_server.fisioagenda.user_data)) == 7
    error_message = "Esperados 7 arquivos no write_files: o teste não está lendo o que o servidor recebe."
  }
  assert {
    condition     = output.comando_senha_demonstracao == "ssh deploy@203.0.113.10 \"sudo sed -n 's/^SEMEAR_SENHA=//p' /opt/fisioagenda/.env\""
    error_message = "Comando da senha errado: ${output.comando_senha_demonstracao}"
  }
}
