terraform {
  required_version = "= 1.15.4"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.1.0"
    }
  }
}
