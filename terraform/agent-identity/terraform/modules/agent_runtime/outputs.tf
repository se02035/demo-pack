output "reasoning_engine_id" {
  description = "Server-generated Reasoning Engine ID (last path segment)."
  value       = element(reverse(split("/", google_vertex_ai_reasoning_engine.hello.name)), 0)
}

output "reasoning_engine_name" {
  description = "Full resource name of the Reasoning Engine."
  value       = google_vertex_ai_reasoning_engine.hello.name
}

output "effective_identity" {
  description = "API effectiveIdentity (no principal:// prefix)."
  value       = google_vertex_ai_reasoning_engine.hello.spec[0].effective_identity
}
