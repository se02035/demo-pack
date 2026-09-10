# Known issues (tell the user before acting)

Validated 2026-09-10 (`us-central1` + `europe-west4`; `europe-west1` historical).
When these conflict with public sandbox docs, **this file and
[limitations.md](limitations.md) win.**

**Agents:** follow [limitations.md](limitations.md) for **Agent action** and
**Tell the user** text. Quote the id. Do not fail EU over to US.

| Id | Trigger | Actual | Workaround |
|---|---|---|---|
| CRUD-1 | `gcloud ai reasoning-engines` / sandbox CLI | Command group does not exist | Use `scripts/sandbox.py`. |
| CRUD-2 | Computer Use `spec.computerUseEnvironment` | HTTP 400 `Computer Use Environment is not supported.` | Template `COMPUTER_USE` + `internetAccess: true`; sandbox template-only, no spec. |
| CRUD-3 | URLs built only from the user project ID | Returned names use the numeric project number | `--project` = user-stated ID. Do not rewrite API names. |
| CRUD-4 | Poll LRO until a `done` field exists | In-progress ops **omit** `done` | Missing `done` = in progress. Cap the wait. Never unbounded. |
| CRUD-5 | `connectionInfo` on every sandbox | Code sandboxes have **no** `connectionInfo` | GET after RUNNING. CDP only on shell/CU. |
| CRUD-6 | Shell/CU **templates** in `europe-west4` (or `europe-west1`) | LRO `ABORTED` (code 10) ~11–16 min; resource `FAILED`; never `ACTIVE`. Code sandboxes **work**. | Tell the user. Offer code in EU or shell/CU in US **only if they agree**. No US failover. Print the operation name (CRUD-12). |
| CRUD-7 | Omit template on shell/CU create | HTTP 400 template/snapshot required. SDK auto-template can hang. | Create template; wait until **ACTIVE**; then `--template`. |
| CRUD-8 | Pause/resume a **code** sandbox | HTTP 500 | Refuse; do not call. Pause/resume shell and CU only. |
| CRUD-9 | Bash on a **code** sandbox | HTTP 400 generic | Refuse. `execute_code` or a shell sandbox. |
| CRUD-10 | CU data plane with ADC bearer / missing Token Creator | 401 invalid `iss`, or 403 `signJwt` | SA JWT required. Token Creator on `--service-account`. Do not grant IAM. |
| CRUD-11 | BYOC Docker Hub | Create OK; never `ACTIVE` | Artifact Registry `*.pkg.dev` only. |
| CRUD-12 | After template `ABORTED`/`FAILED` | Audit logs do **not** contain `ABORTED`. Ops GET is `{code:10, message:ABORTED}` only | Print operation name. Do not send the user to Cloud Logging for a root cause. |
| CRUD-13 | Code create with `LANGUAGE_PYTHON` | Wrong body vs live API | `codeExecutionEnvironment: {}`. |
| CRUD-14 | Create sandbox while template `PROVISIONING` | HTTP 400 not ACTIVE | Poll `templates.get` until `ACTIVE`. Listing ≠ ready. |
| CRUD-15 | VNC / live view | No documented quickstart path | US: Playwright `connect_over_cdp`. Do not invent VNC. |
| CRUD-16 | JS code, CMEK, VPC/PSC, snapshots | Out of skill scope | Refuse. |

## User-facing blurbs

Use the **Tell the user** column in [limitations.md](limitations.md). Short forms:

### CRUD-6 — EU shell/CU templates do not provision

Engine and **Python code** sandboxes work in `europe-west4`. Prebuilt **shell**
and **Computer Use** templates currently end `ABORTED`/`FAILED`. I will not
route this to `us-central1` unless you explicitly want a US region.

### CRUD-8 — No pause on code sandboxes

Pause/resume returns 500 on code-execution sandboxes. I will not call it.
Delete or wait for TTL.

### CRUD-10 — Computer Use needs a service-account JWT

Your user ADC token is not enough (401). Grant Token Creator on the service
account you pass in, and Agent Platform User on that SA. I will not change IAM.

### CRUD-12 — No Cloud Logging root cause

The only customer-visible error is `ABORTED` on the long-running operation. I
will print that operation name for support.
