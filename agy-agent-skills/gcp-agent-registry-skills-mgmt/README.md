# GCP Agent Registry skill

Portable [Agent Skill](https://agentskills.io/specification) so any harness (Cursor, Claude, Agy, and similar) can **search and CRUD skills** in [GCP Agent Registry](https://docs.cloud.google.com/agent-registry/search-agents-and-tools) using the **live v1alpha API**, including mismatches with the public docs.

## Goal

Agents should not copy broken gcloud/`query` examples from the docs. This skill:

- Onboards with **Application Default Credentials** (no pasted tokens, no service-account JSON in chat)
- Uses `gcp-agent-registry-skill/scripts/registry.py` for list, keyword/semantic search, get, create, activate, patch, revisions, download, and delete
- Warns the user before known-broken actions (semantic search outside `eu`, create as ACTIVE, publisher filter, and the rest in `gcp-agent-registry-skill/references/issues.md`)

The official Python package `google-cloud-agentregistry` is **v1-only** and has **no Skills API**. Skills exist only on `https://agentregistry.googleapis.com/v1alpha`. The helper stays on REST.

## What is in this folder

`agy-agent-skills/gcp-agent-registry-skills-mgmt/` holds the skill package plus human-only docs and tests. Agy should load **only** `gcp-agent-registry-skill/` (it contains `SKILL.md`).

| Path | Role |
|---|---|
| [`gcp-agent-registry-skill/`](gcp-agent-registry-skill/) | Agent skill (`SKILL.md`, scripts, references, demo assets) |
| [`README.md`](README.md) | Human onboarding (not part of the skill) |
| [`agent-registry-skill-search.md`](agent-registry-skill-search.md) | Evidence log of REST calls (not part of the skill) |
| [`tests/`](tests/) | Unit tests for `registry.py` (no live GCP; not part of the skill) |

## Technical setup

- Python 3.10+
- [Google Cloud SDK](https://cloud.google.com/sdk) (`gcloud`)
- ADC:

  ```bash
  gcloud auth application-default login
  gcloud auth application-default set-quota-project PROJECT_ID
  ```

- IAM: `roles/agentregistry.viewer` to search; `roles/agentregistry.user` to create/update/delete
- Network access to `agentregistry.googleapis.com`
- `registry.py` needs **no pip packages**. Do not install `google-cloud-agentregistry` for skills.

Three rules that match the live API:

1. **Semantic search only returns results in `eu`.** Keyword search works in `global`, `us`, and `eu`.
2. **Always set `searchType`** (`KEYWORD` or `SEMANTIC`). Omitting it behaves like semantic.
3. **Pass `filter=state=ACTIVE`** (the script does this by default) or disabled/deprecated skills stay searchable.

## Use the skill locally (Agy / Antigravity CLI)

The skill lives at `agy-agent-skills/gcp-agent-registry-skills-mgmt/gcp-agent-registry-skill/` in this demo-pack repo. Start an **Agy** session at the **repository root** (not inside this folder). You talk to the agent; it runs `scripts/registry.py` from that skill folder. You do not invoke that script.

### Prerequisites

Install these on your machine before the first session:

1. **Python 3.10+** (the skill’s helper is stdlib-only; no extra pip packages for runtime).
2. **Google Cloud SDK** (`gcloud`) and **Application Default Credentials** for the GCP project that hosts Agent Registry:

   ```bash
   gcloud auth application-default login
   gcloud auth application-default set-quota-project PROJECT_ID
   ```

   Your account needs `roles/agentregistry.viewer` to search and `roles/agentregistry.user` to create/update/delete skills.

3. **Antigravity CLI (`agy`)** — [install docs](https://antigravity.google/docs/cli/install/):

   ```bash
   # macOS / Linux
   curl -fsSL https://antigravity.google/cli/install.sh | bash
   agy --version
   ```

   On first launch, complete **Agy** Google sign-in (OAuth in the browser). That authenticates the harness. ADC (step 2) is what the skill uses for Agent Registry API calls — both are required.

4. Clone or open **this repository** (`demo-pack`) and `cd` into the repo root (so `agy-agent-skills/gcp-agent-registry-skills-mgmt/gcp-agent-registry-skill/` is on disk).

### Start a session

```bash
cd /path/to/demo-pack
agy
```

In the TUI, confirm the skill is visible:

```
/skills
```

You should see `gcp-agent-registry`. Press `Esc` to leave the skills list. If Agy asks to allow the skill, approve it.

Use **location `eu`** if you need semantic search (it returns empty results in `global` and `us`). Keyword search works in all three.

### Sample prompt

Paste this into the `agy` session (replace the project ID):

```
Use the gcp-agent-registry skill. My GCP project is PROJECT_ID, location eu,
and auth is Application Default Credentials.

List the first-party GKE skills, then semantic-search for skills that help
write a professional email. Summarize the top hits. Warn me if anything you
would do is a known Agent Registry API issue.
```

The agent should collect project/location/ADC, call the registry through the skill, and surface issues (for example semantic-only-in-`eu`) instead of following outdated public-doc examples.

More prompt ideas: [`gcp-agent-registry-skill/references/prompts.md`](gcp-agent-registry-skill/references/prompts.md).

When finished: `/exit`.

## Tests

Unit tests mock ADC and HTTP. They never call Agent Registry.

From this folder:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```
