# Hands-on lab: Agent Identity with one Terraform state

Audience: engineers and DevOps who will run this repo against their own GCP project.

The lab has two parts:

1. **Concepts** — what this demo is proving, with links to public Google documentation.
2. **Exercises** — which files to open, which flags to flip, which commands to run, and what success vs `403` looks like.

Operator index (layout, destroy): [README.md](../README.md). Packaging and Cloud Run v1 details: [agent-identity-terraform.md](agent-identity-terraform.md).

Put `project_id` and `org_id` only in gitignored `terraform/terraform.tfvars`. Commands below use `terraform output` so they stay project-agnostic.

---

## Part 1 — Concepts and challenges

### Agent Identity is not a service account you create first

GCP [Agent Identity](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview) is a SPIFFE identity **minted by the hosting resource** (Reasoning Engine, Cloud Run service, and others). There is no standalone `google_agent_identity` Terraform resource. [`google_agent_identity_auth_provider`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/agent_identity_auth_provider) is a credentials vault for third-party OAuth/API keys and is out of scope here.

IAM uses [principal identifiers](https://docs.cloud.google.com/iam/docs/principal-identifiers):

| Kind | Member |
|---|---|
| One Agent Runtime engine | `principal://agents.global.org-{ORG_ID}.system.id.goog/resources/aiplatform/projects/{PROJECT_NUMBER}/locations/{REGION}/reasoningEngines/{ENGINE_ID}` |
| One Cloud Run service | `principal://agents.global.org-{ORG_ID}.system.id.goog/resources/run/projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE_NAME}` |
| All Agent Runtime agents in a project | `principalSet://agents.global.org-{ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/{PROJECT_NUMBER}` |
| All Cloud Run agents in a project | `principalSet://agents.global.org-{ORG_ID}.system.id.goog/attribute.platformContainer/run/projects/{PROJECT_NUMBER}` |

The API’s `effectiveIdentity` field has **no** `principal://` prefix. IAM `member` strings must add it. [Authenticate as the agent](https://docs.cloud.google.com/iam/docs/auth-agent-own-identity) and [grant access to multiple agents](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity) describe the same shapes.

You do **not** add members to a `principalSet`. Membership is automatic from the minted SPIFFE path. A Cloud Run agent is **not** in the `aiplatform` set.

### Challenge: multi-step deploy without a second Terraform state

A common wish is:

1. Stack A creates “the agent identity” and IAM.
2. Stack B deploys agent code and assumes that identity.

That works for service accounts (you create the SA, then attach it). It does **not** work for Agent Runtime: the engine ID is **server-generated**, so the `principal://.../reasoningEngines/{ID}` string does not exist until the host exists. Cloud Run’s principal **can** be predicted from the service name and bound before the service exists.

This repo keeps **one root module, one backend, one state** and sequences with feature flags so step 2 updates the **same** Reasoning Engine ([Use Terraform with Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/use-terraform)). Identity does not change when you attach source.

Open:

- [`terraform/modules/agent_runtime/main.tf`](../terraform/modules/agent_runtime/main.tf) — `identity_type = "AGENT_IDENTITY"`, source attached later
- [`terraform/modules/agent_identity/main.tf`](../terraform/modules/agent_identity/main.tf) — `principal://` and `principalSet://` members
- [`terraform/modules/cloud_run_agent/main.tf`](../terraform/modules/cloud_run_agent/main.tf) — v1 Knative annotations, not `google_cloud_run_v2_service`

Cloud Run Agent Identity is minted via the **v1** API (`run.googleapis.com/identity-type=agent-identity`). The v2 service resource silently drops those annotations. Both Admin API versions are GA; v2 does not obsolete v1. See [Cloud Run Admin API versions](https://cloud.google.com/run/docs/reference/about-api-versions).

### What the three lab concepts prove

1. **Infra + identity + IAM** — stub engine, predicted Cloud Run principal, Secret Manager / GCS, IAM bound before ADK source exists.
2. **Code on those identities** — same engine gets ADK source; Cloud Run is created with agent-identity. The agent can read the secret granted to **its** `principal://`.
3. **`principal://` vs `principalSet://`**
   - Per-agent `principal://` bindings are **not** inherited by a new agent (`403` on `tf-agentid-demo`).
   - `principalSet://` bindings **are** inherited by a new agent in that platform/project (`tf-agentid-set-proof`).
   - A **later** principalSet IAM change is picked up by **existing and new** agents (`tf-agentid-set-broadcast`) with no new `principal://` members.

Agent tools: [`agent/hello_agent/agent.py`](../agent/hello_agent/agent.py).

---

## Part 2 — Lab

### 0. Configure (once)

Tooling, pinned versions, and the ADK image story: [README.md Prerequisites](../README.md#prerequisites). If you get stuck mid-lab, destroy with the flags currently in `terraform.tfvars` (see [Destroy](#destroy)) and restart at §1. Do not flip flags back to `false` and apply.

```bash
gcloud auth application-default login
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Set `project_id` and `org_id` in `terraform.tfvars`. Leave the four `enable_*` flags `false` for concept 1.

```bash
gcloud config set project "$(grep '^project_id' terraform.tfvars | awk -F\" '{print $2}')"
terraform init
```

Region default is `us-central1`. Override `region` in tfvars if needed.

### 1. Infra, stub identity, IAM

Open [`terraform/variables.tf`](../terraform/variables.tf) (`enable_agent_runtime_code`, `enable_cloud_run` default false). Apply:

```bash
terraform apply
```

Expect a Reasoning Engine with `identity_type = AGENT_IDENTITY` and **no** source, plus secrets `tf-agentid-demo` (per-principal IAM) and `tf-agentid-set-proof` (principalSet IAM only).

```bash
terraform output effective_identity
terraform output cloud_run_principal
terraform output agent_runtime_principal_set
terraform output set_proof_secret_id

gcloud secrets get-iam-policy "$(terraform output -raw set_proof_secret_id)" \
  --project="$(terraform output -raw project_id)"
```

`tf-agentid-set-proof` must list **only** the two `principalSet://` members. `tf-agentid-demo` lists the first Runtime `principal://` and the predicted Cloud Run `principal://`.

### 2. Deploy code on the first agents

In `terraform.tfvars` set:

```hcl
enable_agent_runtime_code = true
enable_cloud_run          = true
```

Leave those **true** from now on (a later plan with them false would strip source and destroy Cloud Run).

```bash
terraform apply
```

This updates the **same** engine (ID must not change) and creates Cloud Run `tf-agentid-hello`. First Cloud Run revision uses the public hello image unless you set `cloud_run_image`.

**Validate Agent Runtime identity and the per-principal secret:**

```bash
PROJECT="$(terraform output -raw project_id)"
ENGINE_ID="$(terraform output -raw reasoning_engine_id)"
REGION="$(grep '^region' terraform.tfvars | awk -F\" '{print $2}')"
REGION="${REGION:-us-central1}"

curl -sS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/reasoningEngines/${ENGINE_ID}" \
  | python3 -c 'import json,sys; s=json.load(sys.stdin).get("spec",{}); print(s.get("identityType"), s.get("effectiveIdentity"))'

curl -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "class_method": "async_stream_query",
    "input": {
      "user_id": "tf-demo",
      "message": "Read the demo secret using your tool and tell me the payload."
    }
  }' \
  "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/reasoningEngines/${ENGINE_ID}:streamQuery?alt=sse"
```

Expect payload `agent-identity-proof`. Ask the same agent to read the **set-proof** secret; expect `principalset-membership-proof` (the first agents are already in the principalSets).

**Cloud Run minted identity** is on the **ready revision**, not the service template:

```bash
REVISION="$(gcloud run revisions list \
  --project="${PROJECT}" --region="${REGION}" \
  --service=tf-agentid-hello \
  --format='value(metadata.name)' --limit=1)"

gcloud run revisions describe "${REVISION}" \
  --project="${PROJECT}" --region="${REGION}" \
  --format='yaml(metadata.annotations)'
```

Expect `run.googleapis.com/identity-type=agent-identity` and `run.googleapis.com/identity` equal to the predicted SPIFFE **without** `principal://` (leading `//agents.global.org-...`).

Optional: swap the first Cloud Run service to the ADK image (`terraform output -raw adk_image_uri`) after Cloud Build, on the **same** service (identity-type is immutable).

### 3a. Second agents inherit principalSet IAM

Build the ADK image **in this project** if you have not (there is no shared public image; the second Cloud Run uses that URI on create):

```bash
gcloud builds submit ../agent \
  --project="$(terraform output -raw project_id)" \
  --region="${REGION}" \
  --config=../agent/cloudbuild.yaml \
  --substitutions=_IMAGE="$(terraform output -raw adk_image_uri)"
```

In `terraform.tfvars`:

```hcl
enable_principalset_agents = true
```

```bash
terraform apply
```

Record `set_proof_reasoning_engine_id` — it must differ from `reasoning_engine_id`. Confirm `gcloud secrets get-iam-policy` on `tf-agentid-set-proof` still has **no** new `principal://` member.

**Negative** (per-principal secret is not inherited):

```bash
NEW_ENGINE="$(terraform output -raw set_proof_reasoning_engine_id)"

curl -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "class_method": "async_stream_query",
    "input": {
      "user_id": "tf-set-proof",
      "message": "Read the demo secret using your tool. If it errors, quote the error verbatim."
    }
  }' \
  "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/reasoningEngines/${NEW_ENGINE}:streamQuery?alt=sse"
```

Expect `403` / `secretmanager.versions.access` / `IAM_PERMISSION_DENIED`.

**Positive** (principalSet inherit): ask the same new engine to read the **set-proof** secret. Expect `principalset-membership-proof`.

**Cloud Run** (`tf-agentid-set-proof`): check the ready revision identity annotation, then invoke ADK via the Run proxy (a user access token returns 401):

```bash
gcloud run services proxy tf-agentid-set-proof \
  --project="${PROJECT}" --region="${REGION}" --port=8091
# another terminal:
curl -sS http://127.0.0.1:8091/list-apps
# POST /apps/hello_agent/users/lab/sessions then POST /run asking for the set-proof secret
```

GCS `read_demo_gcs_object` on the new agents should also `403` (bucket IAM is still per-principal). That is extra negative, not a second experiment.

### 3b. Mutate principalSet IAM for every agent at once

In `terraform.tfvars`:

```hcl
enable_principalset_mutate = true
```

```bash
terraform apply
```

This creates `tf-agentid-set-broadcast` (payload `principalset-broadcast-proof`), binds **only** the two principalSets, and sets `DEMO_SET_BROADCAST_RESOURCE` on **all** hosts (env-only; engine IDs must not change).

Ask **both** engines to read the broadcast secret. Both should return `principalset-broadcast-proof`. `get-iam-policy` on that secret still lists only the two `principalSet://` members.

### Destroy

Same flags as the last apply, in `terraform.tfvars`. Local `terraform.tfstate` is required. Then start again at §1 if you are restarting.

```bash
cd terraform
terraform destroy
# or ./destroy.sh
```

APIs stay enabled (`disable_on_destroy = false`). Do not commit `terraform.tfvars` or `*.tfstate`. Do not reset by flipping flags to `false` and applying.
