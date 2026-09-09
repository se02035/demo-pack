variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "org_id" {
  type        = string
  description = "Organization ID for the Agent Identity trust domain."
}

variable "project_number" {
  type        = string
  description = "Numeric project number used in SPIFFE resource paths."
}

variable "region" {
  type        = string
  description = "Region used in Cloud Run principal paths."
}

variable "cloud_run_service_name" {
  type        = string
  description = "Predicted Cloud Run service name (must match the later google_cloud_run_service)."
}

variable "reasoning_engine_effective_identity" {
  type        = string
  description = "spec.effective_identity from the stub Reasoning Engine (no principal:// prefix)."
}

variable "secret_id" {
  type        = string
  description = "Demo Secret Manager secret ID."
}

variable "bucket_name" {
  type        = string
  description = "Demo GCS bucket name."
}

variable "set_proof_secret_id" {
  type        = string
  description = "Secret ID bound only to principalSets (inherit demo)."
}

variable "broadcast_secret_id" {
  type        = string
  description = "Broadcast secret ID. Empty until enable_principalset_mutate."
  default     = ""
}
