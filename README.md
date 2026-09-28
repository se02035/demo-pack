# ADK v2 shell-sandbox demo agent

Local Agent Development Kit (ADK) v2 agent that gives each conversation session
its own Gemini Enterprise Agent Platform **shell sandbox**. The agent can report
the sandbox identity, run bash commands, list directories, and read/write text
files. Python code execution is intentionally out of scope.

Hard invariant: **exactly one sandbox per ADK session**, never shared.

## Prerequisites

- Python 3.11–3.13
- A Google Cloud project with the Agent Platform API enabled
- Application Default Credentials and the **Agent Platform User** role
  (`roles/aiplatform.user`)

This repo is configured for:

| Setting | Value |
| --- | --- |
| Project | `crafty-progress-421108` |
| Sandbox region | `us-central1` (not `global`) |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

gcloud config set project crafty-progress-421108
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login
gcloud auth application-default set-quota-project crafty-progress-421108

# Create the Agent Platform runtime once (no agent deployment needed)
python scripts/bootstrap_runtime.py
```

Copy `.env.example` to `agents/sandbox_agent/.env` and paste the printed
`SANDBOX_RUNTIME_NAME`.

## Run the Playground

```bash
source .venv/bin/activate
cd agents
adk web --port 8765 --no-reload
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765), select `sandbox_agent`, and try:

> Which sandbox am I in, and what user am I running as? Then create
> /workspace/notes.txt containing "hello from the playground", read it back,
> list /workspace, and show disk usage and the kernel version.

Open a second session and ask for the sandbox name again — it should differ.

## Run the API server (for tests / curl)

```bash
cd agents
adk api_server --port 8765 --no-reload
```

## Tests

```bash
# Unit + SDK contract (no network)
pytest -m "not integration"

# Live isolation tests (need ADC + real SANDBOX_RUNTIME_NAME)
pytest -m integration
```

## Cleanup

```bash
python scripts/reap_sandboxes.py --list
python scripts/reap_sandboxes.py --delete --older-than-hours 1
```

Sandboxes also expire via the configured TTL (default 1 hour).

## Layout

See `docs` in the project store plan, or:

- `agents/sandbox_agent/` — ADK agent, tools, session sandbox manager
- `scripts/` — bootstrap runtime + reaper
- `tests/unit/` — manager invariant + tool/SDK contract tests
- `tests/integration/` — api_server + live one-sandbox-per-session proof
