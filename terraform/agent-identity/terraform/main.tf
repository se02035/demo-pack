data "google_project" "current" {
  project_id = var.project_id
}

data "archive_file" "agent" {
  type        = "tar.gz"
  source_dir  = "${path.module}/../agent"
  output_path = "${path.module}/.build/agent-runtime-source.tar.gz"
  excludes = [
    "Dockerfile",
    "cloudbuild.yaml",
    ".dockerignore",
    "main.py",
    "**/__pycache__/**",
    "**/*.pyc",
  ]
}

locals {
  # Prefer data.google_project.org_id when the API returns it. On folder-parented
  # projects it is often "", so coalesce falls through to var.org_id.
  org_id         = coalesce(data.google_project.current.org_id, var.org_id)
  project_number = data.google_project.current.number
  trust_domain   = "agents.global.org-${local.org_id}.system.id.goog"

  attach_agent_source = var.enable_agent_runtime_code || var.enable_principalset_agents

  # Evaluated at the root so filebase64 sees a plan-time archive (not deferred
  # behind module.shared_resources).
  agent_source_archive_b64 = local.attach_agent_source ? filebase64(data.archive_file.agent.output_path) : null

  extra_env = merge(
    {
      DEMO_SET_SECRET_RESOURCE = module.shared_resources.set_proof_secret_version_resource
    },
    var.enable_principalset_mutate ? {
      DEMO_SET_BROADCAST_RESOURCE = module.shared_resources.broadcast_secret_version_resource
    } : {},
  )
}

module "shared_resources" {
  source = "./modules/shared_resources"

  project_id                 = var.project_id
  region                     = var.region
  enable_principalset_mutate = var.enable_principalset_mutate
}

module "agent_runtime" {
  source = "./modules/agent_runtime"

  project_id                = var.project_id
  region                    = var.region
  display_name              = var.reasoning_engine_display_name
  enable_agent_runtime_code = var.enable_agent_runtime_code
  demo_secret_resource      = module.shared_resources.secret_version_resource
  demo_bucket_name          = module.shared_resources.bucket_name
  demo_object_name          = module.shared_resources.object_name
  source_archive_b64        = local.agent_source_archive_b64
  agent_model               = var.agent_model
  extra_env                 = local.extra_env

  depends_on = [module.shared_resources]
}

module "agent_identity" {
  source = "./modules/agent_identity"

  project_id                          = var.project_id
  org_id                              = local.org_id
  project_number                      = local.project_number
  region                              = var.region
  cloud_run_service_name              = var.cloud_run_service_name
  reasoning_engine_effective_identity = module.agent_runtime.effective_identity
  secret_id                           = module.shared_resources.secret_id
  bucket_name                         = module.shared_resources.bucket_name
  set_proof_secret_id                 = module.shared_resources.set_proof_secret_id
  broadcast_secret_id                 = module.shared_resources.broadcast_secret_id

  depends_on = [module.agent_runtime]
}

module "cloud_run_agent" {
  source = "./modules/cloud_run_agent"

  project_id           = var.project_id
  region               = var.region
  enable_cloud_run     = var.enable_cloud_run
  service_name         = var.cloud_run_service_name
  image                = var.cloud_run_image
  demo_secret_resource = module.shared_resources.secret_version_resource
  demo_bucket_name     = module.shared_resources.bucket_name
  demo_object_name     = module.shared_resources.object_name
  agent_model          = var.agent_model
  extra_env            = local.extra_env

  # IAM for the predicted Cloud Run principal is bound in step 1. Do not wait
  # on the Reasoning Engine source update (it can take 10+ minutes).
  depends_on = [module.shared_resources]
}

module "set_proof_runtime" {
  count  = var.enable_principalset_agents ? 1 : 0
  source = "./modules/agent_runtime"

  project_id                = var.project_id
  region                    = var.region
  display_name              = var.set_proof_reasoning_engine_display_name
  enable_agent_runtime_code = true
  demo_secret_resource      = module.shared_resources.secret_version_resource
  demo_bucket_name          = module.shared_resources.bucket_name
  demo_object_name          = module.shared_resources.object_name
  source_archive_b64        = local.agent_source_archive_b64
  agent_model               = var.agent_model
  extra_env                 = local.extra_env

  depends_on = [module.shared_resources]
}

module "set_proof_cloud_run" {
  count  = var.enable_principalset_agents ? 1 : 0
  source = "./modules/cloud_run_agent"

  project_id           = var.project_id
  region               = var.region
  enable_cloud_run     = true
  service_name         = var.set_proof_cloud_run_service_name
  image                = module.shared_resources.adk_image_uri
  demo_secret_resource = module.shared_resources.secret_version_resource
  demo_bucket_name     = module.shared_resources.bucket_name
  demo_object_name     = module.shared_resources.object_name
  agent_model          = var.agent_model
  extra_env            = local.extra_env

  depends_on = [module.shared_resources]
}
