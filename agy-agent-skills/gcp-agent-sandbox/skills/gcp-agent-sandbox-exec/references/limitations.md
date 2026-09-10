# Known limitations (agent contract)

Validated 2026-09-10. **This file wins over public docs.** Read it before any
create/pause/exec/Computer Use call. Quote the issue id when you stop or change
the plan.

Do not invent workarounds. Do not fail EU traffic over to a US endpoint. Do not
bake project ids, SA emails, or operation ids into chat as “the default.”

## How to apply a row

1. **Agent action** — do this *before* the API call (or instead of it).
2. **Tell the user** — say this in the same turn, in plain language.
3. If they insist on a refused call, explain again and still refuse (except
   where the row says “only if they explicitly allow”).

## What works where

Skill EU example location is **`europe-west4`**. Do not offer `europe-west1` as
the EU region. `us-central1` and `europe-west4` are separate; never mix them.

| Capability | `us-central1` | `europe-west4` |
|---|---|---|
| Empty host engine | yes | yes |
| Code sandbox + Python `execute_code` | yes | yes |
| Shell template → `ACTIVE` | yes (~2 min) | **no** — LRO `ABORTED` (~16 min), resource `FAILED` |
| Shell sandbox + `execute_bash` | yes | not reachable (no ACTIVE template) |
| Computer Use template → `ACTIVE` | yes | **no** — LRO `ABORTED` (~11 min), resource `FAILED` |
| Computer Use JWT / CDP / Playwright `connect_over_cdp` | yes | not reachable |
| Pause / resume shell or Computer Use | yes | not reachable |
| Pause / resume **code** sandbox | **no** (HTTP 500) | **no** (HTTP 500) |
| BYOC `*.pkg.dev` (public AR hello) | template ACTIVE + sandbox RUNNING | not verified |
| BYOC Docker Hub | never `ACTIVE` | not verified |

`europe-west1` (historical): engine + code work; shell/CU templates also never
`ACTIVE` (PROVISIONING then `FAILED`). Same rules as west4. Do not switch the
user to west1 to “fix” west4.

Failure mode is **templates** (warm pool), not sandbox environments. Do not
create a shell/CU sandbox until `templates.get` state is **`ACTIVE`**. Listing a
template while `PROVISIONING` is not ready (HTTP 400 if you create anyway).

## Decision table

