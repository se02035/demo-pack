# Learnings: Agent Platform sandboxes from ADK agents

Practical notes from building and live-verifying this demo against
`YOUR_GCP_PROJECT` / `us-central1` (2026-09-28), on ADK 2.10.0 and
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

TTL is **absolute and set at create time**: activity does not extend it, and
there is no update call (measured — see §12). An abandoned Playground session
bills until TTL, and a *busy* one dies at exactly the same moment. Anything
longer than one TTL has to re-create.

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
projects/PROJECT_NUMBER/locations/us-central1/reasoningEngines/<id>
```

not `projects/YOUR_GCP_PROJECT/...`. Comparing the embedded project
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

- **Leak.** Templates accumulate until you reap them. Still true: two bare
  creates during the Phase 0 run took the runtime from 37 to 39 templates.
- **Latency, but less than it was.** The ~78s template provision we first
  measured did not reproduce on 2026-09-28: a bare create took ~12s. Treat the
  provision time as variable, not as a fixed 78s tax.
- **List lies.** `templates.list` keeps returning deleted templates for a while;
  `templates.get` is truthful.

Mitigations in this repo: `scripts/reap_sandboxes.py --templates` (confirm with
`get` before counting), and `poll_interval_seconds=2.0` on create (the SDK
default of 0.1s polls the operation hundreds of times).

**Fix, now measured:** create one template at bootstrap
(`scripts/bootstrap_template.py`, ~20s once) and set `SANDBOX_TEMPLATE_NAME`.
The manager also auto-creates/reuses `{prefix}-shell-template` if the env var is
empty. With the template pinned, `sandboxes.create` returned in **~3s** across
eight measurements (2.9–3.8s) and added **no** new template. That is the whole
per-create cost now; what is left of first-turn latency is the data-plane
readiness race in §8, not provisioning.

You cannot pass a template and a snapshot together — the API rejects it with
`INVALID_ARGUMENT: Sandbox environment template and sandbox environment
snapshot cannot be specified at the same time`. A restored sandbox silently
inherits its source's template.

## 8. `STATE_RUNNING` is not "ready for execute_bash"

A sandbox can report `STATE_RUNNING` a beat before its data plane accepts
traffic. The first `execute_bash` then fails with:

```text
FAILED_PRECONDITION … Bad Gateway: Unable to reach the sandbox environment
```

This is systematic (reproduced against the raw SDK), not a fluke. Retry it.
Measured time from `create` returning to the first accepted command: **7s, 20s,
23s, 23s** across four fresh sandboxes. Warm `execute_bash` after that is
144–257ms.

Probe with a *short* command timeout and retry, rather than one long attempt.
The failure can present either as an immediate `Bad Gateway` or as the call
sitting until its deadline, so a single 30s probe turns a 7s wait into a 30s
one.

### `execute_bash` has no client-side deadline — cap it yourself

The `timeout` argument is the *sandbox-side* command timeout. The SDK issues the
request over httpx with no client timeout at all, so if the data plane never
answers, the calling thread blocks **forever** — no exception, so no retry
wrapper ever fires. We hit this for real: a restored sandbox (§12) wedged a spike
script for 16 minutes until it was killed.

Pass one explicitly:

```python
client.sandboxes.execute_bash(
    name=name, command=cmd, timeout=120,
    config={"http_options": {"timeout": 150_000}},  # ms, above the command timeout
)
```

Keep the HTTP cap above the command timeout, or you lose the control plane's
"command exceeded Ns and was killed" response and mislabel it as a transport
failure.

### A backgrounded process that holds stdout hangs the whole call

`execute_bash` waits for the command's stdout/stderr to close, not for the
foreground process to exit. Measured with a 12s timeout:

| Command | Result |
| --- | --- |
| `sleep 120 & echo started` | hangs the full 12s, `returncode 124` |
| `sleep 120 >/dev/null 2>&1 & echo started` | returns in 0.46s |

Watch the shell precedence too: in `a && b && nohup c > log &` the `&` applies
to the *entire* `&&` chain, so the backgrounded subshell still owns the original
stdout and the call hangs even though `c` itself was redirected. Redirect both
streams on anything you background.

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

- TTL at create is the crash-safe backstop; we use 1h. It cannot be extended
  later, and pausing does not slow it down (§12).
- **Do not auto-pause idle sessions.** A sandbox left paused for more than a
  few seconds never accepts commands again (§12), so the 10-minute idle pause
  we originally shipped is now off by default.
- Resume from `STATE_PAUSED` only — resuming a running sandbox returns
  `FAILED_PRECONDITION`. You rarely need an explicit resume anyway:
  `execute_bash` against a paused sandbox makes the platform start one (§12).
- Display names like `adk-demo-<user>-<session>` are how tests and the reaper
  attribute resources. Prefer that over undocumented fields until `owner` is
  confirmed.
- Quotas that matter at demo scale: 1,000 sandbox entities per region; 10/min
  Agent Platform resource writes. Reuse the runtime; reap aggressively.

## 12. Pause, TTL and snapshots, as measured

Phase 0 of [`sandbox-lifecycle-demo-plan.md`](sandbox-lifecycle-demo-plan.md),
run live on 2026-09-28 against `YOUR_GCP_PROJECT` / `us-central1`. Every
row is a measurement.

### Latency

| Operation | Measured |
| --- | --- |
| `create` with a pinned template | 2.9–3.8s (n=8) |
| `create` with auto-provisioned template | ~12s, **+1 leaked template** |
| `templates.create` (bootstrap, once) | ~20s |
| Create → first accepted `execute_bash` | 7–23s (n=4) |
| Warm `execute_bash` | 144–257ms |
| `pause` (`wait_for_completion`) | 11.1–11.5s |
| `resume` from `STATE_PAUSED` | ~7.5s to return, but usually dead after |
| `snapshots.create` | 9.5–11.5s, **independent of size** |
| `create` from a snapshot | 7.1–8.5s (but see *Restore is broken*) |

A snapshot of a near-empty `/workspace` (342 bytes) and one of a 50 MB
`/workspace` both took ~9.5s, so snapshot time is not proportional to disk.

### Pause / resume — only safe for a few seconds

**A paused sandbox does not reliably come back.** Wake it immediately and it is
fine; leave it paused and it is gone, while still reporting `STATE_RUNNING`
after the resume. Three sandboxes, identical except for how long they sat
paused, each then polled for 150s:

| Paused for | Came back? |
| --- | --- |
| 0s (woken straight away) | **yes**, ready 6.8s later, marker file intact |
| 30s | no — 8 probes over 150s, all `DEADLINE_EXCEEDED` |
| 120s | no — 7 probes over 150s, all `DEADLINE_EXCEEDED` |

It is not about *how* you wake it. Both wake-up paths were measured separately
against a 20s pause and both failed for 3+ minutes:

- an explicit `sandboxes.resume()` — returns in ~7.5s, reports `STATE_RUNNING`;
- letting `execute_bash` trigger the platform's own auto-resume.

Nor is it about what is running inside: an idle sandbox and one with a
background `nohup sleep` failed identically.

So the pause API works — `pause` itself is reliable, ~11.2s — and the resume
side is what is broken. Consequences for this repo:

- **Automatic idle pausing is off by default** (`SANDBOX_IDLE_PAUSE_SECONDS=0`).
  It used to fire at 10 minutes, which would have silently destroyed the
  sandbox of every session that went quiet. It also bought nothing, because
  pausing does not slow the TTL clock.
- `pause_sandbox` stays available, and the manager still tries to resume, but
  the readiness probe decides whether the sandbox actually came back; a session
  gets a replacement rather than a dead binding.

Two smaller facts worth keeping:

- `execute_bash` against `STATE_PAUSED` returns `503 UNAVAILABLE: Sandbox
  environment is paused; resume has been initiated. Please retry the request.`
  The platform starts a resume on its own, which is why `STATE_RESUMING` shows
  up unprompted — and that is **not** a state you can snapshot from (below).
- When a resume does work, it preserves the whole writable filesystem
  (`/workspace`, `/tmp`, `$HOME`) **and** running background processes: a
  `nohup sleep` was still alive by pid afterwards.

### TTL

- **Activity does not extend TTL.** `expire_time` was byte-identical before and
  after an `execute_bash` 25s later. There is no sandbox update call either, so
  TTL genuinely cannot be extended — only snapshot-and-recreate.
- **Pausing does not stop the clock.** `expire_time` was unchanged after 60s
  paused; a paused sandbox burns its TTL at the same rate as a running one.
- **Minimum TTL is at most 10s.** `10s`, `30s`, `60s` and `120s` were all
  accepted and honoured exactly (`expire_time - create_time` matched the
  request). Short TTLs are fine for demos and tests.
- **Expiry is a hard delete, not a state transition.** The sandbox went from
  `STATE_RUNNING` to `404 NOT_FOUND` within ~3s of `expire_time`; we never
  observed `STATE_TERMINATED` or `STATE_DELETED`. `execute_bash` afterwards
  returns `400 FAILED_PRECONDITION: Precondition check failed.`
- **A paused sandbox expires too**, and resuming it afterwards fails cleanly
  with `FAILED_PRECONDITION`. Pausing is not a way to park a sandbox overnight.

### Snapshots

- **You can only snapshot a sandbox in exactly `STATE_RUNNING`.** Anything else
  is `400 FAILED_PRECONDITION: … must be in RUNNING state to be snapshotted;
  current state: SANDBOX_ENVIRONMENT_STATE_RESUMING`. Combined with the
  auto-resume above, "resume then immediately snapshot" is a race you have to
  poll out of.
- **The default snapshot TTL is 30 days** (720h) when you pass no `ttl`. That is
  a long time to keep a user's disk around by accident — always set it.
- **`size_bytes` is never populated**, on the create response or a later `get`.
  Do not promise users a snapshot size.
- **`parent_snapshot` is never populated** either, including on a snapshot taken
  from a restored sandbox, so there is no visible incremental chain to reason
  about.
- **`latest_sandbox_environment_snapshot` is never populated** on the sandbox —
  not after a pause, not after an explicit snapshot. Track snapshots in session
  state; the field is not a shortcut.
- **`post_snapshot_action` is unreachable from the SDK.** The config model
  rejects it outright (`extra_forbidden`), confirming the plan's assumption.
  Snapshot-then-pause is two calls.
- Snapshots do outlive their source: `snapshots.get` still worked after the
  source sandbox was deleted.

### Restore is broken — this is the Phase 0 gate

`create(..., sandbox_environment_snapshot=…)` **succeeds and produces a sandbox
that can never run a command.** It returns `STATE_RUNNING` in ~7s, `get` keeps
reporting `STATE_RUNNING`, and every `execute_bash` fails with
`DEADLINE_EXCEEDED` (empty error details) from the exec gateway.

**1 of 9 restore attempts** produced a usable sandbox, and that one answered in
0.2s on the first probe — far faster than any genuine fresh sandbox (7–23s),
which points at the gateway routing to the still-live source rather than a real
success. Things we ruled out:

| Tried | Result |
| --- | --- |
| Waiting 6 minutes, polling every 5s | never ready |
| Pause + resume to re-wire the data plane, then 3 more minutes | never ready |
| Passing `spec={"shell_environment": {}}` alongside the snapshot | never ready |
| Passing the pinned template too | `INVALID_ARGUMENT` — mutually exclusive |
| Source created from an auto-provisioned template instead | never ready |
| Restoring after deleting the source sandbox | never ready |
| Ports other than 8080 | never ready |

So **S2 ("what does a snapshot capture?") is unanswerable** — there is no way to
read a restored disk — and the snapshot half of the demo cannot work as
designed. What still holds: snapshots are cheap, fast, survive their source, and
their metadata is readable. Only *restore* is dead.

Because of this, the repo's posture is defensive rather than optimistic:

- `_probe_ready` returns a boolean instead of logging and continuing, so a
  sandbox that never accepts traffic is never bound to a session.
- A restore whose sandbox fails the probe is deleted and reported as
  `restore_unusable`; the session gets a fresh, working, empty sandbox rather
  than a dead one. The snapshot is left intact so restore can be retried.
- Auto-restore on expiry does the same, falling through to a plain create.

## 13. Auth that is enough

`roles/aiplatform.user` plus ADC (or a SA key via
`GOOGLE_APPLICATION_CREDENTIALS`) is sufficient to create runtimes, create /
execute / pause / delete sandboxes, and manage templates. The same role
typically **cannot** read Service Usage or project IAM — judge enablement by
exercising the API, not by `services.get`.

Set the ADC quota project to the project that owns the runtime; otherwise
permission errors can look like `NOT_FOUND`.

## 14. What we deliberately did not use

| Feature | Why not (yet) |
| --- | --- |
| Code Execution sandbox | Different data plane; second sandbox would violate the invariant |
| Computer Use | Different product shape (browser/GUI) |
| Custom container | Solves missing tools, but needs image build/publish |
| Snapshot restore as a product feature | Implemented, but the platform cannot restore a usable sandbox today (§12) |
| `EnvironmentToolset` | Shares one environment across sessions (see §3) |
| CMEK / VPC-SC | Supported by the platform; out of demo scope |

## 15. Highest-value next experiments

1. **Take the restore failure to Google.** Everything else about snapshots
   works; a sandbox created from `sandbox_environment_snapshot` that reports
   `STATE_RUNNING` but never accepts traffic looks like a platform bug, and it
   is the only thing standing between us and the "come back tomorrow" demo.
2. **Re-run Phase 0's restore rows** whenever the SDK or API version moves —
   `tests/integration/test_lifecycle_live.py` keeps the happy path as a
   non-strict xfail precisely so it flips green on its own.
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
