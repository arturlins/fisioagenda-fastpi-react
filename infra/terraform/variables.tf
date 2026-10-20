variable "versao_imagens" {
  description = "SHA completo do commit do main cujas imagens o servidor vai rodar."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.versao_imagens))
    error_message = "Use o SHA completo (40 caracteres hexadecimais). Nunca 'latest'."
  }
}

variable "registro" {
  description = "Prefixo das imagens no registry."
  type        = string
  default     = "ghcr.io/arturlins"
}

variable "ssh_chave_publica_arquivo" {
  description = "Caminho da chave pública SSH do operador."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "ssh_permitido_cidr" {
  description = "Único endereço autorizado na porta 22, ex.: 203.0.113.7/32."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_permitido_cidr, 0)) && !contains(["0.0.0.0/0", "::/0"], var.ssh_permitido_cidr)
    error_message = "Informe um CIDR válido e restrito — SSH aberto ao mundo não é aceito."
  }
}

variable "acme_email" {
  description = "E-mail de contato do Let's Encrypt."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.acme_email))
    error_message = "Informe um e-mail válido."
  }
}

variable "tipo_servidor" {
  description = "Tipo de servidor da Hetzner. Alternativa se indisponível: cpx32."
  type        = string
  default     = "cpx22"
}

variable "localizacao" {
  description = "Local da Hetzner na UE."
  type        = string
  default     = "nbg1"

  validation {
    # Onde a linha CPX é oferecida na UE.
    condition     = contains(["nbg1", "hel1"], var.localizacao)
    error_message = "Use nbg1 ou hel1."
  }
}

variable "imagem_so" {
  description = "Imagem do sistema operacional."
  type        = string
  default     = "ubuntu-24.04"
}
