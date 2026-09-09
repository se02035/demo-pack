output "service_url" {
  description = "Cloud Run URL, or empty when enable_cloud_run is false."
  value       = var.enable_cloud_run ? google_cloud_run_service.hello[0].status[0].url : ""
}

output "service_name" {
  description = "Cloud Run service name (empty when not created)."
  value       = var.enable_cloud_run ? google_cloud_run_service.hello[0].name : ""
}
