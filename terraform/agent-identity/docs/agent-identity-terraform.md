# Agent Identity with Terraform (engineering notes)

Hands-on lab: [walkthrough.md](walkthrough.md). Operator index: [README.md](../README.md).

GCP Agent Identity is not a standalone principal you create like a service account.
It is a SPIFFE identity **minted by the hosting resource** and tied to that
resource’s URI. There is no `google_agent_identity` resource.
[`google_agent_identity_auth_provider`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/agent_identity_auth_provider)
is only for third-party OAuth/API-key vaulting and is out of scope here.

This demo keeps **one root module, one backend, one state**. Concept 1 mints (or
predicts) host resource IDs and binds IAM. Later flags attach ADK code, a second
agent pair, and a principalSet IAM mutation — still the same state.

Set `project_id` and `org_id` in gitignored `terraform/terraform.tfvars` (no
defaults in committed files). Trust `terraform output` over any IDs in older
notes.

Early REST identity probes used a **separate** project that is not this
Terraform state. Probe leftover **names** are listed at the end of this doc.

## Identity-stub pattern

“Pre-create identity, bind IAM, deploy code later” only works by minting or
predicting the host resource ID.

| Host | How the principal exists in step 1 |
|---|---|
| Agent Runtime (`google_vertex_ai_reasoning_engine`) | Create a **stub** with `spec.identity_type = "AGENT_IDENTITY"` and **no** `source_code_spec`. The engine ID is server-generated. Bind IAM to `principal://${spec[0].effective_identity}`. Step 2 adds `source_code_spec` on the **same** resource. |
| Cloud Run (`google_cloud_run_service` v1) | The principal is a function of the **chosen service name**. IAM can be pre-bound before the service exists (live-proven). Step 2 creates the service with identity annotations. |

```
Step 1 (flags off)
  APIs → stub Reasoning Engine (AGENT_IDENTITY) → Secret Manager + uniform GCS
       → IAM member bindings to both SPIFFE principals

Step 2 (same state, flags on)
  Update the same RE with ADK hello-world source
  Create Cloud Run fully-managed service via v1 API annotations
```

Feature flags (root module variables):

| Flag | Concept 1 | Concept 2 | Concept 3a | Concept 3b |
|---|---|---|---|---|
| `enable_agent_runtime_code` | `false` | `true` | `true` | `true` |
| `enable_cloud_run` | `false` | `true` | `true` | `true` |
| `enable_principalset_agents` | `false` | `false` | `true` | `true` |
| `enable_principalset_mutate` | `false` | `false` | `false` | `true` |

Terraform contains **no** `null_resource` / `local-exec`. Agent Runtime
packaging uses `archive_file` (`tar.gz`) + `filebase64`. IAM uses additive
`google_*_iam_member` only (never `google_project_iam_binding`).

## Agent Runtime source packaging

Step 2 attaches `source_code_spec` to the **same** Reasoning Engine. Live apply
failed until all of the following were true.

**Entrypoint is `AdkApp`, not the raw agent.** Agent Runtime loads
`python_spec.entrypoint_object` and requires `query` / `stream_query` (or
async variants). A `google.adk.agents.Agent` (`LlmAgent`) does not define
those methods:

```
Class LlmAgent is missing all methods `query`, `async_query`, `stream_query`, ...
```

[`agent/hello_agent/agent.py`](../agent/hello_agent/agent.py) keeps `root_agent`
for Cloud Run’s FastAPI loader (`get_fast_api_app` / `agents_dir`) and exports
`adk_app = AdkApp(agent=root_agent)`. Terraform `entrypoint_object` is
`adk_app`.

**Requirements are exact pins in [`agent/requirements.txt`](../agent/requirements.txt).** Runtime telemetry does
`from google.cloud.aiplatform.utils import resource_manager_utils` at startup.
Without the package: `ModuleNotFoundError: No module named 'google.cloud.aiplatform'`.
Unpinned `>=1.144` pulled **2.1.0**, which split agentplatform into
`google-cloud-agentplatform`. Keep `google-cloud-aiplatform[adk,agent-engines]`
on the pinned 1.x line in that file (do not bump to 2.x).

**Do not set reserved env vars on `deployment_spec.env`.** Agent Runtime
injects them and returns `400 Environment variable name 'X' is reserved`:

