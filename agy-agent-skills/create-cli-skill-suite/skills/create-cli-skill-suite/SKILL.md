---
name: create-cli-skill-suite
description: >-
  Factory that builds a CLI skill suite for a remote API: Python argparse CLI
  plus npx-installable Agent Skills. Use when the user wants to create a CLI
  skill suite, wrap a REST/gRPC/proprietary API, live-verify with an official
  Python SDK, ship a known-issues contract, or `npx skills add` a generated
  suite. Do not use for MCP-only or prompt-only skills. Grill for scope, infer
  names, live-verify before packaging. Read references/process.md before
  writing files.
license: Apache-2.0
compatibility: >-
  Google Antigravity (agy). Python 3.10+ is required only when this skill
  later generates a product CLI (not to load the factory). Load with
  `npx skills add ./agy-agent-skills/create-cli-skill-suite -a antigravity-cli`.
  This factory has no Python package.
metadata:
  version: "1.0"
---

# Create a CLI skill suite

Build a **Python CLI + Agent Skills** suite for a **remote API**. Target harness
is **Google Antigravity (`agy`)** only.

This factory is **self-contained**. Do not open, link to, or copy from another
suite. Illustrations use the fictional slug `acme-widgets` only.

If the user wants an **MCP-only** or **prompt-only** skill, **stop**. This
factory is the wrong tool.

## Stop until the user accepts

Do **not** write the product suite (`SKILL.md`, `pyproject.toml`, directories)
and do **not** run live probes until:

1. A **scope brief** is accepted ([references/discovery.md](references/discovery.md)).
2. A **spec sheet** (names, split, CLI) is accepted ([references/spec.md](references/spec.md)).
3. Identity and target environment are stated (grill if missing).

Do **not** ship a packaged CLI until the verification matrix has been **executed**
(each ship-bar row ran: success **or** recorded failure with an issue id) and
the user accepts the **implementation plan**.

## Process (one screen)

1. **Seed** — take what they already said. Do not re-ask. No secrets in chat.
2. **Grill** — `/grill-me` posture. [references/discovery.md](references/discovery.md).
   No probes, no files. Present a **scope brief**. Wait.
3. **Spec sheet** — infer names, descriptions, split from the brief.
   [references/spec.md](references/spec.md). Wait.
4. **Verification plan** — matrix of skill × ship-bar → SDK/HTTP call.
   Show it, then probe. [references/verification.md](references/verification.md).
5. **Live probes** — official Python SDK first. Throwaway `_probe_*.py`
   (gitignored). Complete ≠ every row green. Assign issue ids on failures.
6. **Implementation plan** — only proven calls become CLI commands. Failed rows
   become known issues. If probes imply a new split, re-propose. **Wait.**
7. **TDD CLI** — mock the SDK. `help`/`--version` skip the client.
   [references/tdd.md](references/tdd.md) + [references/packaging.md](references/packaging.md).
8. **Skills** — suite-root `skills/`. Duplicate limitations + issues into each
   skill. Prerequisite gate. Fail closed if CLI missing (do not invent curl).
9. **Smoke** — packaged CLI, then delete with the confirm flag. Cleanup
   `agy-<slug>-` resources.

Copy-adapt from [references/templates/](references/templates/) (see
[references/templates/INDEX.md](references/templates/INDEX.md)). Replace
`acme-widgets` / `acme_widgets` / `ACME` with the accepted spec sheet.

## Rules (do not skip)

- [references/learnings.md](references/learnings.md) — live API wins; no silent
  failover; cap waits; npx copies **only** the skill folder.
- [references/auth.md](references/auth.md) — harness login ≠ API creds.
- [references/prerequisites.md](references/prerequisites.md) — generated skills
  **ask and stop** before long-running calls.
- [references/known-issues.md](references/known-issues.md) — every probe finding
  ships in the skill (`issues.md` + `limitations.md` + issue gate + `help.issues[]`
  + CLI refuse).
- Factory text stays **product-agnostic**. Product-specific clients, regions,
  and issue ids belong only in the **generated** suite after probes.

## Generated suite layout

```
<suite>/
  pyproject.toml
  src/<pkg>/
  tests/
  skills/<skill-a>/SKILL.md
  README.md
```

Install for agy: **pip CLI**, then `npx skills add <suite> -a antigravity-cli`.
Never advertise npx as installing Python.
