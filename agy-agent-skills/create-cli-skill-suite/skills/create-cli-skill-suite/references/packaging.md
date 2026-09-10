# Packaging (Python CLI + npx)

Emit this stack from [templates/](templates/). Replace `{{SLUG}}`, `{{PKG}}`,
`{{CLI}}`, `{{PREFIX}}`. Do not point at another suite.

## Python stack

| Piece | Rule |
|---|---|
| Language | Python 3.10+ |
| Layout | `src/{{PKG}}/` (`__init__.py`, `__main__.py`, `cli.py`) + `tests/` + `skills/` |
| Packaging | `pyproject.toml` (setuptools src layout), `[project.scripts]` unique command, `python3 -m {{PKG}}` fallback |
| CLI | `argparse`; JSON stdout; warnings on stderr; `help` catalog; `--version`; required env flags with **no** hidden defaults |
| Types / docs | `mypy --strict`; Google-style docstrings on public functions |
| Tests | pytest; mock the SDK client; no live network |
| Deps | Official Python SDK in `[project] dependencies`; `requirements.txt` is `-e .`; `.[dev]` for pytest/mypy |
| Gitignore | `*.egg-info/`, `_probe_*.py`, `_smoke_*.py`, `*-api-evidence.md` |

## `help` catalog (JSON)

Each command:

- `name`, `summary`, `when`
- `required_flags`, `optional_flags`
- `placeholders` (never real ids)
- `example`
- `issues[]` (`id`, `workaround`)

`help` and `--version` **must not** construct the SDK client.

## Errors

Non-zero exit on refuse/error. Stdout JSON:

```json
{"error": "plain language", "issue": "ACME-1"}
```

`issue` is `null` when no known-issue id applies.

Confirm flag name comes from the spec sheet (often `--yes`).

## npx layout (required)

```
<suite>/
  pyproject.toml
  src/<pkg>/
  tests/
  skills/
    <skill-a>/SKILL.md
    <skill-a>/references/limitations.md
    <skill-a>/references/issues.md
    <skill-a>/references/api-mapping.md
  README.md
```

`npx skills add` copies **only** each skill folder. No shims to `src/` or
sibling skills. Duplicate limitations and issues into every skill.

Agy loads **`<launch-cwd>/.agents/skills/`**. README must say:

1. `python3 -m pip install -e /path/to/<suite>` (same `python3` agy uses)
2. From the workspace you will launch `agy` in:
   `npx skills add /path/to/<suite> -a antigravity-cli`
3. Restart `agy`. Check `/skills`.

Do not tell users to `ln -sf`. Do not document repo-root
`npx skills add owner/repo` unless `skills/` is at the repo root. Avoid `/` in
git branch names in GitHub tree URLs; prefer `main`.

Two-step is intentional: npx does not install the Python CLI.

Copy [templates/README.md](templates/README.md) for generated suites (pip then
npx). See [templates/INDEX.md](templates/INDEX.md) for which template becomes
which generated path. This factory’s own README is npx-only (no CLI).
