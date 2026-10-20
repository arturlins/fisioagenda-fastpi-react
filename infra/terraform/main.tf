locals {
  rotulos = { projeto = "fisioagenda", gerenciado_por = "terraform" }

  # O IP existe antes do servidor (hcloud_primary_ip), então o cloud-init já
  # nasce sabendo o próprio domínio. Destruído junto: IP novo a cada apply.
  dominio_base = "${replace(hcloud_primary_ip.ipv4.ip_address, ".", "-")}.sslip.io"

  # Mesmo realm do desenvolvimento, menos o client de testes: ele concede token
  # por senha (Direct Access Grant) e não tem lugar num servidor na internet.
  realm_base = jsondecode(file("${path.module}/../../keycloak/realm-fisioagenda.json"))
  realm_producao = merge(local.realm_base, {
    clients = [for client in local.realm_base.clients : client if client.clientId != "fisioagenda-testes"]
  })

  env = <<-EOT
    DOMINIO_BASE=${local.dominio_base}
    TLS_MODO=${var.acme_email}
    REGISTRO=${var.registro}
    VERSAO_IMAGENS=${var.versao_imagens}
    POSTGRES_SUPERUSER_PASSWORD=${random_password.segredo["postgres_superusuario"].result}
    APP_DB_USER=fisioagenda_app
    APP_DB_PASSWORD=${random_password.segredo["banco_aplicacao"].result}
    KEYCLOAK_DB_USER=keycloak
    KEYCLOAK_DB_PASSWORD=${random_password.segredo["banco_keycloak"].result}
    KEYCLOAK_ADMIN_USER=admin
    KEYCLOAK_ADMIN_PASSWORD=${random_password.segredo["keycloak_admin"].result}
    KEYCLOAK_BACKEND_CLIENT_SECRET=${random_password.segredo["keycloak_backend"].result}
    SEMEAR_SENHA=${random_password.segredo["demonstracao"].result}
  EOT
}

# Alfanuméricos: entram em DSN e em variável de ambiente sem precisar de escape.
resource "random_password" "segredo" {
  for_each = toset([
    "postgres_superusuario",
    "banco_aplicacao",
    "banco_keycloak",
    "keycloak_admin",
    "keycloak_backend",
    "demonstracao",
  ])

  length  = 32
  special = false
}

resource "hcloud_ssh_key" "operador" {
  name       = "fisioagenda-operador"
  public_key = trimspace(file(pathexpand(var.ssh_chave_publica_arquivo)))
  labels     = local.rotulos
}

resource "hcloud_primary_ip" "ipv4" {
  name        = "fisioagenda-ipv4"
  type        = "ipv4"
  location    = var.localizacao
  auto_delete = false
  labels      = local.rotulos
}

resource "hcloud_firewall" "fisioagenda" {
  name   = "fisioagenda"
  labels = local.rotulos

  rule {
    description = "HTTP: desafio ACME e redirecionamento para HTTPS"
    direction   = "in"
    protocol    = "tcp"
    port        = "80"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "HTTPS"
    direction   = "in"
    protocol    = "tcp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "HTTP/3"
    direction   = "in"
    protocol    = "udp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "SSH só do operador"
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    source_ips  = [var.ssh_permitido_cidr]
  }

  rule {
    description = "ICMP"
    direction   = "in"
    protocol    = "icmp"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_server" "fisioagenda" {
  name         = "fisioagenda"
  server_type  = var.tipo_servidor
  image        = var.imagem_so
  location     = var.localizacao
  ssh_keys     = [hcloud_ssh_key.operador.id]
  firewall_ids = [hcloud_firewall.fisioagenda.id]
  labels       = local.rotulos

  user_data = templatefile("${path.module}/templates/cloud-init.yaml.tftpl", {
    chave_ssh = hcloud_ssh_key.operador.public_key
    compose   = base64encode(file("${path.module}/../compose.prod.yaml"))
    env       = base64encode(local.env)
    realm     = base64encode(jsonencode(local.realm_producao))
    db_init   = base64encode(file("${path.module}/../../db/init/01-bancos-e-extensoes.sh"))
  })

  public_net {
    ipv4_enabled = true
    ipv4         = hcloud_primary_ip.ipv4.id
    ipv6_enabled = false
  }
}
