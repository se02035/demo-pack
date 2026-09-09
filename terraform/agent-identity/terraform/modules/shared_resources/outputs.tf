output "secret_id" {
  description = "Secret Manager secret ID (not the full resource name)."
  value       = google_secret_manager_secret.demo.secret_id
}

output "secret_name" {
  description = "Full Secret Manager secret resource name."
  value       = google_secret_manager_secret.demo.name
}

output "secret_version_resource" {
  description = "projects/.../secrets/.../versions/latest accessor used by the agent."
  value       = "${google_secret_manager_secret.demo.name}/versions/latest"
}

output "set_proof_secret_id" {
  description = "Secret ID bound only to principalSets (inherit demo)."
  value       = google_secret_manager_secret.set_proof.secret_id
}

output "set_proof_secret_version_resource" {
  description = "projects/.../secrets/tf-agentid-set-proof/versions/latest"
  value       = "${google_secret_manager_secret.set_proof.name}/versions/latest"
}

output "broadcast_secret_id" {
  description = "Broadcast secret ID, or empty until enable_principalset_mutate."
  value       = var.enable_principalset_mutate ? google_secret_manager_secret.broadcast[0].secret_id : ""
}

output "broadcast_secret_version_resource" {
  description = "Broadcast secret version resource, or empty until enable_principalset_mutate."
  value       = var.enable_principalset_mutate ? "${google_secret_manager_secret.broadcast[0].name}/versions/latest" : ""
}

output "bucket_name" {
  description = "Demo GCS bucket name."
  value       = google_storage_bucket.demo.name
}

output "object_name" {
  description = "Demo GCS object name."
  value       = google_storage_bucket_object.demo.name
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository ID."
  value       = google_artifact_registry_repository.adk.repository_id
}

output "adk_image_uri" {
  description = "Suggested ADK image URI after an out-of-band Cloud Build."
  value       = local.adk_image_uri
}
