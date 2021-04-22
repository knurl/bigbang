terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 2.52.0"
    }

    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0.3"
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

  required_version = "~> 0.14.0"
}

provider "azurerm" {
  features {}
}
