# Learnings: Agent Platform sandboxes from ADK agents

Practical notes from building and live-verifying this demo against
`crafty-progress-421108` / `us-central1` (2026-09-28), on ADK 2.10.0 and
`google-cloud-agentplatform` 2.2.0. Companion to the [README](../README.md).
How to run the agent lives there; this file is about *how sandboxes behave*
when you wire them into an ADK agent.

## 1. Pick a sandbox flavour deliberately

| Flavour | Spec | Data plane | Good for |
| --- | --- | --- | --- |
| Shell | `shell_environment: {}` | `execute_bash` | Arbitrary bash; file ops via shell |
| Code Execution | `code_execution_environment: {}` | `execute_code` | Python / JS payloads |
| Computer Use | `computer_use_environment: ...` | browser / GUI tooling | UI automation |

They are **not interchangeable**. Shell docs are explicit: `send_command` /
`execute_code` target Code Execution sandboxes and send Python payloads the
shell container will not accept. This demo uses **one shell sandbox per ADK
session** and never opens a second flavour alongside it — that would break the
one-sandbox-per-session invariant.

## 2. Trust the `agentplatform` SDK, not every doc page

Google's docs currently show two incompatible call paths:

- Code Execution / manage pages → `google-cloud-agentplatform`,
  `agentplatform.Client`, `client.sandboxes.*`
- Shell quickstart → `google-cloud-aiplatform[agent_engines]`, `vertexai.Client`,
  mixed `client.agent_engines.sandboxes.*` and `client.sandboxes.*`

Introspection of `google-cloud-agentplatform==2.2.0` confirms the flat
`client.sandboxes.*` path is what actually exists. Pin that package and keep a
signature contract test (`tests/unit/test_sdk_contract.py`) — the surface has
already moved once.

Live calls for shell sandboxes negotiated **`v1beta1`**. There is still no
usable async client: `client.aio.sandboxes` exposes no methods, so every
sandbox call must go through `asyncio.to_thread` or it will stall the ADK
event loop for the whole provision window.

## 3. One sandbox per session is your problem, not ADK's

ADK's experimental `EnvironmentToolset` holds **one** `BaseEnvironment` for
the lifetime of the toolset, and toolsets are constructed once at import. Using
it as-is shares a single sandbox across every session — the opposite of what
you want.

Pattern that works:

- Key on `(app_name, user_id, session_id)` (session ids alone are not unique
  across users).
- Per-key `asyncio.Lock` so concurrent tool calls in one turn create once.
- Durable binding in ADK session state (`state["sandbox"] = {...}`), because
  `adk web` defaults to `--reload` and a SQLite session store — process death
  must not orphan the platform resource or silently create a second one.
- Lazy create on first tool call (provisioning is ~10–20s once the template
  exists; burning that on "hi" is wasteful).

Prove isolation with **two observation points**: ADK session state *and* the
platform API. Distinct resource names are necessary but not sufficient — also
assert filesystem isolation (a marker written in session A must be invisible
from B) and an exact sandbox count for the test's display-name prefix.

## 4. ADK has no session-end hook

Verified in 2.10.0: no "session ended" callback; `Runner` only closes toolsets
/ plugins at runner shutdown. Teardown has to be defence in depth:

1. **TTL at create** (primary; survives crashes) — docs recommend this.
2. Idle pause, then delete.
3. An explicit `end_sandbox_session` tool.
4. Best-effort delete on process shutdown.
5. An operator reaper script matching a display-name prefix.

`execute_bash` resets TTL on activity, so an active conversation stays alive
without a keep-alive pinger. An abandoned Playground session bills until TTL.

## 5. Model region ≠ sandbox region

Sandboxes are regional. `global` / multi-region `us` / `eu` are documented for
Memory Bank and Sessions (and partly for Code Execution) — **not** for shell
sandboxes. Use a real region (`us-central1` here).

The Gemini model can be served from `global` while the sandbox stays regional.
Keep `GOOGLE_CLOUD_LOCATION` and `SANDBOX_LOCATION` as separate settings.
Collapsing them is the tempting bug: a model that works at `global` will 404
in `us-central1` (we saw that with floating aliases like `gemini-flash-latest`).

This agent's defaults: model `gemini-3.8-flash` at `global`, sandbox
`us-central1`.

## 6. Runtime names use the project *number*

`runtimes.create` returns names like:

```text
projects/149377925365/locations/us-central1/reasoningEngines/<id>
```

not `projects/crafty-progress-421108/...`. Comparing the embedded project
segment to `GOOGLE_CLOUD_PROJECT` (usually a project *id*) rejects every real
runtime. Only compare when both sides are the same kind of identifier, or look
the number up via Resource Manager (needs extra IAM).

Reuse **one** long-lived runtime. Project quotas include ~10 create/delete/
update Agent Platform resources per minute — creating a runtime per test will
hit that wall.

## 7. Bare `create` secretly provisions a template

Calling `sandboxes.create` without an explicit `sandbox_environment_template`
makes the SDK create a `shell-sandbox-template` first and **never delete it**.
In our run, N sandboxes left N templates behind.

Consequences:

- **Latency.** Template provisioning was ~78s of an ~85–90s first turn.
- **Leak.** Templates accumulate until you reap them.
- **List lies.** `templates.list` keeps returning deleted templates for a while;
  `templates.get` is truthful.

