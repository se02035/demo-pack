---
name: acme-widgets-crud
description: >-
  Create, list, get, and delete Acme Widgets via the acme-widgets CLI.
  Use when the user mentions Acme Widgets, widget CRUD, or the widgets API.
  Read references/limitations.md before mutate. Prefer this skill to create
  or tear down widgets.
license: Apache-2.0
compatibility: >-
  Requires Python 3.10+, the acme-widgets CLI
  (`python3 -m pip install -e <path-to-this-suite>`), the product auth
  mechanism documented in Onboarding, and network access to the API host.
  Invoke `acme-widgets` or `python3 -m acme_widgets`.
metadata:
  version: "1.0"
---

# Acme Widgets (CRUD)

Copy-adapt this file. Replace `acme-widgets`, `acme_widgets`, `ACME-`, and
the product words with the **accepted spec sheet**. Keep the section order.

Prefer the **CLI** over inventing curl. When public docs conflict with live
results, follow this skill and
[references/limitations.md](references/limitations.md) (ids in
[references/issues.md](references/issues.md)). Tell the user **before** a
known-broken call.

## CLI required (before any API call)

The CLI is a **separate pip install**, not bundled in this skill folder.

1. Run `acme-widgets help` (no API client). If the binary is missing, run
   `python3 -m acme_widgets help`.
2. If both fail, **stop**. Do not call the API. Do not invent curl. Tell the
   user:

```bash
python3 -m pip install -e /path/to/agy-agent-skills/acme-widgets
```

Install into the **same Python** the harness uses to run tools.

## Known limitations (required)

**Read [references/limitations.md](references/limitations.md) before mutate.**
Act and speak using that table.

## Onboarding (required before any API call)

Collect from the user. **Do not guess** environment or credentials. Do not
read ambient vendor-CLI config.

1. CLI — step above (`help` / `--version` must work).
2. Auth — the mechanism probes proved. Confirm without printing secrets.
   Harness login is not the API credential.
3. Target environment — user-stated flags (no defaults).
4. Permissions — user confirms caller-must-have roles from limitations.
   Do not probe policy unless they ask. Do not grant access.

If anything required is missing, **ask** and show a sample prompt. If flags
are unclear, run `acme-widgets help` first (no client).

## Per-action prerequisites

| Intent | Requires | Cheap preflight | Then |
|---|---|---|---|
| List / get | env flags, auth | `help`; auth presence | API call |
| Create | env flags, auth, extras from `requires:` | same | warn if it bills; then create |
| Delete | env flags, resource name, `--yes` | same | delete |

Do not start a long wait until this row is complete.

## Hard rules

- Required env flags on API commands (no defaults).
- Deletes require `--yes`. Without it, print the name and stop.
- Reuse resource names from this conversation; do not create a new host
  resource per turn without asking.
- Before an API call, apply the **Issue gate**. Docs lose to `limitations.md`.

## Issue gate

Before an action, match it in [references/limitations.md](references/limitations.md).
Tell the user using **Tell the user**, then apply **Agent action** (or stop).
Quote the id.

| User asks to… | Issue |
|---|---|
| Use a vendor CLI probes did not find | ACME-1 |
| (add a row per probe finding) | ACME-N |

API shapes: [references/api-mapping.md](references/api-mapping.md).

## CLI

Prefer `acme-widgets`. Fallback: `python3 -m acme_widgets`.

```bash
acme-widgets help
acme-widgets --<env> VALUE COMMAND
```

| Command | Purpose |
|---|---|
| `widgets create\|list\|get\|delete` | Fill from proven probes |

## Sample prompts

Show these on first use. Full list: [references/prompts.md](references/prompts.md).

- Show me how to invoke the CLI (`acme-widgets help`); do not call the API yet.
- Onboard me to Acme Widgets in environment ENV, using the documented auth.
