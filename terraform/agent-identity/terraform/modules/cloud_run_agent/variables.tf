variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "Cloud Run region."
}

variable "enable_cloud_run" {
  type        = bool
  description = "When true, create the v1 Cloud Run service with agent identity annotations."
}

variable "service_name" {
  type        = string
  description = "Service name. Must match the principal predicted in step 1."
}

variable "image" {
  type        = string
  description = "Container image. Default hello image proves identity; swap to the ADK image later."
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

variable "agent_model" {
  type        = string
  description = "Gemini model ID injected as DEMO_MODEL."
}

variable "extra_env" {
  type        = map(string)
  description = "Additional container env vars. Empty values are omitted."
  default     = {}
}
