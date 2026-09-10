---
name: gcp-agent-sandbox-crud
description: >-
  Create, list, get, pause, resume, and delete Google Gemini Enterprise Agent
  Platform sandbox environments, templates, and empty host engines. Covers
  prebuilt shell, Python code-execution, and Computer Use sandboxes, optional
  BYOC, ADC, and live API/doc mismatches. EU example region is europe-west4
  (not europe-west1). Shell/CU templates currently fail there; code exec works.
  Use when the user mentions Agent Platform sandboxes, sandboxEnvironment,
  sandbox templates, pause/resume sandbox, or CRUD on reasoning-engine
  sandboxes. Read references/limitations.md before create/pause/exec. Prefer
  this skill to create or tear down sandboxes.
license: Apache-2.0
compatibility: >-
  Requires Python 3.10+, pip install google-cloud-aiplatform[agent_engines]>=2.1.0
  (see ../requirements.txt), Google Cloud SDK (gcloud) with Application Default
  Credentials, and network access to {location}-aiplatform.googleapis.com.
  Use scripts/sandbox.py (agentplatform.Client, API v1). There is no gcloud
  sandbox CLI.
metadata:
  version: "1.0"
---

# GCP Agent Platform sandboxes (CRUD)

Create and manage **sandbox environments** and **templates** on an empty Agent
Platform instance. Prefer the bundled script over inventing curl. Public docs
conflict with the live API — when they do, follow this skill and
[references/limitations.md](references/limitations.md) (ids in
[references/issues.md](references/issues.md)). Tell the user **before** a
known-broken call.

Do not attach smoke-test sandboxes to existing named demo agents unless the user
names that engine. Sandboxes **bill while they exist**.

## Known limitations (required)

**Read [references/limitations.md](references/limitations.md) before create,
pause, exec, or Computer Use.** Act and speak using that table. Summary:

- EU location to use in examples: **`europe-west4`**. Not `europe-west1`. Never
  fail EU traffic over to a US endpoint (CRUD-6).
- In `europe-west4`, **Python code** sandboxes work. **Shell and Computer Use
  templates do not** (`ABORTED`/`FAILED`). Offer code in EU, or shell/CU in
  `us-central1` only if the user agrees.
- Do not create a shell/CU sandbox until the template is **`ACTIVE`** (CRUD-14).
- Do not pause/resume **code** sandboxes (CRUD-8). Do not bash-exec on code
  (CRUD-9).
- Computer Use needs a SA JWT + Token Creator on that SA (CRUD-10). ADC bearer
  fails.
- On template abort, print the **operation name**. Do not send the user to
  Cloud Logging for `ABORTED` (CRUD-12).
- Code create body is empty `codeExecutionEnvironment: {}` (CRUD-13).
- BYOC: Artifact Registry only, not Docker Hub (CRUD-11). No VNC path (CRUD-15).

## Onboarding (required before any API call)

Collect from the user. **Do not guess** project, location, engine, or credentials.
Do not read `gcloud config`.

1. Auth — Application Default Credentials only:
   ```bash
   gcloud auth application-default login
   gcloud auth application-default set-quota-project PROJECT_ID
   ```
   Confirm with `gcloud auth application-default print-access-token >/dev/null`
   (do not print the token). Never ask for SA JSON keys or pasted tokens.
2. `PROJECT_ID` — the GCP project **the user states**.
3. `LOCATION` — Agent Platform region the user states (examples: `us-central1`,
   `europe-west4`). No default. US and EU are separate; do not mix. If they say
   “EU” and do not name a region, ask; prefer `europe-west4` over `europe-west1`.
4. IAM — user confirms `roles/aiplatform.user` (or equivalent). Computer Use also
   needs Token Creator on `--service-account` (CRUD-10). Do not probe IAM unless
   they ask. Do not grant IAM.
5. Engine — reuse a name already in this session, or the user names an existing
   `reasoningEngines/…` resource, or asks to create a dedicated empty host.
   Never pick from `engines list` without confirmation.

If project/location/ADC are missing on first use, **ask** and show the sample
prompts below. If flags are unclear, run `python3 scripts/sandbox.py help` first
(no ADC). Run the shim from **this skill directory**.

