locals {
  trust_domain = "agents.global.org-${var.org_id}.system.id.goog"

  # API effectiveIdentity omits the principal:// prefix; IAM members must add it.
  agent_runtime_principal = "principal://${var.reasoning_engine_effective_identity}"

  cloud_run_principal = "principal://${local.trust_domain}/resources/run/projects/${var.project_number}/locations/${var.region}/services/${var.cloud_run_service_name}"

  agent_runtime_principal_set = "principalSet://${local.trust_domain}/attribute.platformContainer/aiplatform/projects/${var.project_number}"

  cloud_run_principal_set = "principalSet://${local.trust_domain}/attribute.platformContainer/run/projects/${var.project_number}"

  per_agent_secret_members = {
    agent_runtime = local.agent_runtime_principal
    cloud_run     = local.cloud_run_principal
  }

  agent_runtime_project_roles = toset([
    "roles/logging.logWriter",
    "roles/aiplatform.expressUser",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/browser",
  ])

  cloud_run_project_roles = toset([
    "roles/logging.logWriter",
    "roles/aiplatform.expressUser",
    "roles/serviceusage.serviceUsageConsumer",
  ])

  principal_set_members = {
    agent_runtime = local.agent_runtime_principal_set
    cloud_run     = local.cloud_run_principal_set
  }
}

# Proof: per-agent Secret Manager access (bound in step 1, including predicted Cloud Run).
resource "google_secret_manager_secret_iam_member" "demo" {
  for_each = local.per_agent_secret_members

  project   = var.project_id
  secret_id = var.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}

# Proof: per-agent GCS object access (non-legacy role).
resource "google_storage_bucket_iam_member" "demo" {
  for_each = local.per_agent_secret_members

  bucket = var.bucket_name
  role   = "roles/storage.objectViewer"
  member = each.value
}

# Baseline Agent Runtime principalSet (additive; already present on this project).
resource "google_project_iam_member" "agent_runtime_set" {
  for_each = local.agent_runtime_project_roles

  project = var.project_id
  role    = each.value
  member  = local.agent_runtime_principal_set
}

# Cloud Run agent identities are not in the aiplatform principalSet.
resource "google_project_iam_member" "cloud_run_set" {
  for_each = local.cloud_run_project_roles

  project = var.project_id
  role    = each.value
  member  = local.cloud_run_principal_set
}

resource "google_project_iam_member" "cloud_run_principal" {
  for_each = local.cloud_run_project_roles

  project = var.project_id
  role    = each.value
  member  = local.cloud_run_principal
}

# Inherit demo: both platform principalSets, no individual principal:// members.
resource "google_secret_manager_secret_iam_member" "set_proof" {
  for_each = local.principal_set_members

  project   = var.project_id
  secret_id = var.set_proof_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}

# Mutate demo: same sets, created after both agent pairs exist.
resource "google_secret_manager_secret_iam_member" "broadcast" {
  for_each = var.broadcast_secret_id != "" ? local.principal_set_members : {}

  project   = var.project_id
  secret_id = var.broadcast_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}
