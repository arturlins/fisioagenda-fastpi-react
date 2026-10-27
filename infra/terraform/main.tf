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

  # Só o que não é segredo. As seis senhas nascem no servidor, no primeiro boot
  # (infra/servidor/gerar-env.sh): o Terraform não as gera nem as conhece, então
  # elas não ficam no state nem no user_data — que qualquer processo da máquina
  # lê no serviço de metadados.
  env_base = <<-EOT
    DOMINIO_BASE=${local.dominio_base}
    TLS_MODO=${var.acme_email}
    REGISTRO=${var.registro}
    VERSAO_IMAGENS=${var.versao_imagens}
    APP_DB_USER=fisioagenda_app
    KEYCLOAK_DB_USER=keycloak
    KEYCLOAK_ADMIN_USER=admin
  EOT
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
    env_base  = base64encode(local.env_base)
    gerar_env = base64encode(file("${path.module}/../servidor/gerar-env.sh"))
    realm     = base64encode(jsonencode(local.realm_producao))
    db_init   = base64encode(file("${path.module}/../../db/init/01-bancos-e-extensoes.sh"))
  })

  public_net {
    ipv4_enabled = true
    ipv4         = hcloud_primary_ip.ipv4.id
    ipv6_enabled = false
  }
}
