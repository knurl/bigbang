terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.25.0"
    }

    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.29.0"
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

  required_version = "~> 1.5.7"
}
