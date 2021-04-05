terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 2.50.0"
    }

    kubernetes = {
      source = "hashicorp/kubernetes"
      version = ">= 2.0.2"
    }

    random = {
      source  = "hashicorp/random"
      version = ">= 3.0.0"
    }

    local = {
      source  = "hashicorp/local"
      version = ">= 2.0.0"
    }

    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }

  required_version = ">= 0.14"
}

provider "azurerm" {
  features {}
}
