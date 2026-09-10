# GCP Agent Platform sandbox skills

Portable [Agent Skills](https://agentskills.io/specification) so any harness
(Cursor, Claude, Agy, and similar) can **CRUD, execute in, and drive Computer Use
sandboxes** on [Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sandbox/manage-sandboxes)
using the **`gcp-agent-sandbox` CLI** (`agentplatform.Client`, API v1), including
mismatches with the public docs.

This folder is a **two-step** suite: install the Python CLI, then install the
skill packages. The skills call the CLI; they do not bundle `sandbox.py`.

## What is in this folder

| Path | Role |
|---|---|
| [`src/gcp_agent_sandbox/`](src/gcp_agent_sandbox/) | Installable CLI package |
| [`skills/gcp-agent-sandbox-crud/`](skills/gcp-agent-sandbox-crud/) | CRUD skill |
| [`skills/gcp-agent-sandbox-exec/`](skills/gcp-agent-sandbox-exec/) | Exec skill (`exec code` / `exec bash`) |
| [`skills/gcp-agent-sandbox-computer-use/`](skills/gcp-agent-sandbox-computer-use/) | Computer Use skill (JWT / CDP / Playwright) |
| [`skills/gcp-agent-sandbox-crud/references/limitations.md`](skills/gcp-agent-sandbox-crud/references/limitations.md) | **Agent contract** — what works where (copy also lives in exec and computer-use) |
| [`README.md`](README.md) | This runbook (not part of a skill) |
| [`sandbox-api-evidence.md`](sandbox-api-evidence.md) | Live API notes (not part of a skill) |
| [`tests/`](tests/) | Unit tests (mocked Client; no live GCP) |

Maintainer note: when you edit limitations, copy the file into all three skill
`references/` folders.

There is **no** `gcloud` sandbox / reasoning-engines CLI.

## Use with Agy

### Prerequisites

- Python 3.10+
- Node.js / `npx`
- [Google Cloud SDK](https://cloud.google.com/sdk) (`gcloud`)
- [Antigravity CLI (`agy`)](https://antigravity.google/docs/cli/install/):

  ```bash
  curl -fsSL https://antigravity.google/cli/install.sh | bash
  agy --version
  ```

- ADC for the GCP project that hosts Agent Platform:

  ```bash
  gcloud auth application-default login
  gcloud auth application-default set-quota-project PROJECT_ID
  gcloud auth application-default print-access-token >/dev/null
  ```

- IAM: `roles/aiplatform.user` on the project. Computer Use also needs Token
  Creator on the SA you pass as `--service-account` (never default an SA).

Agy Google sign-in authenticates the harness. ADC authenticates Vertex AI. Both
are required.

### Step 1 — Install the Python CLI

Use the **same `python3` Agy will use to run tools**. From this folder:

```bash
cd /path/to/demo-pack/agy-agent-skills/gcp-agent-sandbox
python3 -m pip install -e .
gcp-agent-sandbox --version
gcp-agent-sandbox help
```

`help` and `--version` need **no** ADC. If the `gcp-agent-sandbox` binary is
not on `PATH`, use:

```bash
python3 -m gcp_agent_sandbox --version
python3 -m gcp_agent_sandbox help
```

Until this lands on `main`, you can install the CLI from the feature branch:

```bash
python3 -m pip install "git+https://github.com/se02035/demo-pack.git@feat/agent-sandbox-skill#subdirectory=agy-agent-skills/gcp-agent-sandbox"
```

### Step 2 — Install the skills into the Agy workspace

Agy loads workspace skills from **`<workspace>/.agents/skills/`**. This suite’s
skill packages live under `skills/`. Run `npx skills add` from the directory
you will launch `agy` in (typically the **demo-pack** repo root):

```bash
cd /path/to/demo-pack
npx skills add ./agy-agent-skills/gcp-agent-sandbox -a antigravity-cli
```

Confirm `.agents/skills/` contains `gcp-agent-sandbox-crud`,
`gcp-agent-sandbox-exec`, and `gcp-agent-sandbox-computer-use`.

Do not symlink skill folders by hand. `npx skills add se02035/demo-pack` from
the GitHub repo root will not find these packages (`skills/` is nested in this
suite, and the feature branch name contains a slash).

### Step 3 — Start Agy and check the skills

```bash
cd /path/to/demo-pack
agy
```

In the TUI, run `/skills`. You should see the three names. Approve a skill if
Agy asks. Then:

```
/gcp-agent-sandbox-crud Show me how to invoke the sandbox CLI. Do not call GCP yet.
```

The agent should run `gcp-agent-sandbox help` (or `python3 -m gcp_agent_sandbox
help`) and **not** hit the API.

### Step 4 — First live prompt

Pass `PROJECT_ID` and `LOCATION` yourself (`us-central1` or `europe-west4`). Do
not expect the agent to read `gcloud config`.

```
Onboard me to Agent Platform sandboxes in project PROJECT_ID, location us-central1, using ADC.
Create a dedicated empty sandbox-host engine and a Python code sandbox (TTL 1h).
Run print(2+2). Delete sandbox then engine with --yes when done.
```

Sandboxes **bill while they exist**. Shell and Computer Use templates currently
fail in `europe-west4`; Python code works there. Do not fail EU traffic over to
US unless you explicitly agree.

### Troubleshooting (Agy)

- **Skills missing in `/skills`:** you launched `agy` in a different directory
  than the one that received `.agents/skills/`. Restart `agy` after `npx skills
  add`.
- **Agent says the CLI is missing:** pip used a different Python than Agy.
  Reinstall with that interpreter (`python3 -m pip install -e …`) and retry
  `python3 -m gcp_agent_sandbox help`.
- **`help` works but API calls fail:** ADC, quota project, or
  `roles/aiplatform.user`.

## CLI without a harness

```bash
gcp-agent-sandbox help
gcp-agent-sandbox --project PROJECT_ID --location LOCATION engines list
```

`--project` and `--location` are required on API commands. Deletes need `--yes`.

## Tests (developers)

```bash
cd /path/to/demo-pack/agy-agent-skills/gcp-agent-sandbox
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m mypy src tests
```

No live GCP in pytest.

## Rules that match the live API

1. **Always pass `--location`.** Sandboxes are regional. `us-central1` and
   `europe-west4` are independent. There is no `global` sandbox API. Shell and
   Computer Use **templates currently fail** in `europe-west4`; Python code
   sandboxes work. Do not fail EU over to US. See
   [`skills/gcp-agent-sandbox-crud/references/limitations.md`](skills/gcp-agent-sandbox-crud/references/limitations.md).
2. **Never infer project, location, or engine.** Ask the user. Do not read
   `gcloud config`.
3. **Deletes require `--yes`.** Sandboxes bill while they exist; prefer TTL and pause.
