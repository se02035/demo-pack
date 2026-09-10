# Sandbox API evidence (human-only)

Live checks on 2026-09-10 against project `crafty-progress-421108` using ADC
(`gcloud auth application-default print-access-token`). This file is **not** a
skill. Do not copy the project id into `SKILL.md` or prompts.

## Readonly (planning)

- Vertex AI API enabled (`aiplatform.googleapis.com`).
- `gcloud ai reasoning-engines` is not a valid command group.
- `GET …/reasoningEngines` and sandbox collections return HTTP 200 in
  `us-central1`, `us-east1`, `us-west1`, `europe-west1`. `global` → 404.
- Existing demo engines had zero sandboxes; smoke used dedicated empty hosts
  with display-name prefix `agy-sandbox-host-`.

## Stage 1 CRUD smoke (create / pause / resume / delete)

Sequential **US then EU**. No `:execute`, `/exec`, or Computer Use data plane.

### What worked (both regions unless noted)

Control plane: `https://{LOCATION}-aiplatform.googleapis.com/v1beta1/…`

Headers: `Authorization: Bearer ADC`, `x-goog-user-project: crafty-progress-421108`.

| Call | Body / notes |
|---|---|
| `POST …/reasoningEngines` | `{"displayName", "description"}`. LRO name nested under the engine. |
| `POST …/sandboxEnvironmentTemplates` | Shell: `defaultContainerCategory=DEFAULT_CONTAINER_CATEGORY_SHELL_SANDBOX`. Computer Use: `DEFAULT_CONTAINER_CATEGORY_COMPUTER_USE` + `egressControlConfig.internetAccess=true`. LRO at `…/locations/{loc}/operations/{op}` (not under the engine). Often **several minutes**. |
| `POST …/sandboxEnvironments` shell | `spec.shellEnvironment: {}` + template + `ttl: 3600s`. GET has `connectionInfo.loadBalancerHostname` + `routingToken`. |
| `POST …/sandboxEnvironments` code | `spec.codeExecutionEnvironment.codeLanguage=LANGUAGE_PYTHON` + ttl. **No** `connectionInfo` on GET. |
| `POST …/sandboxEnvironments` Computer Use | Template + `displayName` + `ttl` **only**. GET has `connectionInfo`. |
| `POST {sandbox}:pause` / `:resume` | Body `{}`. Wait for `STATE_PAUSED` / `STATE_RUNNING`. |
| `DELETE` sandboxes, then templates, then engine | 200 + LRO. |

Returned resource names use project **number** `149377925365`, not the project id.
In-progress LROs **omit** `done` (they do not send `done: false`).

### What failed

`spec.computerUseEnvironment: {}` on sandbox create → HTTP 400
`Computer Use Environment is not supported.` (CRUD-2). Documented in the CRUD
skill `references/issues.md`.

Live BYOC was not attempted (no Artifact Registry image supplied).

### Cleanup

On failure, list engines whose `displayName` starts with `agy-sandbox-host-` and
delete leftover sandboxes, templates, then engines. First US attempt used this
path after CRUD-2; leftovers were removed before EU.

## Not verified in Stage 1

- `:execute` / bash `/exec` (Stage 2)
- JWT / CDP / VNC (Stage 3)
- Whether `:execute` 404 when `connectionInfo` is missing (code sandboxes have
  no `connectionInfo`; tracked for exec)

### europe-west1 (2026-09-10)

- `POST reasoningEngines` and engine delete work.
- Shell sandbox create **without** a template: HTTP 400
  `Either sandbox environment template or snapshot needs to be provided`.
- Explicit shell template create LRO: polled ~10 minutes with `done` omitted,
  then `error.code=10 ABORTED`.
- Code sandbox create LRO: same `ABORTED` after ~2.5 minutes.
- Leftover `agy-sandbox-host-*` engines were deleted.

Delete order: sandboxes → templates → engine.

## CLI SDK rewrite (2026-09-10)

`gcp-agent-sandbox` is argparse over `agentplatform.Client` (`api_version=v1`),
not stdlib REST. Unit tests mock the Client (no live GCP).

CLI re-smoke (this section): code create + `execute_code` in `us-central1` and
`europe-west4` via the rewritten CLI, then delete. Shell/CU template behaviour
was already measured in the 40-minute west4 run and is not repeated here.

Prefix `agy-sandbox-host-cli-*`. Both regions: engine create → code sandbox
`STATE_RUNNING` → `exec code print(2+2)` → `msg_out` `4\n` (`exit_status_int` 0)
→ sandbox delete `--yes` → engine delete `--yes`. Wall time ~32s for both
regions sequential. Zero leftover `agy-sandbox-host*` engines afterward.

| Location | Engine | Code sandbox | `execute_code` |
|---|---|---|---|
| `us-central1` | `…/reasoningEngines/1739319093246296064` | `…/sandboxEnvironments/5394468478415536128` | `4\n` |
| `europe-west4` | `…/reasoningEngines/3612001250360426496` | `…/sandboxEnvironments/5986128329705521152` | `4\n` |


