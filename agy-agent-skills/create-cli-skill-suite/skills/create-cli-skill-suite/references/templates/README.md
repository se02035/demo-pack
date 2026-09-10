# Acme Widgets skills

Copy-adapt this runbook for the **generated** suite. Replace `acme-widgets`,
`acme_widgets`, org/repo, and product words. This factory’s own README is
npx-only; generated suites are **pip then npx**.

Portable [Agent Skills](https://agentskills.io/specification) so Antigravity
(`agy`) can operate the product API via the **`acme-widgets` CLI**.

This folder is a **two-step** suite: install the Python CLI, then install the
skill packages. The skills call the CLI; they do not bundle Python sources.

## What is in this folder

| Path | Role |
|---|---|
| `src/acme_widgets/` | Installable CLI package |
| `skills/acme-widgets-crud/` | Example skill (duplicate limitations/issues into each skill) |
| `README.md` | This runbook (not part of a skill) |
| `*-api-evidence.md` | Live API notes (gitignored; not part of a skill) |
| `tests/` | Unit tests (mocked client; no live network) |

Maintainer note: when you edit limitations, copy the file into all skill
`references/` folders.

## Use with Agy

### Prerequisites

- Python 3.10+
- Node.js / `npx`
- [Antigravity CLI (`agy`)](https://antigravity.google/docs/cli/install/)
- Product auth (see the skill Onboarding). Agy sign-in is **not** the API
  credential.

### Step 1 — Install the Python CLI

Use the **same `python3` Agy will use to run tools**. From this folder:

```bash
cd /path/to/agy-agent-skills/acme-widgets
python3 -m pip install -e .
acme-widgets --version
acme-widgets help
```

`help` and `--version` need **no** API client. If the binary is not on
`PATH`:

```bash
python3 -m acme_widgets --version
python3 -m acme_widgets help
```

After merge to `main`:

```bash
python3 -m pip install "git+https://github.com/ORG/REPO.git@main#subdirectory=agy-agent-skills/acme-widgets"
```

Avoid `/` in branch names in GitHub tree URLs.

### Step 2 — Install the skills into the Agy workspace

Agy loads workspace skills from **`<workspace>/.agents/skills/`**. Run
`npx skills add` from the directory you will launch `agy` in:

```bash
cd /path/to/agy-workspace
npx skills add /path/to/agy-agent-skills/acme-widgets -a antigravity-cli
```

After `main`, a GitHub tree URL pointing **at this suite** (it has `skills/`):

```bash
npx skills add https://github.com/ORG/REPO/tree/main/agy-agent-skills/acme-widgets -a antigravity-cli
```

Do not symlink skill folders by hand. `npx skills add owner/repo` from the
GitHub repo root will not find these packages unless `skills/` is at the repo
root.

### Step 3 — Start Agy and check the skills

```bash
cd /path/to/agy-workspace
agy
```

In the TUI, run `/skills`. Restart `agy` after `npx skills add`. Then:

```
/acme-widgets-crud Show me how to invoke the CLI. Do not call the API yet.
```

The agent should run `acme-widgets help` and **not** hit the API.

### Troubleshooting (Agy)

- **Skills missing in `/skills`:** you launched `agy` in a different directory
  than the one that received `.agents/skills/`. Restart `agy` after npx.
- **Agent says the CLI is missing:** pip used a different Python than Agy.
  Reinstall with that interpreter and retry `python3 -m acme_widgets help`.
- **`help` works but API calls fail:** product auth, not harness login.

## CLI without a harness

```bash
acme-widgets help
acme-widgets --env ENV widgets list
```

Environment flags are required on API commands. Deletes need `--yes`.

## Tests (developers)

```bash
cd /path/to/agy-agent-skills/acme-widgets
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m mypy src tests
```

No live network in pytest.