Mitigations in this repo: `scripts/reap_sandboxes.py --templates` (confirm with
`get` before counting), and `poll_interval_seconds=2.0` on create (the SDK
default of 0.1s polls the operation hundreds of times).

**Best next fix:** create one template at bootstrap, pass it into every
`create`. That removes both the leak and most first-turn latency.

## 8. `STATE_RUNNING` is not "ready for execute_bash"

A sandbox can report `STATE_RUNNING` a beat before its data plane accepts
traffic. The first `execute_bash` then fails with:

```text
FAILED_PRECONDITION … Bad Gateway: Unable to reach the sandbox environment
```

This is systematic (reproduced against the raw SDK), not a fluke. Retry it.
Warm `execute_bash` after that is ~100–200ms.

## 9. Do not retry the user's command timeout

The control plane reports a command that outlived its `timeout` as
`FAILED_PRECONDITION` wrapping `DEADLINE_EXCEEDED` with detail
`command exceeded Ns and was killed`. A naive retry classifier that matches
"deadline" will **re-execute the user's command** — wrong for anything
non-idempotent.

Treat that detail as data: return `timed_out: true`, `returncode: 124`, do not
retry. Non-zero exits are also data (`returncode` / `stderr`), not exceptions.

## 10. Default shell image (as measured)

Inventoried live on the default `shell_environment` image. Treat as a snapshot,
not a contract — Google can change the image without notice.

| | |
| --- | --- |
| OS | Debian 12 (bookworm) |
| User | `appuser` (uid 999); **no `sudo` binary** |
| Resources | 2 CPUs, 512 MB RAM, no swap |
| Writable | `/workspace` (default cwd), `/tmp`, `$HOME`; not `/etc` |
| Provision | ~10–19s once a template exists |
| Warm bash | ~100–200ms round trip |

Present: bash/coreutils, `grep`/`sed`/`awk`/`find`, `tar`/`gzip`, `perl`,
`openssl`, `apt`/`dpkg`, and — notably — **Python 3.11.2 in `/opt/venv`** with
fastapi/uvicorn/pydantic (clearly for the sandbox's own exec service). This
agent still ships no code-execution tool and does not promise that interpreter.

Absent: `curl`, `wget`, `git`, `jq`, `node`, `go`, `gcc`, `make`, `vim`,
`less`, `unzip`, `ssh`, `sqlite3`, `sudo`.

**No outbound network, and it fails by hanging.** Resolvers are configured
(`8.8.8.8`), but DNS and direct-IP TCP (including the metadata IP) block until
killed. Anything network-touching burns its entire timeout (tool default here
is 120s). `apt-get install` fails fast for a different reason: no write access
to the dpkg lock and no sudo.

**Each `execute_bash` is a fresh shell.** `cd` and exported variables do not
survive across calls. Chain with `&&` or persist under `/workspace`. The `cwd`
argument works for a single call.

## 11. Lifecycle that works in practice

- TTL at create is the crash-safe backstop; we use 1h.
- Idle pause after 10 minutes was observed live (a sandbox left alone showed
  `STATE_PAUSED`). Resume from `STATE_PAUSED` only — resuming a running
  sandbox returns `FAILED_PRECONDITION`.
- Display names like `adk-demo-<user>-<session>` are how tests and the reaper
  attribute resources. Prefer that over undocumented fields until `owner` is
  confirmed.
- Quotas that matter at demo scale: 1,000 sandbox entities per region; 10/min
  Agent Platform resource writes. Reuse the runtime; reap aggressively.

## 12. Auth that is enough

`roles/aiplatform.user` plus ADC (or a SA key via
`GOOGLE_APPLICATION_CREDENTIALS`) is sufficient to create runtimes, create /
execute / pause / delete sandboxes, and manage templates. The same role
typically **cannot** read Service Usage or project IAM — judge enablement by
exercising the API, not by `services.get`.

Set the ADC quota project to the project that owns the runtime; otherwise
permission errors can look like `NOT_FOUND`.

## 13. What we deliberately did not use

| Feature | Why not (yet) |
| --- | --- |
| Code Execution sandbox | Different data plane; second sandbox would violate the invariant |
| Computer Use | Different product shape (browser/GUI) |
| Custom container | Solves missing tools, but needs image build/publish |
| Snapshots | Good for "come back tomorrow"; not needed for the first demo |
| `EnvironmentToolset` | Shares one environment across sessions (see §3) |
| CMEK / VPC-SC | Supported by the platform; out of demo scope |

## 14. Highest-value next experiments

1. **Pin one reusable template** at bootstrap and pass it to every `create`.
2. **Snapshots** if you want disk to outlive TTL without leaving compute up.
3. **Code Execution sandbox** only if you accept either replacing shell or
   relaxing the one-sandbox-per-session rule.
4. **Custom image** if the default toolchain is the real constraint (and you
   still cannot rely on outbound network unless the template enables it).

## Sources

- [Sandboxes overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sandbox)
- [Shell sandbox quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sandbox/shell-sandbox-quickstart)
- [Manage sandboxes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sandbox/manage-sandboxes)
- [Supported locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/agent-locations)
- [Agent quotas](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/agent-quotas)
- Live measurements and bug list: project store
  `internal/adk-sandbox-live-verification.md` (not shipped in this repo)
