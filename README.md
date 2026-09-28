# ADK v2 shell-sandbox demo agent

Local Agent Development Kit (ADK) v2 agent that gives each conversation session
its own Gemini Enterprise Agent Platform **shell sandbox**. The agent can report
the sandbox identity, run bash commands, list directories, and read/write text
files. Python code execution is intentionally out of scope.

Hard invariant: **exactly one sandbox per ADK session**, never shared.

## Prerequisites

- Python 3.11–3.13
- A Google Cloud project with the Agent Platform API enabled
- Application Default Credentials and the **Agent Platform User** role
  (`roles/aiplatform.user`)

This repo is configured for:

| Setting | Value |
| --- | --- |
| Project | `crafty-progress-421108` |
| Sandbox region | `us-central1` (not `global`) |
| Model | `gemini-3.8-flash` at `global` |

`GOOGLE_CLOUD_LOCATION` (model) and `SANDBOX_LOCATION` (sandbox) are separate
on purpose: sandboxes cannot use `global`, while `gemini-3.8-flash` is served
from the global endpoint.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

gcloud config set project crafty-progress-421108
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login
gcloud auth application-default set-quota-project crafty-progress-421108

# Create the Agent Platform runtime once (no agent deployment needed)
python scripts/bootstrap_runtime.py
```

Copy `.env.example` to `agents/sandbox_agent/.env` and paste the printed
`SANDBOX_RUNTIME_NAME`. Note the printed name uses the project **number**
rather than the project id — that is expected, and config validation allows it.

Instead of user ADC you can authenticate with a service-account key holding
`roles/aiplatform.user`:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json   # keep it out of the repo
```

## Run the Playground

```bash
source .venv/bin/activate
cd agents
adk web --port 8765 --no-reload
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765), select `sandbox_agent`, and try:

> Which sandbox am I in, and what user am I running as? Then create
> /workspace/notes.txt containing "hello from the playground", read it back,
> list /workspace, and show disk usage and the kernel version.

Open a second session and ask for the sandbox name again — it should differ.

## Run the API server (for tests / curl)

```bash
cd agents
adk api_server --port 8765 --no-reload
```

## Tests

```bash
# Unit + SDK contract (no network)
pytest -m "not integration"

# Live isolation tests (need ADC + real SANDBOX_RUNTIME_NAME)
pytest -m integration
```

## What is actually inside the sandbox

Inventoried against a live default shell sandbox in `us-central1` on
2026-09-28. Nothing here is configurable from this repo — it is whatever the
default `shell_environment` image ships — so treat it as a snapshot rather than
a contract.

| | |
| --- | --- |
| OS | Debian GNU/Linux 12 (bookworm) |
| User | `appuser` (uid 999), no `sudo` binary at all |
| Working directory | `/workspace` (writable; `/tmp` and `$HOME` also writable, `/etc` is not) |
| Resources | 2 CPUs, 512 MB RAM, no swap |
| Provisioning | ~10–19 s to `STATE_RUNNING` |
| Warm `execute_bash` | ~100–200 ms round trip |

**Present:** `bash`, `sh`, `dash`, GNU coreutils (`ls`, `cat`, `cut`, `sort`,
`head`, `tail`, `wc`, `tee`, `base64`, `md5sum`, `sha256sum`, `du`, `df`),
`grep`, `sed`, `awk`, `find`, `xargs`, `diff`, `tar`, `gzip`, `perl`,
`openssl`, `ps`, `top`, `which`, `env`, `apt`/`apt-get`/`dpkg`.

`python3` **is** present — Python 3.11.2 in a virtualenv at `/opt/venv`, on
`PATH`, with `fastapi`, `uvicorn`, `starlette`, `pydantic`, `anyio`,
`websockets` and `click` installed. It is there to serve the sandbox's own
machinery, so do not treat it as a supported surface; this agent deliberately
ships no code-execution tool and the system instruction tells the model to
probe with `command -v` rather than assume a runtime.

**Absent:** `curl`, `wget`, `git`, `jq`, `node`, `npm`, `go`, `java`, `ruby`,
`gcc`, `make`, `vim`, `nano`, `less`, `zip`/`unzip`, `ssh`, `rsync`, `sqlite3`,
`tree`, `file`, `patch`, `htop`, `gcloud`, `docker`, `systemctl`, `sudo`.

**No outbound network.** `/etc/resolv.conf` points at `8.8.8.8`/`1.1.1.1`, but
packets do not leave: DNS lookups and direct-IP TCP connects (including to the
metadata IP `169.254.169.254`) **hang until killed** rather than failing fast.
Anything network-touching will burn its entire timeout, so avoid it. `apt-get
install` fails immediately for a different reason — no write access to the
`dpkg` lock, and no `sudo` to gain it.

**Each command is a fresh shell.** `cd` and exported variables do not carry
over between `execute_bash` calls; persist state under `/workspace` instead.

### Command failures vs. sandbox failures

- A non-zero exit is returned as data (`returncode`, `stderr`), not raised.
- A command that outlives its `timeout` comes back as `timed_out: true` with
  `returncode: 124`. It is never retried, since re-running a partially applied
  command is unsafe, and the sandbox stays usable afterwards.
- A sandbox can report `STATE_RUNNING` a moment before its data plane accepts
  traffic; the first `execute_bash` then fails with `FAILED_PRECONDITION` /
  "Bad Gateway: Unable to reach the sandbox environment". This is retried
  automatically, so the first call in a session can take ~20 s.

## Cleanup

```bash
python scripts/reap_sandboxes.py --list
python scripts/reap_sandboxes.py --delete --older-than-hours 1

# Sandboxes plus the templates they leave behind (see below)
python scripts/reap_sandboxes.py --delete --templates
```

Sandboxes also expire via the configured TTL (default 1 hour).

**Templates accumulate.** Every `sandboxes.create` without an explicit
`sandbox_environment_template` makes the SDK provision a fresh
`shell-sandbox-template` first, and nothing ever deletes it — 24 sandbox
creations left 24 templates behind. `--templates` removes the ones no live
sandbox still references. Provisioning that template is also most of the
first-turn latency (~85 s of an ~90 s first turn); pinning one reusable
template at bootstrap and passing it to `create` would remove both the leak and
the wait, and is the obvious next improvement.

Be aware that `templates.list` keeps returning templates for a while after they
are deleted, so the reaper confirms each one with `get` before counting it.
Trust `get`, not `list`, when checking whether cleanup worked.

## Layout

- [`docs/sandbox-learnings.md`](docs/sandbox-learnings.md) — how Agent Platform
  sandboxes behave when wired into ADK (flavour choice, one-per-session,
  templates, timeouts, image facts)
- `agents/sandbox_agent/` — ADK agent, tools, session sandbox manager
- `scripts/` — bootstrap runtime + reaper
- `tests/unit/` — manager invariant + tool/SDK contract tests
- `tests/integration/` — api_server + live one-sandbox-per-session proof
