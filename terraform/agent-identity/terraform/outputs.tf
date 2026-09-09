output "project_id" {
  description = "GCP project ID."
  value       = var.project_id
}

output "project_number" {
  description = "GCP project number."
  value       = local.project_number
}

output "org_id" {
  description = "Organization ID used in the Agent Identity trust domain."
  value       = local.org_id
}

output "trust_domain" {
  description = "Agent Identity trust domain (no principal:// prefix)."
  value       = local.trust_domain
}

output "reasoning_engine_id" {
  description = "Server-generated Reasoning Engine ID (first / hello pair)."
  value       = module.agent_runtime.reasoning_engine_id
}

output "reasoning_engine_name" {
  description = "Full Reasoning Engine resource name (first / hello pair)."
  value       = module.agent_runtime.reasoning_engine_name
}

output "effective_identity" {
  description = "Agent Runtime effectiveIdentity from the API (no principal:// prefix)."
  value       = module.agent_runtime.effective_identity
}

output "agent_runtime_principal" {
  description = "IAM member string for the first Reasoning Engine."
  value       = module.agent_identity.agent_runtime_principal
}

output "cloud_run_principal" {
  description = "Predicted IAM member string for the first Cloud Run service (bound in step 1)."
  value       = module.agent_identity.cloud_run_principal
}

output "agent_runtime_principal_set" {
  description = "IAM member string for all Agent Runtime agents in the project."
  value       = module.agent_identity.agent_runtime_principal_set
}

output "cloud_run_principal_set" {
  description = "IAM member string for all Cloud Run agents in the project."
  value       = module.agent_identity.cloud_run_principal_set
}

output "secret_id" {
  description = "Per-principal demo Secret Manager secret ID."
  value       = module.shared_resources.secret_id
}

output "secret_version_resource" {
  description = "Full resource name of the per-principal demo secret version (latest)."
  value       = module.shared_resources.secret_version_resource
}

output "set_proof_secret_id" {
  description = "principalSet inherit-demo secret ID."
  value       = module.shared_resources.set_proof_secret_id
}

output "set_proof_secret_version_resource" {
  description = "principalSet inherit-demo secret version resource."
  value       = module.shared_resources.set_proof_secret_version_resource
}

output "broadcast_secret_id" {
  description = "principalSet mutate-demo secret ID (empty until enable_principalset_mutate)."
  value       = module.shared_resources.broadcast_secret_id
}

output "broadcast_secret_version_resource" {
  description = "principalSet mutate-demo secret version resource (empty until enable_principalset_mutate)."
  value       = module.shared_resources.broadcast_secret_version_resource
}

output "bucket_name" {
  description = "Demo GCS bucket name (uniform bucket-level access)."
  value       = module.shared_resources.bucket_name
}

output "object_name" {
  description = "Demo GCS object name."
  value       = module.shared_resources.object_name
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository for the optional ADK Cloud Run image."
  value       = module.shared_resources.artifact_registry_repository
}

output "adk_image_uri" {
  description = "Suggested ADK image URI after gcloud builds submit (not built by Terraform)."
  value       = module.shared_resources.adk_image_uri
}

output "cloud_run_url" {
  description = "First Cloud Run service URL. Empty until enable_cloud_run=true."
  value       = module.cloud_run_agent.service_url
}

output "set_proof_reasoning_engine_id" {
  description = "Second Reasoning Engine ID (empty until enable_principalset_agents)."
  value       = var.enable_principalset_agents ? module.set_proof_runtime[0].reasoning_engine_id : ""
}

output "set_proof_effective_identity" {
  description = "Second Reasoning Engine effectiveIdentity (empty until enable_principalset_agents)."
  value       = var.enable_principalset_agents ? module.set_proof_runtime[0].effective_identity : ""
}

output "set_proof_cloud_run_url" {
  description = "Second Cloud Run URL (empty until enable_principalset_agents)."
  value       = var.enable_principalset_agents ? module.set_proof_cloud_run[0].service_url : ""
}

output "set_proof_cloud_run_service_name" {
  description = "Second Cloud Run service name."
  value       = var.set_proof_cloud_run_service_name
}

output "agent_model" {
  description = "Gemini model ID injected as DEMO_MODEL on Agent Runtime and Cloud Run."
  value       = var.agent_model
}
