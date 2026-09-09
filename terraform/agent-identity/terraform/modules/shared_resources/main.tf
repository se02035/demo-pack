data "google_project" "current" {
  project_id = var.project_id
}

locals {
  apis = toset([
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "apphub.googleapis.com",
    "agentregistry.googleapis.com",
    "agentidentity.googleapis.com",
  ])

  bucket_name   = "tf-agentid-demo-${data.google_project.current.number}"
  object_name   = "hello.txt"
  secret_id     = "tf-agentid-demo"
  ar_repository = "tf-agentid"
  adk_image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/${local.ar_repository}/hello-adk:latest"
}

resource "google_project_service" "apis" {
  for_each = local.apis

  project = var.project_id
  service = each.value
  # This project already had these APIs enabled for other workloads. Destroy
  # removes demo resources (engine, Cloud Run, secret, bucket, AR) but leaves
  # APIs on. Set true only in a throwaway project.
  disable_on_destroy = false
}

resource "google_secret_manager_secret" "demo" {
  project   = var.project_id
  secret_id = local.secret_id

  replication {
    auto {}
  }

  labels = {
    demo = "agent-identity"
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "demo" {
  secret      = google_secret_manager_secret.demo.id
  secret_data = "agent-identity-proof"
}

# Bound only to principalSets (not individual principal:// members).
resource "google_secret_manager_secret" "set_proof" {
  project   = var.project_id
  secret_id = "tf-agentid-set-proof"

  replication {
    auto {}
  }

  labels = {
    demo = "agent-identity"
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "set_proof" {
  secret      = google_secret_manager_secret.set_proof.id
  secret_data = "principalset-membership-proof"
}

# Created in concept 3b. Bound only to principalSets after both agent pairs exist.
resource "google_secret_manager_secret" "broadcast" {
  count = var.enable_principalset_mutate ? 1 : 0

  project   = var.project_id
  secret_id = "tf-agentid-set-broadcast"

  replication {
    auto {}
  }

  labels = {
    demo = "agent-identity"
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "broadcast" {
  count = var.enable_principalset_mutate ? 1 : 0

  secret      = google_secret_manager_secret.broadcast[0].id
  secret_data = "principalset-broadcast-proof"
}

resource "google_storage_bucket" "demo" {
  name                        = local.bucket_name
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  labels = {
    demo = "agent-identity"
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_object" "demo" {
  name    = local.object_name
  bucket  = google_storage_bucket.demo.name
  content = "hello from gcs (agent identity demo)\n"
}

resource "google_artifact_registry_repository" "adk" {
  project       = var.project_id
  location      = var.region
  repository_id = local.ar_repository
  description   = "ADK Cloud Run images for the Agent Identity demo."
  format        = "DOCKER"

  labels = {
    demo = "agent-identity"
  }

  depends_on = [google_project_service.apis]
}

# Agent Runtime builds/pushes a source image then pulls it as this SA.
resource "google_project_iam_member" "reasoning_engine_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

  depends_on = [google_project_service.apis]
}