| Id | When | Agent action | Tell the user |
|---|---|---|---|
| CRUD-1 | They ask for `gcloud` sandbox / reasoning-engines | Use `gcp-agent-sandbox` (or `python3 -m gcp_agent_sandbox`). Do not invent gcloud. | There is no gcloud sandbox CLI. I will use the gcp-agent-sandbox CLI. |
| CRUD-2 | Computer Use create with `spec.computerUseEnvironment` | Omit spec. Template `COMPUTER_USE` + `internetAccess: true`, then sandbox from that template only. | The Computer Use spec field is rejected (400). I will use a template with internet egress and no sandbox spec. |
| CRUD-3 | Resource name has a project **number** | Keep the API name. `--project` stays the user-stated ID. | Same project; the API prints the numeric project number in names. |
| CRUD-4 | LRO has no `done` field | Treat as in progress. Never wait unbounded. Cap ~300s LRO + ~300s until `ACTIVE`. | Creates are async. I will poll until `done: true` or the cap; missing `done` means still running. |
| CRUD-5 | `connectionInfo` on a **code** sandbox | Do not call Computer Use / CDP on code sandboxes. Use `execute_code`. | Code sandboxes have no browser connection info. Shell/CU do after they are RUNNING. |
| CRUD-6 | Shell or Computer Use **template** in `europe-west4` (or `europe-west1`) | **Do not** wait 40 minutes. **Do not** fail over to US. Offer: (a) Python code sandbox in the same EU region, or (b) shell/CU in `us-central1` **only if they agree**. On abort: print LRO `error` + **operation name**, stop that kind, continue others. | Shell and Computer Use templates in this EU region currently fail to provision (operation ends `ABORTED`, template `FAILED` after ~11–16 min). Python code execution in the same region works. I will not send this to the US unless you ask me to. |
| CRUD-7 | Shell/CU sandbox without `--template` | Create or reuse a template first. Do not use SDK auto-template (`wait_for_completion=True` can hang). | Docs that promise an implicit default template are wrong. I will create a template, wait until it is ACTIVE, then create the sandbox. |
| CRUD-8 | Pause or resume a **code** sandbox | **Refuse.** Do not call the API (500). Pause/resume only shell and Computer Use. | Pause/resume is not supported on code-execution sandboxes (the API returns 500). Delete it or let TTL expire. |
| CRUD-9 | Bash / `execute_bash` on a **code** sandbox | **Refuse.** Use `execute_code`. Shell sandboxes for bash. | Bash exec is not valid on a code sandbox (400). I can run Python on this one, or we need a shell sandbox. |
| CRUD-10 | Computer Use health/tabs/CDP/Playwright | Require `--service-account`. On 403 `signJwt`, stop and print IAM below. Never send ADC OAuth as the CU bearer (401 invalid `iss`). Do not grant IAM. | Computer Use needs a service-account JWT. Your user needs Token Creator **on that SA**, and the SA needs Agent Platform User. Your user login token is not a substitute. I will not change IAM for you. |
| CRUD-11 | BYOC image on Docker Hub / not `*.pkg.dev` | **Refuse** Docker Hub. Require Artifact Registry. | The platform does not pull Docker Hub images (create is accepted, template never becomes ACTIVE). Use an Artifact Registry URI. |
| CRUD-12 | Template LRO `ABORTED` / `FAILED` | Stop waiting. Print `error.code` `error.message` and the **operation resource name**. Do not tell them to grep Cloud Logging for `ABORTED` (it is not there). Do not retry the same region/kind in a loop. | The provisioner aborted with no further detail. Cloud Logging in your project will not show a root cause. The operation name is the handle for Google support. |
| CRUD-13 | Code sandbox create body | Send `spec.codeExecutionEnvironment` as `{}`. Do not send `LANGUAGE_PYTHON`. | Live creates succeed with an empty code spec. The language enum in older samples is the wrong body. |
| CRUD-14 | Template listed but not `ACTIVE` | Keep polling `templates.get` until `ACTIVE`, or stop on `FAILED`/`DELETED`/timeout. | A template that still says PROVISIONING cannot start a sandbox yet. |
| CRUD-15 | VNC / live desktop view | Do not implement. No documented path in the quickstart. Playwright CDP is the proven US path. | VNC/live view is not documented enough to use. In the US I can attach Playwright over CDP instead. |
| CRUD-16 | JavaScript code sandboxes, CMEK, VPC/PSC, snapshots | Out of skill scope. Do not attempt. | This skill does not cover JS sandboxes, CMEK, VPC, or snapshots. |

## IAM the caller must already have

Do not probe IAM unless they ask. Do not put emails or project ids in flags by
default. Computer Use still requires `--service-account` from the user.

| Who | Role | On | If missing |
|---|---|---|---|
| ADC principal | `roles/aiplatform.user` | project | Control plane 403 |
| ADC principal | `roles/iam.serviceAccountTokenCreator` | **the** JWT service account | CRUD-10 (`signJwt` 403) |
| That service account | `roles/aiplatform.user` | project | CU data plane 401 / forbidden |
| `service-PROJECT_NUMBER@gcp-sa-vertex-sandbox.iam.gserviceaccount.com` | `roles/artifactregistry.reader` | the image repo (or project) | BYOC pull from **your** AR (not needed for Google public AR hello) |

## LRO / logging (do not mislead)

- In-progress LROs **omit** `done` (CRUD-4).
- West4 shell/CU: LRO later `done=true` with `error.code=10 message=ABORTED`;
  template state `FAILED`. A 40 minute wait does not help (CRUD-6, CRUD-12).
- Cloud Audit records create start and end as OK/`NOTICE` even when the LRO
  aborted. **`ABORTED` is only on the Operations resource**, not in logs.
- Official sandbox-creation troubleshooting (IAM, location, missing engine,
  quota) does not match this failure. `europe-west4` is a documented sandbox
  region.

## Exec / Computer Use skills

Use **gcp-agent-sandbox-exec** and **gcp-agent-sandbox-computer-use**. They call
the same `gcp-agent-sandbox` CLI (install it first; it is not bundled in the
skill folders).

- Python exec: only if you have a **RUNNING** code sandbox; decode execute
  output as UTF-8 JSON `msg_out` (not raw `model_dump`).
- Bash: only RUNNING **shell** sandbox (CRUD-9).
- Browser: only RUNNING **Computer Use** sandbox + JWT (CRUD-10). Proven
  Playwright call is `chromium.connect_over_cdp` with the SDK WS URL and
  `Sec-WebSocket-Protocol`. US only until EU templates work.
