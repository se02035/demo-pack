# TDD the packaged CLI

Do this **after** the user accepts the implementation plan. Mock the **SDK
client**. No live network in pytest.

Copy-adapt [templates/test_cli.py](templates/test_cli.py) and
[templates/cli.py](templates/cli.py).

## Required tests

- `help` exits 0 and **does not** construct the client
- `--version` exits 0, prints `{{VERSION}}`, **does not** construct the client
- `help` JSON includes command names, `required_flags`, `issues[]` where
  applicable
- `help` JSON contains **no** live account, principal, or operation strings
  from verification
- API commands require environment flags (parser has no hidden defaults)
- Client-side refuse for known-broken calls (cite issue id; non-zero; JSON
  `error` + `issue`)
- Confirm flag required on deletes

Then: `python3 -m pip install -e ".[dev]"` and `python3 -m pytest` plus
`python3 -m mypy src tests` (`mypy --strict` via [templates/mypy.ini](templates/mypy.ini);
[templates/pytest.ini](templates/pytest.ini) sets `pythonpath = src`).

Public functions get Google-style docstrings. `__version__` in
`{{PKG}}/__init__.py` matches skill `metadata.version` and CLI `--version`.
