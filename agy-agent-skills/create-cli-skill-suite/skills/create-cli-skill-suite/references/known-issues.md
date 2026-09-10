# Known issues (every generated skill)

Verification is useless if findings stay in a private evidence file. Fold
**every** live mismatch, auth gap, environment failure, and refused call into
the **output** skills.

Assign ids during probes. Prefix = uppercase slug (`ACME-1`). Never skip a
failed ship-bar row. Adjacent features not on the ship-bar get an
out-of-scope id so the agent does not invent them.

## Ship in each skill folder (duplicate for npx)

| File | Audience | Contents |
|---|---|---|
| `references/issues.md` | Agents | Id, trigger, actual live result, workaround |
| `references/limitations.md` | Agents (**contract**) | Same ids: **When**, **Agent action** (before the API call), **Tell the user**. Plus a **what-works-where** table if probes differ by environment or kind |
| `SKILL.md` | Agents | Onboarding; read limitations before mutate; **issue gate** table; quote the id when stopping |
| `references/api-mapping.md` | Agents | CLI → SDK/HTTP shapes. Not the whole SKILL.md |
| CLI `help` JSON | Agents | `issues[]` per command |
| CLI behavior | Agents | Client-side **refuse** for known-broken calls (cite id); do not rely on opaque HTTP text |

Start from [templates/issues.md](templates/issues.md),
[templates/limitations.md](templates/limitations.md), and the issue-gate in
[templates/SKILL.md](templates/SKILL.md).

## Rules

- Docs lose to live results. Tell the user **before** repeating a failed call.
- Unproven, failed, or adjacent-not-on-ship-bar features stay in the issue
  list — do not omit them from SKILL.md.
- If the user insists on a refused call, **still refuse**, except rows that
  say “only if they explicitly agree.”
- `*-api-evidence.md` is human-only, suite-root, gitignored. Issues and
  limitations stay generic (no baked account/principal/operation defaults).
- Successful probes do not need an issue row unless the docs were wrong
  (then document the working body as a workaround).
- After CLI smoke, add new ids if behavior changed; do not delete ids (mark
  superseded if needed).
- Split suites: keep duplicated `limitations.md` / `issues.md` in sync
  (README maintainer note).

## How to apply a limitations row (generated skill)

1. **Agent action** — do this *before* the API call (or instead of it).
2. **Tell the user** — same turn, plain language, quote the id.
3. If they insist, explain again and still refuse (unless the row allows an
   explicit opt-in).
