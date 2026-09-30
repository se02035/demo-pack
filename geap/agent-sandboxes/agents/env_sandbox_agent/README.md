# Environment Toolset + session sandboxes

Small ADK demo: a custom [`BaseEnvironment`](https://adk.dev/integrations/environment-toolset/)
backed by [Agent Platform sandboxes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sandbox).
Each Playground session gets two sandboxes, created on first use:

| Flavour | Display name | Tools |
| --- | --- | --- |
| Shell | `sandbox-{session_id}-shell` | `shell_Execute`, `shell_ReadFile`, `shell_WriteFile`, `shell_EditFile` |
| Code | `sandbox-{session_id}-code` | `code_Execute` (Python source), `code_ReadFile`, … |

Platform resource names are stored in session state (`sandbox_shell` /
`sandbox_code`) so a reloaded session reuses the same sandboxes. Session B
never receives session A's resource names.

This is intentionally thinner than [`sandbox_agent`](../sandbox_agent/) (no
pause/snapshot/reaper). Use that agent for the full lifecycle demo.

## Prerequisites

- Python 3.11–3.13
- Agent Platform API enabled on your GCP project
- Application Default Credentials with `roles/aiplatform.user`

```bash
# From geap/agent-sandboxes
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_GCP_PROJECT_ID

# One-time runtime (shared with sandbox_agent if you already have one)
python scripts/bootstrap_runtime.py
```

Copy [`.env.example`](.env.example) to `.env` and set `GOOGLE_CLOUD_PROJECT` and
`SANDBOX_RUNTIME_NAME`. Do not commit `.env`.

## Run

```bash
source .venv/bin/activate
cd agents
adk web --port 8765 --no-reload
```

Open the UI, select `env_sandbox_agent`, and try:

1. **Session A:** write `/workspace/secret-a.txt` with unique text via the shell
   tools, then read it back. Optionally run a one-liner with `code_Execute`.
2. **Session B (new chat):** try to read `/workspace/secret-a.txt` — it must not
   exist on B's sandbox.
3. Return to **Session A** — the same file is still there (same sandbox from
   session state).

## Isolation test (ADC, no LLM)

```bash
# From geap/agent-sandboxes, with agents/env_sandbox_agent/.env configured
pytest tests/integration/test_env_toolset_isolation.py -m integration -v
```

The test binds two in-memory sessions, writes a marker through the shell
environment on A, asserts B cannot read it, and checks distinct
`sandbox_shell` bindings.
