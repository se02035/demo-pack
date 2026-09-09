terraform {
  required_version = "= 1.15.4"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.1.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "= 2.8.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
