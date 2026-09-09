variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "Region for regional resources (bucket, Artifact Registry)."
}

variable "enable_principalset_mutate" {
  type        = bool
  description = "When true, create the principalSet broadcast secret (concept 3b)."
  default     = false
}
