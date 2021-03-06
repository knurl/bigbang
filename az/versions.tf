terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 2.77.0"
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

  required_version = "~> 1.0.5"
}

provider "azurerm" {
  features {}
}
