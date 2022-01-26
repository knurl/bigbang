terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 2.90.0"
    }

    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.7.1"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.1.0"
    }

    local = {
      source  = "hashicorp/local"
      version = "~> 2.1.0"
    }
  }

  required_version = "~> 1.1.4"
}

provider "azurerm" {
  features {}
}
