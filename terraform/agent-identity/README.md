# Agent Identity Terraform demo

One Terraform **state** that sequences GCP [Agent Identity](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview) across Agent Runtime and Cloud Run: mint identity and bind IAM first, deploy ADK code onto those same hosts, then show that `principalSet://` IAM is inherited (and later mutated) while per-agent `principal://` bindings are not.

This is a demo, not a production module. There is no `google_agent_identity` resource — identity is minted by the hosting resource.

**Hands-on lab (concepts + commands):** [docs/walkthrough.md](docs/walkthrough.md)

**Engineering notes** (Cloud Run v1 vs v2, source packaging, failed engine updates): [docs/agent-identity-terraform.md](docs/agent-identity-terraform.md)

## Layout

```
agent/                             # ADK hello-world (Runtime tarball + Cloud Run image)
docs/walkthrough.md                # lab
docs/agent-identity-terraform.md   # engineering notes
terraform/                         # one root module, local modules, local state
  modules/shared_resources/
  modules/agent_identity/
  modules/agent_runtime/
  modules/cloud_run_agent/
```

No `null_resource` / `local-exec`. Provider: `hashicorp/google` **8.1.0** (pinned in `terraform/versions.tf`).

## Prerequisites

Lab users use their own GCP project. Versions that matter at runtime are pinned in this repo; do not re-state them as ranges.

- **Terraform 1.15.4** — pinned (`terraform/versions.tf`, `terraform/.terraform-version`). `terraform init` refuses other CLIs. Install with [tfenv](https://github.com/tfutils/tfenv) or the [HashiCorp zip](https://developer.hashicorp.com/terraform/install).
- **`gcloud`** with Application Default Credentials that can administer the project (Owner or equivalent). No SDK version pin. Before concept 3a Cloud Run invoke: `gcloud components install cloud-run-proxy`.
- A **GCP project in an organization**, with billing enabled. Agent Identity’s trust domain is org-scoped. Folder-parented projects often do not expose `org_id` on `data.google_project`.
- **`project_id` and `org_id`** — required Terraform variables with no defaults. Put them only in gitignored `terraform/terraform.tfvars`.

**Do not** install Python, ADK, or Docker on the laptop. Agent Runtime installs [`agent/requirements.txt`](agent/requirements.txt) from the tarball; Cloud Run uses [`agent/Dockerfile`](agent/Dockerfile) (`python:3.12.14-slim`). Walkthrough `python3 -c` one-liners only need a system Python for JSON parsing.

**Image:** concept 2’s first Cloud Run service uses the public `us-docker.pkg.dev/cloudrun/container/hello` image (identity proof without a custom build). Concept 3a’s second Cloud Run service needs **your** Cloud Build of `agent/` into the Artifact Registry repo Terraform created in concept 1 (`terraform output -raw adk_image_uri`). There is no shared public ADK image. Cloud Build’s `gcr.io/cloud-builders/docker` builder has no useful semver pin.

```bash
gcloud auth application-default login
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit project_id and org_id. Do not commit terraform.tfvars.
gcloud config set project "$(grep '^project_id' terraform.tfvars | awk -F\" '{print $2}')"
terraform init
```

## Apply (same backend, leave flags true after you flip them)

| Concept | Flags | What you get |
|---|---|---|
| 1. Infra + identity + IAM | `enable_agent_runtime_code` / `enable_cloud_run` false | Stub Reasoning Engine (`AGENT_IDENTITY`), secrets/GCS/AR, per-principal IAM, principalSet IAM on `tf-agentid-set-proof` |
| 2. Code on first agents | those two **true** | ADK source on the **same** engine; Cloud Run `tf-agentid-hello` |
| 3a. Inherit | `enable_principalset_agents` true | Second Runtime + Cloud Run `tf-agentid-set-proof` (no per-principal secret IAM) |
| 3b. Mutate | `enable_principalset_mutate` true | Secret `tf-agentid-set-broadcast` bound only to principalSets; env-only update on all hosts |

After concept 2, build the ADK image **before** concept 3a (the second Cloud Run uses `terraform output -raw adk_image_uri`):

```bash
PROJECT="$(terraform output -raw project_id)"
IMAGE="$(terraform output -raw adk_image_uri)"
gcloud builds submit ../agent \
  --project="${PROJECT}" \
  --region=us-central1 \
  --config=../agent/cloudbuild.yaml \
  --substitutions=_IMAGE="${IMAGE}"
```

Do **not** use `google_cloud_run_v2_service` — v2 drops identity annotations. Do **not** `terraform taint` the Reasoning Engine to retry a failed source update (the engine ID and IAM member both change).

Full commands, expected payloads, and `403`s: [docs/walkthrough.md](docs/walkthrough.md).

## Destroy

Use the **same flags as the last apply** (keep them in `terraform.tfvars`). Do not reset a stuck lab by flipping flags to `false` and applying — that strips source / Cloud Run instead of tearing everything down.

```bash
cd terraform
terraform destroy
# or: ./destroy.sh
```

**Local `terraform.tfstate` is required** (gitignored; no remote backend). Destroy removes Reasoning Engines, Cloud Run, secrets, IAM this module created, the demo bucket, and Artifact Registry `tf-agentid`. APIs stay enabled (`disable_on_destroy = false`) so Terraform does not disable APIs it adopted, including ones that were already on. Cloud Build history can remain.

After destroy, start again at concept 1.
