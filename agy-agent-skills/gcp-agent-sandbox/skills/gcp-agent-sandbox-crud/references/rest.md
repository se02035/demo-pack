# SDK mapping (`agentplatform.Client` v1)

Client (API commands only; `help` must not construct it):

```python
agentplatform.Client(
    project=PROJECT_ID,
    location=LOCATION,
    http_options={"api_version": "v1"},
)
```

There is no `global` sandbox API. Engine, template, and sandbox must share
`--location`. Prefer `gcp-agent-sandbox` over curl (CRUD-1). Do not use
deprecated `vertexai.Client`.

Known limits (read first): [limitations.md](limitations.md).

Package: `gcp-agent-sandbox` (`google-cloud-aiplatform[agent_engines]>=2.1.0`).

## Resources

| Resource | Name format |
|---|---|
| Engine | `projects/{p}/locations/{l}/reasoningEngines/{id}` |
| Template | `…/reasoningEngines/{e}/sandboxEnvironmentTemplates/{id}` |
| Sandbox | `…/reasoningEngines/{e}/sandboxEnvironments/{id}` |
| LRO | `…/locations/{l}/operations/{op}` (often) |

`{p}` in returned names is often the **numeric project number** (CRUD-3). Engine
CLI output uses **`runtime.api_resource.name`**.

## CLI → SDK

| CLI | SDK |
|---|---|
| `engines create` | `runtimes.create(config={"display_name", "description"?})` |
| `engines list/get/delete` | `runtimes.list/get/delete` (`delete(..., force=True)` after `--yes`) |
| `templates create --kind shell\|computer-use\|byoc` | `sandboxes.templates.create` with `wait_for_completion=False`; CU always `egress_control_config.internet_access=True`; poll until template **ACTIVE** |
| `sandboxes create --kind code` | `spec={"code_execution_environment": {}}` (CRUD-13) |
| `sandboxes create --kind shell` | `spec={"shell_environment": {}}` + ACTIVE template |
| `sandboxes create --kind computer-use` | template only, **no spec** (CRUD-2) |
| `sandboxes pause/resume/wait` | `pause`/`resume` with `wait_for_completion=False`, then `get` until PAUSED/RUNNING. **Refuse code** (CRUD-8) |
| `exec code` | `execute_code`; decode Chunk JSON `msg_out` |
| `exec bash` | `execute_bash` (no SA). Refuse code (CRUD-9) |
| `cu *` | `generate_access_token` + `send_command` / `generate_browser_ws_headers`; `--service-account` required (CRUD-10) |

Never unbounded SDK wait. Caps: 300s LRO, 300s template ACTIVE, 300s sandbox wait.

## Create shapes (SDK dicts)

Code:

```python
spec = {"code_execution_environment": {}}
config = {"display_name": "NAME", "ttl": "3600s", "wait_for_completion": False}
```

Shell:

```python
spec = {"shell_environment": {}}
config = {
    "display_name": "NAME",
    "ttl": "3600s",
    "wait_for_completion": False,
    "sandbox_environment_template": TEMPLATE_NAME,
}
```

Computer Use sandbox: **omit spec**. Template:

```python
config = {
    "wait_for_completion": False,
    "default_container_environment": {
        "default_container_category": "DEFAULT_CONTAINER_CATEGORY_COMPUTER_USE",
    },
    "egress_control_config": {"internet_access": True},
}
```

BYOC image must be Artifact Registry (`*.pkg.dev`). Grant
`roles/artifactregistry.reader` on the repo to
`service-PROJECT_NUMBER@gcp-sa-vertex-sandbox.iam.gserviceaccount.com`.

## Exec / CU

`execute_code` outputs are Chunks whose `data` is UTF-8 JSON
`{"exit_status_int","msg_err","msg_out"}`. Do not print `model_dump` of Chunks
(base64).

`execute_bash` returns `stdout` / `stderr` / `returncode` / `duration_ms`.

CU Playwright: `chromium.connect_over_cdp(url, headers=headers)` where headers
include `Sec-WebSocket-Protocol`. Do not log that header’s value.

## LRO

In-progress operations **omit** `done`. Complete: `done is True`. Errors on the
operation (`error.code` / `error.message`) plus **operation name** (CRUD-12).
Template `ABORTED` is not in Cloud Logging. Listing a template is not ACTIVE
(CRUD-14).
