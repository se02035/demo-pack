variable "project_id" {
  type        = string
  description = "GCP project that hosts the Agent Identity demo. Set in gitignored terraform.tfvars (no default)."
}

variable "region" {
  type        = string
  description = "Region for Agent Runtime, Cloud Run, Artifact Registry, and the demo bucket."
  default     = "us-central1"
}

variable "org_id" {
  type        = string
  description = "Organization ID for the Agent Identity trust domain. Required: data.google_project.org_id is empty on folder-parented projects. Set in gitignored terraform.tfvars."
}

variable "enable_agent_runtime_code" {
  type        = bool
  description = "Concept 2: attach the ADK hello-world source_code_spec to the stub Reasoning Engine."
  default     = false
}

variable "enable_cloud_run" {
  type        = bool
  description = "Concept 2: create the fully-managed Cloud Run v1 service with agent identity annotations."
  default     = false
}

variable "enable_principalset_agents" {
  type        = bool
  description = "Concept 3a: create a second Agent Runtime + Cloud Run pair with no per-principal secret IAM (principalSet inherit)."
  default     = false
}

variable "enable_principalset_mutate" {
  type        = bool
  description = "Concept 3b: create tf-agentid-set-broadcast and bind secretAccessor only to principalSets (env-only update on all hosts)."
  default     = false
}

variable "cloud_run_service_name" {
  type        = string
  description = "Cloud Run service name. Used to predict the SPIFFE principal in step 1; do not change between steps."
  default     = "tf-agentid-hello"
}

variable "cloud_run_image" {
  type        = string
  description = "Container image for the first Cloud Run service. Default is the public hello image so identity can be proven before the ADK image is built."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "set_proof_cloud_run_service_name" {
  type        = string
  description = "Second Cloud Run service name (principalSet inherit demo)."
  default     = "tf-agentid-set-proof"
}

variable "reasoning_engine_display_name" {
  type        = string
  description = "Display name for the stub / ADK Reasoning Engine (same resource both steps)."
  default     = "tf-agentid-hello"
}

variable "set_proof_reasoning_engine_display_name" {
  type        = string
  description = "Display name for the second Reasoning Engine (principalSet inherit demo)."
  default     = "tf-agentid-set-proof"
}

variable "agent_model" {
  type        = string
  description = "Gemini model ID for the ADK agent (DEMO_MODEL)."
  default     = "gemini-2.5-flash"
}
