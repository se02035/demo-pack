variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "Region for the Reasoning Engine."
}

variable "display_name" {
  type        = string
  description = "Display name for the Reasoning Engine (same resource in both steps)."
}

variable "enable_agent_runtime_code" {
  type        = bool
  description = "When true, attach ADK source_code_spec to this engine."
}

variable "demo_secret_resource" {
  type        = string
  description = "projects/.../secrets/.../versions/latest for the demo secret."
}

variable "demo_bucket_name" {
  type        = string
  description = "Demo GCS bucket name."
}

variable "demo_object_name" {
  type        = string
  description = "Demo GCS object name."
}

variable "source_archive_b64" {
  type        = string
  description = "Base64-encoded ADK source tarball. Null when enable_agent_runtime_code is false."
  default     = null
  sensitive   = true
}

variable "agent_model" {
  type        = string
  description = "Gemini model ID injected as DEMO_MODEL. Changing this does not require a new source archive."
}

variable "extra_env" {
  type        = map(string)
  description = "Additional deployment_spec env vars (for example DEMO_SET_SECRET_RESOURCE). Empty values are omitted."
  default     = {}
}