## Hard rules

- Host: regional Agent Platform (`agentplatform.Client` `api_version=v1`). No `global` sandbox API.
- `--project` and `--location` are required on API commands (no defaults).
- Deletes require `--yes`. Without it, print the name and stop.
- Default sandbox TTL is `3600s`. Warn before create. Pause when idle; delete when done.
- Computer Use templates must set `egressControlConfig.internetAccess: true`.
- Code language in v1 is **Python only**.
- BYOC only if the user supplies `IMAGE_URI` and grants Artifact Registry reader
  to `service-{PROJECT_NUMBER}@gcp-sa-vertex-sandbox.iam.gserviceaccount.com`.
- Reuse engine/sandbox/template names from this conversation; do not create a new
  engine per turn.
- Before an API call, apply the **Issue gate**. Docs lose to `limitations.md`.

## Issue gate

Before an action, match it in [references/limitations.md](references/limitations.md).
Tell the user using that file’s **Tell the user** text, then apply **Agent action**
(or stop).

| User asks to… | Issue |
|---|---|
| Use `gcloud` sandbox / reasoning-engines commands | CRUD-1 |
| Create a Computer Use sandbox with `spec.computerUseEnvironment` | CRUD-2 |
| Treat API `projects/NUMBER/…` names as a different project than `PROJECT_ID` | CRUD-3 |
| Treat an LRO without `done: true` as complete | CRUD-4 |
| Expect `connectionInfo` on a code-execution sandbox | CRUD-5 |
| Shell or Computer Use in `europe-west4` / `europe-west1` / “EU” | CRUD-6 |
| Omit `--template` on shell or Computer Use create | CRUD-7 |
| Pause or resume a code-execution sandbox | CRUD-8 |
| Run bash on a code-execution sandbox | CRUD-9 |
| Drive the Computer Use browser / CDP / Playwright | CRUD-10 |
| BYOC from Docker Hub | CRUD-11 |
| Explain a template `ABORTED`/`FAILED` from Cloud Logging | CRUD-12 |
| Code sandbox with `LANGUAGE_PYTHON` in the spec | CRUD-13 |
| Create a sandbox from a still-PROVISIONING template | CRUD-14 |
| VNC or live desktop | CRUD-15 |
| JavaScript / CMEK / VPC / snapshots | CRUD-16 |

REST/SDK shapes: [references/rest.md](references/rest.md). Exec:
**gcp-agent-sandbox-exec**. Browser: **gcp-agent-sandbox-computer-use**.

## Script

All paths relative to this skill root.

```bash
python3 scripts/sandbox.py help
python3 scripts/sandbox.py --project PROJECT_ID --location LOCATION COMMAND
```

| Command | Purpose |
|---|---|
| `engines create\|list\|get\|delete` | Empty sandbox-host instance |
| `templates create\|list\|get\|delete` | `--kind shell\|computer-use\|byoc` |
| `sandboxes create\|list\|get\|pause\|resume\|delete\|wait` | `--kind code\|shell\|computer-use\|byoc` |
| `exec code\|bash` | Stage 2; see gcp-agent-sandbox-exec |
| `cu health\|tabs\|cdp\|ws\|playwright` | Stage 3; `--service-account` required |

`sandboxes wait` polls until `STATE_RUNNING` (default), `STATE_PAUSED`, or `gone` (timeout 300s).
Delete order: sandboxes → templates → engine.

## Sample prompts

Show these on first use. Full list: [references/prompts.md](references/prompts.md).

- Show me how to invoke the sandbox CLI (`scripts/sandbox.py help`); do not call GCP yet.
- Onboard me to Agent Platform sandboxes in project `PROJECT_ID`, location `us-central1`, using ADC.
- Same onboarding in `europe-west4` (expect code-only; shell/CU templates fail — tell me first).
- Create a dedicated empty sandbox-host engine, then a prebuilt shell sandbox with TTL 1h; list; delete when done.
- Create a code-execution sandbox (Python, default machine).
- Pause this sandbox, then resume it (refuse if it is a code sandbox).
- Create a Computer Use sandbox from a reused template (internet egress on).