`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_QUOTA_PROJECT`, `GOOGLE_CLOUD_LOCATION`,
`PORT`, `K_SERVICE`, `K_REVISION`, `K_CONFIGURATION`,
`GOOGLE_APPLICATION_CREDENTIALS`.

Cloud Run may still set `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION`. Demo
tools use `DEMO_SECRET_RESOURCE`, `DEMO_BUCKET_NAME`, `DEMO_OBJECT_NAME`,
`DEMO_MODEL` (Terraform `var.agent_model`, default `gemini-2.5-flash`).
`gemini-flash-latest` 404’d as a publisher model in this project/region.

**Archive excludes Cloud Run-only files.** Root `archive_file` packs
`hello_agent/` + `requirements.txt` and excludes `Dockerfile`,
`cloudbuild.yaml`, `.dockerignore`, and `main.py`.

**Cloud Run does not wait on the RE source update.** Step 1 already bound the
predicted Cloud Run principal. `module.cloud_run_agent` depends only on
`module.shared_resources` so a 10+ minute engine update (or a failed one)
does not block `google_cloud_run_service`.

### Failed source update / engine ID

The intended path is stub → in-place `source_code_spec` on the **same** engine
ID so step-1 IAM stays valid.

A crashed source revision **rolls the engine back to identity-only**. Later
updates then failed ~2 minutes after image push with **no stderr** (control
plane “cannot serve traffic”). Recreating the engine recovered, but **changed
the ID** (`7812572724336787456` → `9060069821118414848`) and the
`principal://...reasoningEngines/{ID}` IAM member. Terraform rebound those
members on apply.

Do **not** `terraform taint` the Reasoning Engine as a retry. Fix source /
requirements and apply. If recreate is unavoidable, accept a new RE principal.
Cloud Run’s principal is a function of the **service name** and stays stable
if `cloud_run_service_name` is unchanged.

## Principal formats

`effectiveIdentity` from the Agent Runtime API does **not** include the
`principal://` prefix. IAM `member` strings must add it.

Trust domain:

```
agents.global.org-{ORG_ID}.system.id.goog
```

| Kind | Member string |
|---|---|
| One Agent Runtime engine | `principal://agents.global.org-{ORG_ID}.system.id.goog/resources/aiplatform/projects/{PROJECT_NUMBER}/locations/{REGION}/reasoningEngines/{ENGINE_ID}` |
| One Cloud Run service | `principal://agents.global.org-{ORG_ID}.system.id.goog/resources/run/projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE_NAME}` |
| All Agent Runtime agents in the project | `principalSet://agents.global.org-{ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/{PROJECT_NUMBER}` |
| All Cloud Run agents in the project | `principalSet://agents.global.org-{ORG_ID}.system.id.goog/attribute.platformContainer/run/projects/{PROJECT_NUMBER}` |

Terraform constructs the Agent Runtime member as:

```hcl
"principal://${google_vertex_ai_reasoning_engine.hello.spec[0].effective_identity}"
```

Cloud Run’s member is predicted from `var.cloud_run_service_name` (default
`tf-agentid-hello`). Do not rename the service between step 1 and step 2, or the
pre-bound IAM will not match the minted identity.

## IAM model

Per-agent proof bindings (the point of the demo):

- `roles/secretmanager.secretAccessor` on the demo secret
- `roles/storage.objectViewer` on the demo bucket (non-legacy roles only)

Both the stub Reasoning Engine principal and the predicted Cloud Run principal
receive those bindings in step 1.

Baseline `principalSet` for all Agent Runtime agents in the project already
existed here with `roles/logging.logWriter`, `roles/aiplatform.expressUser`,
`roles/serviceusage.serviceUsageConsumer`, `roles/browser`, and others. This
root still **declares** the roles it needs as additive members (idempotent)
rather than assuming they stay.

Cloud Run agent identity is **not** in the `aiplatform` principalSet. The demo
also binds the predicted Cloud Run principal (and a `run` principalSet) for
Vertex/Gemini and logging so the ADK revision can call the model.

## Live-tested results (keep only what worked)

