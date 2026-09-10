# Template index

Copy-adapt files in this folder into the **generated** suite after the user
accepts the implementation plan. Replace `acme-widgets` / `acme_widgets` /
`ACME` / `ORG` / `REPO` with the accepted spec sheet. Pin the official SDK
extra and version from probes.

| File | Becomes |
|---|---|
| `pyproject.toml` | suite `pyproject.toml` |
| `requirements.txt` | suite `requirements.txt` (`-e .`) |
| `requirements-dev.txt` | suite `requirements-dev.txt` |
| `mypy.ini` | suite `mypy.ini` |
| `pytest.ini` | suite `pytest.ini` |
| `gitignore` | suite `.gitignore` |
| `__init__.py` | `src/<pkg>/__init__.py` |
| `__main__.py` | `src/<pkg>/__main__.py` |
| `cli.py` | `src/<pkg>/cli.py` |
| `test_cli.py` | `tests/test_cli.py` |
| `SKILL.md` | `skills/<name>/SKILL.md` (one per accepted skill) |
| `limitations.md` | duplicated into each skill `references/` |
| `issues.md` | duplicated into each skill `references/` |
| `api-mapping.md` | duplicated into each skill `references/` |
| `prompts.md` | each skill `references/prompts.md` |
| `README.md` | suite `README.md` (pip then npx) |
| `scope-brief.md` | chat artifact during discovery (not shipped) |
| `spec-proposal.md` | chat artifact during spec (not shipped) |

Do not copy this `templates/` folder into the generated suite.
