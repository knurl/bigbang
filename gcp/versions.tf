terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.53.1"
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

  required_version = "~> 1.4.5"
}