| Test | Result |
|---|---|
| Create identity-only Reasoning Engine (`spec.identityType=AGENT_IDENTITY`, no source) via `v1beta1` REST | **Worked.** `effectiveIdentity` = `agents.global.org-{ORG_ID}.system.id.goog/resources/aiplatform/projects/{PROJECT_NUMBER}/locations/{REGION}/reasoningEngines/{ENGINE_ID}` |
| GET that stub on **v1 GA** API | **Worked.** Same `identityType` / `effectiveIdentity` (Terraform GA provider can manage it) |
| IAM bind `principal://...reasoningEngines/{ID}` as `secretAccessor` on a new secret | **Worked.** Org policy did not block `principal://` members |
| IAM **pre-bind** Cloud Run principal **before** the service existed | **Worked.** Same secret accepted `principal://.../services/tf-agentid-probe-cr` |
| Project `principalSet` for all Agent Runtime agents | **Worked** |
| Enable `agentidentity.googleapis.com` | **Worked** |
| Cloud Run via `gcloud beta run deploy --identity-type` | **Failed.** SDK 575 exposes these flags only on **`gcloud alpha`** |
| Cloud Run via `gcloud alpha run deploy --functional-type=agent --identity-type=agent-identity` | **Worked.** Revision annotation `run.googleapis.com/identity` minted the expected SPIFFE ID |
| Cloud Run **v2** REST with `run.googleapis.com/identity-type` template annotations | **Failed (silent drop).** Service created as a normal compute SA; no agent identity |
| Cloud Run **v1 Knative** REST with revision annotations `run.googleapis.com/identity-type=agent-identity` + service `apphub.cloud.google.com/functional-type=agent` | **Worked.** Same minted identity as gcloud alpha. This is the native Terraform path (`google_cloud_run_service`) |

## Cloud Run: why v1, and why v2 is not used

**Do not use `google_cloud_run_v2_service` for this demo.** v2 rejects/strips
`run.googleapis.com/*` template annotations, and live create did not mint agent
identity. There is no first-class `identity_type` argument on
`google_cloud_run_v2_service` in `hashicorp/google` 8.1.0.

v1 here is still **fully-managed Cloud Run**. It is the Knative-compatible API
Cloud Run has always exposed. It is not deploying onto a GKE/Knative cluster.

