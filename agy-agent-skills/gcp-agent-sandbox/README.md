# GCP Agent Platform sandbox skills

Portable [Agent Skills](https://agentskills.io/specification) so any harness
(Cursor, Claude, Agy, and similar) can **CRUD, execute in, and drive Computer Use
sandboxes** on [Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sandbox/manage-sandboxes)
using **`agentplatform.Client` (API v1)** via `scripts/sandbox.py`, including
mismatches with the public docs.

The suite ships **CRUD, exec, and Computer Use** skill packages. They share one
CLI.

## Goal

Agents should not invent gcloud/curl against sandbox APIs. This suite:

- Onboards with **Application Default Credentials** (no pasted tokens, no
  service-account JSON in chat)
- Uses `scripts/sandbox.py` for engines, templates, and sandboxes
- Warns before known-broken actions (see
  `gcp-agent-sandbox-crud/references/limitations.md`; ids in
  `gcp-agent-sandbox-crud/references/issues.md`)

There is **no** `gcloud` sandbox / reasoning-engines CLI. Runtime dependency:
`google-cloud-aiplatform[agent_engines]>=2.1.0` (`requirements.txt`).

## What is in this folder

`agy-agent-skills/gcp-agent-sandbox/` holds the skill packages plus human-only docs
and tests. Agy should load **skill directories that contain `SKILL.md`**.

| Path | Role |
|---|---|
| [`gcp-agent-sandbox-crud/`](gcp-agent-sandbox-crud/) | CRUD skill (`SKILL.md`, shim, references) |
| [`gcp-agent-sandbox-exec/`](gcp-agent-sandbox-exec/) | Exec skill (`exec code` / `exec bash`) |
| [`gcp-agent-sandbox-computer-use/`](gcp-agent-sandbox-computer-use/) | Computer Use skill (JWT / CDP / Playwright) |
| [`gcp-agent-sandbox-crud/references/limitations.md`](gcp-agent-sandbox-crud/references/limitations.md) | **Agent contract** — what works where, required actions, user-facing wording |
| [`scripts/sandbox.py`](scripts/sandbox.py) | Shared argparse CLI over `agentplatform.Client` |
| [`README.md`](README.md) | Human onboarding (not part of a skill) |
| [`sandbox-api-evidence.md`](sandbox-api-evidence.md) | Live API notes (not part of a skill) |
| [`tests/`](tests/) | Unit tests (mocked Client; no live GCP) |

## Technical setup

- Python 3.10+
- [Google Cloud SDK](https://cloud.google.com/sdk) (`gcloud`)
- ADC:

  ```bash
  gcloud auth application-default login
  gcloud auth application-default set-quota-project PROJECT_ID
  ```

- IAM: `roles/aiplatform.user` on the project (Computer Use also needs Token
  Creator on `--service-account`)
- Network access to `{LOCATION}-aiplatform.googleapis.com`
- Runtime: `python3 -m pip install -r requirements.txt`

```bash
python3 -m pip install -r requirements.txt
```

Rules that match the live API:

1. **Always pass `--location`.** Sandboxes are regional. `us-central1` and
   `europe-west4` are independent. There is no `global` sandbox API. Shell and
   Computer Use **templates currently fail** in `europe-west4`; Python code
   sandboxes work. Do not fail EU over to US. See
   [`gcp-agent-sandbox-crud/references/limitations.md`](gcp-agent-sandbox-crud/references/limitations.md).
2. **Never infer project, location, or engine.** Ask the user. Do not read
   `gcloud config`.
3. **Deletes require `--yes`.** Sandboxes bill while they exist; prefer TTL and pause.

## Use the skill locally (Agy / Antigravity CLI)

Skill packages live under `agy-agent-skills/gcp-agent-sandbox/`:
`gcp-agent-sandbox-crud`, `gcp-agent-sandbox-exec`, and
`gcp-agent-sandbox-computer-use`. Start an **Agy** session at the **repository
root**. You talk to the agent; it runs `scripts/sandbox.py` from the skill
folder (the shim). You do not need to invoke the script yourself.

### Prerequisites

1. **Python 3.10+** and `pip install -r agy-agent-skills/gcp-agent-sandbox/requirements.txt`.
2. **Google Cloud SDK** and ADC for the project that hosts Agent Platform
   (commands above). Your account needs `roles/aiplatform.user`.
3. **Antigravity CLI (`agy`)** — [install docs](https://antigravity.google/docs/cli/install/):

   ```bash
   curl -fsSL https://antigravity.google/cli/install.sh | bash
   agy --version
   ```

   Agy Google sign-in authenticates the harness. ADC authenticates Vertex AI.
   Both are required.

4. Open this repository and `cd` to the repo root so
   `agy-agent-skills/gcp-agent-sandbox/` (and its three skill packages) is on disk.

### Start a session

```bash
cd /path/to/demo-pack
agy
```

Example slash / natural-language prompts (placeholders only):

```
/gcp-agent-sandbox-crud Show me how to invoke the sandbox CLI. Do not call GCP yet.
```

```
Create a dedicated empty sandbox-host engine in project PROJECT_ID location us-central1, then a prebuilt shell sandbox with TTL 1h. Delete them when done.
```

## CLI without a harness

From the suite root (`agy-agent-skills/gcp-agent-sandbox/`):

```bash
python3 scripts/sandbox.py help
python3 scripts/sandbox.py --project PROJECT_ID --location LOCATION engines list
```

From the skill directory (same commands via the shim):

```bash
cd gcp-agent-sandbox-crud
python3 scripts/sandbox.py help
```

## Tests (developers)

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
python3 -m mypy scripts tests
```

No live GCP in pytest.
