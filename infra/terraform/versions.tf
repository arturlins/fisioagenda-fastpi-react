terraform {
  required_version = ">= 1.9"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.70"
    }
  }
}

# O token vem de HCLOUD_TOKEN, nunca de arquivo.
provider "hcloud" {}
