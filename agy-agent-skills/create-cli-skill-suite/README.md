# create-cli-skill-suite (factory)

Factory [Agent Skill](https://agentskills.io/specification) for **Google
Antigravity (`agy`)**. Given a remote API and the features you want, it grills
for scope, live-verifies with the official Python SDK, then produces a
**Python argparse CLI + npx-installable skills** suite.

This folder has **no Python package**. Load the skill with npx only.

## Load in Agy

From the Antigravity workspace that contains this repo (typically the
demo-pack root):

```bash
cd /path/to/demo-pack
npx skills add ./agy-agent-skills/create-cli-skill-suite -a antigravity-cli
agy
```

Confirm `/skills` lists `create-cli-skill-suite`. Restart `agy` after npx if it
was already running.

After merge to `main`, a GitHub tree URL pointing **at this suite** (it has
`skills/`):

```bash
npx skills add https://github.com/se02035/demo-pack/tree/main/agy-agent-skills/create-cli-skill-suite -a antigravity-cli
```

Avoid `/` in branch names in tree URLs. Do not `npx skills add se02035/demo-pack`
from the repo root (`skills/` is nested). Do not symlink by hand.

## First prompt

```
/create-cli-skill-suite I want a CLI skill suite for <remote API> that can <ship-bar>.
```

The agent should **grill** (ask, not build), then present a scope brief. It
must not write product files or run live probes until you accept the scope
brief and spec sheet.

MCP-only or prompt-only skills are out of scope for this factory.

## What this skill produces

Generated suites default to `agy-agent-skills/<slug>/` (or a path you name):

```
<suite>/
  pyproject.toml          # pip install -e .  (CLI)
  src/<pkg>/
  tests/
  skills/<skill>/SKILL.md
  README.md               # pip then npx
```

Those suites are two-step: **pip the CLI**, then **npx the skills**. This
factory README is npx-only.

## Layout of this factory

| Path | Role |
|---|---|
| `skills/create-cli-skill-suite/SKILL.md` | Process gates |
| `skills/create-cli-skill-suite/references/` | Discovery, spec, verification, packaging, templates |

The factory is self-contained. It does not depend on any other suite in this
repo.
