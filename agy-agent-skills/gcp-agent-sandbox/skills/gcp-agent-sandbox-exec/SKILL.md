---
name: gcp-agent-sandbox-exec
description: >-
  Execute Python via execute_code and bash via execute_bash in Gemini Enterprise
  Agent Platform sandboxes using the gcp-agent-sandbox CLI (agentplatform.Client
  v1). Code exec works in us-central1 and europe-west4. Bash requires a RUNNING
  shell sandbox (US today; EU shell templates fail). Use when the user asks to
  run code or a shell command inside an Agent Platform sandbox.
license: Apache-2.0
compatibility: >-
  Python 3.10+, the gcp-agent-sandbox CLI
  (`python3 -m pip install -e <path-to-the-suite>`), gcloud ADC, network to
  {location}-aiplatform.googleapis.com. There is no gcloud sandbox CLI.
metadata:
  version: "1.0"
---

# GCP Agent Platform sandbox exec

Run **Python** (`exec code`) or **bash** (`exec bash`) in an existing sandbox.
Prefer **`gcp-agent-sandbox`** over inventing curl. Before any call, apply
[references/limitations.md](references/limitations.md) (CRUD-6, CRUD-8, CRUD-9).

Create sandboxes with **gcp-agent-sandbox-crud** first. Reuse the engine/sandbox
name from this conversation.

## CLI required

1. Run `gcp-agent-sandbox help exec`, or `python3 -m gcp_agent_sandbox help exec`.
2. If both fail, **stop**. Do not call GCP. Do not invent curl. Tell the user to
   `python3 -m pip install -e /path/to/demo-pack/agy-agent-skills/gcp-agent-sandbox`
   using the same Python as this harness.

## Hard rules

- `--project` and `--location` required. No defaults. No US failover for EU.
- `exec code` only on a **RUNNING code** sandbox. Decode stdout is `msg_out`
  from Chunk JSON (do not `model_dump` Chunks).
- `exec bash` only on a **RUNNING shell** sandbox. Refuse on code (CRUD-9).
- In `europe-west4`, offer Python exec. Do not wait on shell templates (CRUD-6).
- `help` first if flags are unclear (no Client/ADC).

```bash
gcp-agent-sandbox help exec
gcp-agent-sandbox --project PROJECT_ID --location LOCATION \
  exec code SANDBOX --engine ENGINE --code 'print(2+2)'
gcp-agent-sandbox --project PROJECT_ID --location LOCATION \
  exec bash SANDBOX --engine ENGINE --command 'echo ok && pwd'
```

Fallback: `python3 -m gcp_agent_sandbox` with the same arguments.

Non-zero `exit_status_int` / `returncode` is a failed **program**, not an RPC error.

## Sample prompts

- Run `print(2+2)` in code sandbox SANDBOX in project PROJECT_ID location us-central1.
- Same Python exec in europe-west4.
- Run `echo ok && pwd` in shell sandbox SANDBOX (US). If the sandbox is code, refuse.
