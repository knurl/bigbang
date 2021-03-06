terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 3.59.0"
    }

    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.1.0"
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

provider "aws" {
  region = var.region
}
