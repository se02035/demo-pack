output "trust_domain" {
  description = "Agent Identity trust domain (no principal:// prefix)."
  value       = local.trust_domain
}

output "agent_runtime_principal" {
  description = "IAM member for the stub Reasoning Engine."
  value       = local.agent_runtime_principal
}

output "cloud_run_principal" {
  description = "Predicted IAM member for the Cloud Run service."
  value       = local.cloud_run_principal
}

output "agent_runtime_principal_set" {
  description = "IAM member for all Agent Runtime agents in the project."
  value       = local.agent_runtime_principal_set
}

output "cloud_run_principal_set" {
  description = "IAM member for all Cloud Run agents in the project."
  value       = local.cloud_run_principal_set
}