v1 is **not deprecated**. Google’s [Admin API versions](https://cloud.google.com/run/docs/reference/about-api-versions)
page is explicit: both v1 and v2 are GA, and v2 does not obsolete v1. Google and
HashiCorp still recommend **v2 for new IaC**. This demo uses v1 as a
**temporary exception** because Agent Identity only works through the v1
annotation surface today.

| Option | Native TF, no gcloud? | Agent identity minted? | Verdict |
|---|---|---|---|
| `google_cloud_run_v2_service` + `run.googleapis.com/identity-type` template annotations | Yes | **No.** v2 silently drops `run.googleapis.com/*` | Drop |
| `google_cloud_run_v2_service` first-class `identity_type` | **No** in google 8.1.0 / public proto | Untestable via Terraform | Not available |
| Undocumented v2 JSON `template.identityType` | REST-only | Public enum names return `INVALID_ARGUMENT` | Not usable |
| `gcloud alpha run deploy --identity-type=agent-identity` | No (shell / local-exec) | Yes | Rejected (no custom scripts in TF) |
| **`google_cloud_run_service` (v1) + revision annotations** | Yes | **Yes (proven)** | **Keep** |

When Google publishes `RevisionTemplate.identity_type` and HashiCorp maps it
onto `google_cloud_run_v2_service`, swap `terraform/modules/cloud_run_agent` to
v2. Until then there is no Terraform-native v2 identity path.

### Terraform provider vs identity-type annotations

HashiCorp’s `google_cloud_run_service` docs list an **allowlist** of
`run.googleapis.com/*` revision annotations. `identity-type` and
`identity-certificate-enabled` are **not** on that list (nor on the public v1
ObjectMeta annotation catalog). REST v1 accepts them (proven).

The provider may:

- send them through anyway (desired — REST is what minting needs)
- warn
- strip them on apply
- perpetual-diff against server-added keys such as `run.googleapis.com/identity`
  (the minted SPIFFE, written by the API after create)

The Cloud Run module keeps identity-type annotations in config, sets
`autogenerate_revision_name = true`, and `lifecycle.ignore_changes` on
**server-added** annotation keys (creator, lastModifier, operation-id, minted
`run.googleapis.com/identity`, default maxScale). It does **not** ignore
`identity-type` itself, so a provider strip/fight shows up on the next plan.

If `terraform plan` after a successful apply wants to remove
`run.googleapis.com/identity-type`, the provider is fighting the annotation.
Workarounds: keep ignore_changes off for that key and re-apply (may recreate a
revision), or wait for v2 `identity_type`. Identity-type is **immutable** once
set (product rule, both APIs).

gcloud Agent Platform flags are still **alpha** on SDK 575 (`gcloud alpha run`),
even though the v1 annotations work.

There is **no public date** for `RevisionTemplate.identity_type`. Watch
googleapis `revision_template.proto`, Terraform provider notes for
`cloudrunv2`, and gcloud promoting `--identity-type` from alpha → beta → GA.

v1 limitations vs v2 that matter for this demo:

- Features land as annotations, not typed fields. Perpetual plan diffs from
  server-added annotations are common.
- First-class v2-only (or much cleaner on v2): `iap_enabled`,
  `deletion_protection`, `build_config`, `multi_region_settings`,
  `invoker_iam_disabled`, typed Direct VPC, `scaling` blocks, GPU as typed
  resources.

## Org policies on this project

Effective policies that matter:

- `iam.allowedPolicyMemberDomains`: **project-level reset** → effective
  `allowAll: true`. This is why `principal://agents.global.org-...` binds
  succeeded. If a parent folder/org later re-enforces a customer-id-only
  allowlist, Agent Identity members will fail until `system.id.goog` / agent
  principals are allowed (or the constraint is reset again at project).
- `storage.uniformBucketLevelAccess`: **enforced true**. Demo buckets must set
  `uniform_bucket_level_access = true`.
- `iam.disableServiceAccountCreation`, `gcp.resourceLocations`,
  `run.allowedIngress`, `run.allowedVPCEgress`: not blocking.
- Project-listed constraints (`compute.requireShieldedVm`,
  `sql.restrictAuthorizedNetworks`,
  `discoveryengine.managed.disableCustomMcpServerConnector`) are effective
  **unenforced**.

No org-policy change is required for this demo **as the project sits today**.
`iam.allowedPolicyMemberDomains` is the one that would break Agent Identity IAM
if re-tightened.

## Sequenced apply (same backend)

`project_id` and `org_id` have **no** committed defaults. Copy
`terraform/terraform.tfvars.example` to gitignored `terraform.tfvars` and fill
them in. After you flip a flag true, leave it true so plan/destroy match state.
Lab commands: [walkthrough.md](walkthrough.md).

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# set project_id and org_id
terraform init
terraform apply
```

Concept 2 Cloud Run first revision uses the public hello image
(`us-docker.pkg.dev/cloudrun/container/hello`) so identity can be proven
without a custom build. Artifact Registry is created in concept 1. After
`gcloud builds submit` (a README command, not Terraform `local-exec`), re-apply
with `cloud_run_image` set to `terraform output -raw adk_image_uri` to swap the
ADK image onto the **same** service (identity-type is already set and immutable).
The second Cloud Run service (concept 3a) uses that URI on create.

## Destroy

Tear down everything this state manages (Reasoning Engine with
`deletion_policy = FORCE`, Cloud Run, secrets, uniform bucket, Artifact
Registry, IAM members). Pass the same flags as the last apply (or keep them
in `terraform.tfvars`):

```bash
cd terraform
terraform destroy
```

`terraform/destroy.sh` is a thin wrapper around the same command. Local
`terraform.tfstate` is required. APIs stay enabled (`disable_on_destroy = false`)
so Terraform does not disable APIs it adopted, including ones that were already
on. Do not reset a stuck lab by flipping flags to `false` and applying. Probe
leftovers in a **separate** project are **not** in this state.

## Validation

Terraform outputs: `effective_identity`, predicted Cloud Run principal, secret
and bucket IDs, Reasoning Engine name/ID, Cloud Run URL (after step 2). Use
those values; do not hardcode project IDs or engine IDs.

Confirm SPIFFE, not the default compute SA:

```bash
PROJECT="$(terraform output -raw project_id)"
ENGINE_ID="$(terraform output -raw reasoning_engine_id)"
REGION="us-central1"

curl -sS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/reasoningEngines/${ENGINE_ID}" \
  | python3 -c 'import json,sys; s=json.load(sys.stdin).get("spec",{}); print(s.get("identityType"), s.get("effectiveIdentity"))'

# Minted Cloud Run identity is on the ready *revision*, not the service template.
REVISION="$(gcloud run revisions list \
  --project="${PROJECT}" --region="${REGION}" \
  --service=tf-agentid-hello \
  --format='value(metadata.name)' --limit=1)"

gcloud run revisions describe "${REVISION}" \
  --project="${PROJECT}" --region="${REGION}" \
  --format='yaml(metadata.annotations)'
```

Expect revision annotation `run.googleapis.com/identity-type=agent-identity`
and server-added `run.googleapis.com/identity` equal to the predicted SPIFFE
**without** the `principal://` prefix (leading `//agents.global.org-...`).
The service spec may still list the default compute SA; that is not a failure.

Invoke Agent Runtime and ask it to read the secret bound in step 1:

```bash
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

Secret Manager audit logs for `AccessSecretVersion` should show the Agent
Runtime `principal://...reasoningEngines/{ID}`, not a service account.

Optional negative: a principal without the secret binding fails
`AccessSecretVersion`.

## Limitations

- Identity is resource-tied; there is no attach-later SPIFFE object.
- Reasoning Engine ID is server-generated; a stub-without-code is required
  before a **specific** RE principal can be bound. Cloud Run principal **can**
  be bound before the service exists (proven).
- Cloud Run agent identity is **not** on `google_cloud_run_v2_service`. Use v1
  `google_cloud_run_service` annotations as a **temporary exception** (v1 is GA
  and not deprecated, but Google/HashiCorp recommend v2 for new IaC).
- Cloud Run identity-type is immutable once set.
- `gcloud` identity flags are **alpha** on SDK 575. No public date for
  `RevisionTemplate.identity_type`.
- HashiCorp’s v1 annotation allowlist does not document `identity-type`; the
  provider may warn, strip, or perpetual-diff it. See above.
- `iam.allowedPolicyMemberDomains` is currently allow-all via project reset;
  tightening it to Workspace customer IDs would block
  `principal://agents.global.org-...` until the policy is adjusted.
- Uniform bucket-level access is enforced; Terraform must set it.
- Agent source in Terraform state (base64 archive) is the single-state
  trade-off. `source_archive` is API input-only.
- Failed RE source updates can roll the engine back to identity-only; later
  updates may fail fast with no stderr. Recreate changes the engine ID and RE
  IAM member. Do not taint as a retry. Cloud Run pre-bind stays name-stable.
- `python_spec.entrypoint_object` must be an `AdkApp`, not a raw `LlmAgent`.
- Python/ADK versions are exact pins in [`agent/requirements.txt`](../agent/requirements.txt) (do not bump `google-cloud-aiplatform` to 2.x).
- Do not set Agent Runtime reserved env names (see source packaging).
- Auth manager (`google_agent_identity_auth_provider`) is out of scope.

## Leftover probe resources

Early REST/gcloud identity probes created resources in a **separate** GCP
project that is not this Terraform state. The demo uses different names
(`tf-agentid-hello`, `tf-agentid-demo-*`, `tf-agentid-set-proof`) so they do
not collide. Destroy or import probe leftovers only if you still use that
other project.

| Resource | Notes |
|---|---|
| Reasoning Engine `tf-agentid-probe-stub` | Identity-only stub from REST probing |
| Secret `tf-agentid-probe-secret` | IAM probe target |
| Cloud Run `tf-agentid-probe-cr` | gcloud alpha identity deploy |
| Cloud Run `tf-agentid-probe-v1ann` | v1 annotation probe (worked) |
| Cloud Run `tf-agentid-probe-v2ann` | v2 annotation probe (failed identity) |
| Cloud Run `tf-agentid-probe-v2ft` | v2 failed-identity service |
| `agentidentity.googleapis.com` | Enabled during probing; Terraform still declares it |

## APIs and provider

Provider: `hashicorp/google` `8.1.0` (pinned; GA `identity_type` on
`google_vertex_ai_reasoning_engine`). Terraform CLI `1.15.4`.

Terraform still declares APIs even when already enabled:
`aiplatform`, `run`, `secretmanager`, `storage`, `cloudbuild`,
`artifactregistry`, `apphub`, `agentregistry`, `agentidentity`.
