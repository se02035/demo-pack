# Standard Google ADK class_methods required when deploying via Terraform
# (the provider does not introspect the entrypoint). See:
# https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/use-terraform
locals {
  adk_class_methods = [
    { name = "get_session", api_mode = "" },
    { name = "list_sessions", api_mode = "" },
    { name = "create_session", api_mode = "" },
    { name = "delete_session", api_mode = "" },
    { name = "async_get_session", api_mode = "async" },
    { name = "async_list_sessions", api_mode = "async" },
    { name = "async_create_session", api_mode = "async" },
    { name = "async_delete_session", api_mode = "async" },
    { name = "async_add_session_to_memory", api_mode = "async" },
    { name = "async_search_memory", api_mode = "async" },
    { name = "stream_query", api_mode = "stream" },
    { name = "async_stream_query", api_mode = "async_stream" },
    { name = "streaming_agent_run_with_events", api_mode = "async_stream" },
  ]
}

resource "google_vertex_ai_reasoning_engine" "hello" {
  project      = var.project_id
  region       = var.region
  display_name = var.display_name
  description  = "Agent Identity demo: stub in step 1, ADK hello-world source in step 2."
  # So `terraform destroy` actually deletes the engine (default can fail).
  deletion_policy = "FORCE"

  spec {
    identity_type = "AGENT_IDENTITY"

    dynamic "source_code_spec" {
      for_each = var.enable_agent_runtime_code ? [1] : []
      content {
        inline_source {
          # Input-only. Lands in Terraform state as the single-state trade-off.
          source_archive = var.source_archive_b64
        }

        python_spec {
          entrypoint_module = "hello_agent.agent"
          entrypoint_object = "adk_app"
          requirements_file = "requirements.txt"
          version           = "3.12"
        }
      }
    }

    agent_framework = var.enable_agent_runtime_code ? "google-adk" : null
    class_methods   = var.enable_agent_runtime_code ? jsonencode(local.adk_class_methods) : null

    dynamic "deployment_spec" {
      for_each = var.enable_agent_runtime_code ? [1] : []
      content {
        min_instances         = 0
        max_instances         = 2
        container_concurrency = 2

        resource_limits = {
          cpu    = "1"
          memory = "2Gi"
        }

        # Do not set reserved names; Agent Runtime injects them and returns 400:
        # GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_QUOTA_PROJECT, GOOGLE_CLOUD_LOCATION,
        # PORT, K_SERVICE, K_REVISION, K_CONFIGURATION, GOOGLE_APPLICATION_CREDENTIALS.
        env {
          name  = "GOOGLE_GENAI_USE_VERTEXAI"
          value = "true"
        }

        env {
          name  = "DEMO_MODEL"
          value = var.agent_model
        }

        env {
          name  = "DEMO_SECRET_RESOURCE"
          value = var.demo_secret_resource
        }

        env {
          name  = "DEMO_BUCKET_NAME"
          value = var.demo_bucket_name
        }

        env {
          name  = "DEMO_OBJECT_NAME"
          value = var.demo_object_name
        }

        dynamic "env" {
          for_each = { for k, v in var.extra_env : k => v if v != null && v != "" }
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  timeouts {
    create = "30m"
    update = "30m"
    delete = "20m"
  }
}
