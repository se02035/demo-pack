# Fully-managed Cloud Run via the v1 Knative-compatible API.
# Do NOT replace this with google_cloud_run_v2_service: v2 silently drops
# run.googleapis.com/* template annotations and will not mint Agent Identity.
#
# identity-type / identity-certificate-enabled are NOT on HashiCorp's documented
# annotation allowlist. REST v1 accepts them (live-proven). The provider may
# warn, strip, or perpetual-diff them. identity-type is left out of
# ignore_changes so a provider fight is visible on the next plan.
# Server-added keys (including minted run.googleapis.com/identity) are ignored.

resource "google_cloud_run_service" "hello" {
  count = var.enable_cloud_run ? 1 : 0

  name                       = var.service_name
  location                   = var.region
  project                    = var.project_id
  autogenerate_revision_name = true

  metadata {
    annotations = {
      "apphub.cloud.google.com/functional-type" = "agent"
    }
  }

  template {
    metadata {
      annotations = {
        "run.googleapis.com/identity-type"                = "agent-identity"
        "run.googleapis.com/identity-certificate-enabled" = "true"
      }
    }

    spec {
      containers {
        image = var.image

        ports {
          container_port = 8080
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }

        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }

        env {
          name  = "GOOGLE_CLOUD_LOCATION"
          value = var.region
        }

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

  traffic {
    percent         = 100
    latest_revision = true
  }

  lifecycle {
    ignore_changes = [
      metadata[0].annotations["serving.knative.dev/creator"],
      metadata[0].annotations["serving.knative.dev/lastModifier"],
      metadata[0].annotations["run.googleapis.com/operation-id"],
      metadata[0].annotations["run.googleapis.com/ingress-status"],
      template[0].metadata[0].name,
      template[0].metadata[0].annotations["autoscaling.knative.dev/maxScale"],
      template[0].metadata[0].annotations["run.googleapis.com/client-name"],
      template[0].metadata[0].annotations["run.googleapis.com/client-version"],
      template[0].metadata[0].annotations["run.googleapis.com/startup-cpu-boost"],
      template[0].metadata[0].annotations["run.googleapis.com/identity"],
      template[0].spec[0].service_account_name,
    ]
  }
}
