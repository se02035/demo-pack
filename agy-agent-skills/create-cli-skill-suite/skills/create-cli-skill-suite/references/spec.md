# Spec sheet and skill split

From the **accepted scope brief**, propose every Agent Skills frontmatter field
plus suite/CLI names and a one-vs-many split. Present **one sheet** (not a quiz).
**User must accept or object.** Do not proceed on inferred names alone.

Fill [templates/spec-proposal.md](templates/spec-proposal.md).

Official fields: [Agent Skills `SKILL.md` specification](https://agentskills.io/specification).

## Fields (every generated skill)

| Field | Rule |
|---|---|
| `name` | Required. 1–64 chars, lowercase letters/numbers/hyphens, no leading/trailing hyphen, no `--`. Must match the skill directory |
| `description` | Required. 1–1024 chars. What it does **and when to use it**, with match keywords. Not a one-line stub |
| `license` | Optional. Propose `Apache-2.0` unless the user named another |
| `compatibility` | Optional, max 500. Python 3.10+, suite CLI install line, auth mechanism, network/API host. Confirm |
| `metadata.version` | Propose `"1.0"`. CLI `--version` must match |
| `allowed-tools` | Omit unless the user asks (experimental) |

Suite-level (still on the sheet):

- **Suite directory** — `agy-agent-skills/<suite>/` unless the user names another path
- **CLI / Python package** — unique kebab/snake pair (`{{CLI}}` / `{{PKG}}`); **one CLI** for the suite
- **Issue-id prefix** — uppercase product slug (`ACME-1`). Shared across skills
- **Smoke prefix** — `agy-<slug>-` unless the user names another
- **Confirm flag** — often `--yes` (user can object)

Infer GitHub org/repo from remotes if present; still confirm on the sheet.

## Naming schema (user can object)

- Product **slug** from purpose: short kebab-case (`acme-widgets`)
- **Suite** = slug. **CLI** = same slug. **Package** = snake (`acme_widgets`)
- **Skills** = `<slug>-<group>` (`acme-widgets-crud`, `acme-widgets-query`)
- Skill folder name **equals** `name`
- Cross-skill pointers use those names (“create with `<slug>-crud` first”)

## When to suggest multiple skills

Propose a split (do not silently split) when **any** of these hold:

- Different remote systems (two APIs, or control plane vs data plane)
- Different action groups with different prerequisites or auth
- One `SKILL.md` would exceed ~500 lines for a single job

Keep **one CLI**. Do not split only because one API has many subcommands.

Show Option A (split) and Option B (single skill) as a table: `name`, one-line
job, remote system, example description keywords.

## Confirm / object

- Accept → verification plan uses those names
- Object (rename, merge, regroup, license) → revise and confirm again
- After probes, if a new remote system or cleaner split appears, **re-propose**
  and wait. Do not invent extra skills after acceptance without asking

Do not write `SKILL.md`, `pyproject.toml`, or directories until the latest
sheet is accepted.
