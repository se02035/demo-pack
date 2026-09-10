# Spec proposal (fill from accepted scope brief)

Present as one sheet. Wait for accept or object. Do not write product files yet.

Replace tokens after accept: `{{SLUG}}` `{{PKG}}` `{{CLI}}` `{{PREFIX}}` `{{VERSION}}`.

## Suite

| Field | Proposed | Notes |
|---|---|---|
| Suite directory | `agy-agent-skills/{{SLUG}}/` | |
| CLI command | `{{CLI}}` | same as slug |
| Python package | `{{PKG}}` | snake_case |
| Issue prefix | `{{PREFIX}}-` | e.g. `ACME-1` |
| Smoke prefix | `agy-{{SLUG}}-` | |
| Confirm flag | `--yes` | |
| License | Apache-2.0 | |
| Version | `"1.0"` / `1.0.0` | skill metadata and CLI `--version` |
| GitHub (pip / npx) | `https://github.com/{{ORG}}/{{REPO}}` | infer from remotes; confirm |

## Skills

Option A — split:

| `name` | Job | Remote system | Description keywords |
|---|---|---|---|
| `{{SLUG}}-crud` | | | |
| `{{SLUG}}-query` | | | |

Option B — single skill: `{{SLUG}}`

**Recommendation:** A or B because:

## Frontmatter (each skill)

```yaml
name: {{SLUG}}-crud
description: >-
  (what it does AND when to use it; match keywords; 1–1024 chars)
license: Apache-2.0
compatibility: >-
  Python 3.10+, {{CLI}} (`python3 -m pip install -e <path-to-the-suite>`),
  <auth mechanism>, network to <API host>.
metadata:
  version: "1.0"
```

User: **accept Option A / accept Option B / object (edits):**
