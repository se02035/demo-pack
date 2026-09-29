# Plan: pause/resume, TTL and snapshot demo for the ADK sandbox agent

**Status:** implemented and live-validated on `cursor/adk-sandbox-agent-af6c`.
Phase 0 ran on 2026-09-28; results are in
[`sandbox-learnings.md` §12](sandbox-learnings.md).
**Target:** same project `YOUR_GCP_PROJECT`, sandboxes in `us-central1`,
model `gemini-3.8-flash` at `global`.

> **Phase 0 gate tripped — the snapshot half of this plan is blocked, and
> pause/resume is far weaker than assumed.**
>
> **Resume is unreliable.** A sandbox woken within a couple of seconds of being
> paused comes back fine; one left paused for 30s or more never accepts a
> command again, whether you call `resume` explicitly or let `execute_bash`
> trigger the platform's auto-resume. §5.4's idle-pause step is therefore
> destructive, and automatic idle pausing now ships disabled.
>
> **Restore does not work at all**: a sandbox created from
> `sandbox_environment_snapshot` reports `STATE_RUNNING` but its data plane
> never accepts a command (1 usable result in 9 attempts, and that one looks
> like gateway routing to the still-live source). S2 is therefore unanswerable
> and §5.3's ordering question is moot. Two of the plan's assumptions also came
> out the other way: **`execute_bash` does not reset TTL** (§5.5) and
> **`latest_sandbox_environment_snapshot` is never populated** (S5).
>
> The code ships the defensive version: restore is attempted, the result is
> probed, and an unusable sandbox is deleted and replaced with a fresh empty one
> rather than bound to the session. Nothing silently hands a user a dead
> sandbox. Decisions for Oliver are in §10.

## 1. Goal

Turn sandbox lifecycle from invisible plumbing into something a user can watch
in the Playground and a test can assert:

1. **Pause / resume** — pause a session's sandbox, show it stops billing compute,
   resume it, and show `/workspace` survived.
2. **TTL** — show the expiry clock, show what activity does to it, and show what
   happens when it runs out (and that the agent recovers without breaking the
   one-sandbox-per-session invariant).
3. **Snapshots** — checkpoint a session's disk, destroy the sandbox, restore
   from the checkpoint, and show the files came back. Then use snapshots to make
   idle-delete non-destructive ("come back tomorrow").

The hard invariant is unchanged: **at most one live sandbox per ADK session.**
Snapshots are not sandboxes, so they do not count against it, but restore does
create a sandbox — §5.3 is about doing that without a two-sandbox window.

Out of scope: cross-session snapshot sharing ("fork my sandbox into a new
session"), custom images, Code Execution / Computer Use sandboxes.

## 2. What the SDK exposes (verified by introspection)

```python
client.sandboxes.pause(name, poll_interval_seconds=0.1, config={"wait_for_completion": bool})
client.sandboxes.resume(name, poll_interval_seconds=0.1, config={"wait_for_completion": bool})

client.sandboxes.snapshots.create(
    source_sandbox_environment_name=...,
    config={"display_name", "owner", "ttl", "wait_for_completion"},  # wait defaults True
    poll_interval_seconds=0.1,
) -> RuntimeSandboxSnapshotOperation  # .response is SandboxEnvironmentSnapshot
client.sandboxes.snapshots.get(name) / list(name=<runtime>, config={filter, page_size}) / delete(name)

# Restore = create a *new* sandbox seeded from a snapshot
client.sandboxes.create(name=<runtime>, spec=..., config={
    "sandbox_environment_snapshot": <snapshot name>,
    "sandbox_environment_template": <optional>, "ttl": ..., "display_name": ...})
```

Resource fields that matter:

| Resource | Fields |
| --- | --- |
| `SandboxEnvironment` | `state`, `ttl`, `expire_time`, `sandbox_environment_snapshot` (what it was restored from), `latest_sandbox_environment_snapshot`, `sandbox_environment_template`, `owner` |
| `SandboxEnvironmentSnapshot` | `name`, `display_name`, `source_sandbox_environment`, `parent_snapshot`, `size_bytes`, `ttl`, `expire_time`, `create_time`, `owner` |
| `PostSnapshotAction` enum | `RUNNING`, `PAUSE` — "action on the source after the snapshot is taken" |

Gaps the design must work around:

- **No way to extend a sandbox's TTL.** There is no `update` for sandboxes;
  `ttl` is create-time only ("expiration = now + TTL"). "Extend" has to mean
  either *activity resets the clock* (documented for `execute_code`; unverified
  for `execute_bash`) or *snapshot and recreate*.
- **`post_snapshot_action` is not on `CreateRuntimeSandboxSnapshotConfig`.** The
  enum exists and the API accepts it, but the SDK config can't set it. Snapshot
  then pause is two calls unless we pass it through a raw request.
- **Snapshots have their own TTL**, independent of the source sandbox. Good: a
  snapshot can outlive its sandbox by design. Must be set explicitly or we
  inherit an unknown default.
- **`parent_snapshot`** suggests incremental chains. Unknown whether deleting a
  parent breaks a child.
- Same no-async story as the rest of the SDK: everything via `asyncio.to_thread`,
  and pass a sane `poll_interval_seconds` (the 0.1s default hammered the
  operations endpoint during create).

## 3. Phase 0 — questions to answer live before building

A throwaway spike, outside the repo, on the existing runtime. Each row is a
measurement, not a guess. Record results into `docs/sandbox-learnings.md`.

| # | Question | How to measure |
| --- | --- | --- |
| P1 | Pause and resume latency | time `pause`/`resume` with `wait_for_completion` |
| P2 | What survives pause? `/workspace`, `/tmp`, `$HOME`? Background processes? | write markers in each + `nohup sleep 9999 &`, pause, resume, check |
| P3 | Is a paused sandbox still reachable by `execute_bash`? Error shape? | call while `STATE_PAUSED` |
| P4 | First `execute_bash` after resume — same Bad Gateway readiness race as after create? | observe, count retries |
| T1 | Does `execute_bash` reset TTL on shell sandboxes? | `get().expire_time` before/after a command |
| T2 | Does the TTL clock keep running while paused? | pause, wait, compare `expire_time` |
| T3 | What happens at expiry: `NOT_FOUND`, `STATE_DELETED`, or `STATE_TERMINATED`? How fast after `expire_time`? | create with `ttl=120s`, poll |
| T4 | Can a paused sandbox expire, and does resume after expiry fail cleanly? | pause, let TTL lapse, resume |
| T5 | Minimum accepted TTL (for short demo settings) | try 30s / 60s / 120s |
| S1 | Snapshot latency and `size_bytes` for a near-empty vs ~50 MB `/workspace` | time `snapshots.create` |
| S2 | What does a snapshot capture — `/workspace` only, or the whole writable FS? | markers in `/workspace`, `/tmp`, `$HOME`, restore, check |
| S3 | Can you snapshot a **paused** sandbox? Does the source keep running? | snapshot in each state, `get` after |
| S4 | Restore latency; does restore also create a hidden template (the leak again)? | count templates before/after |
| S5 | Is `latest_sandbox_environment_snapshot` auto-populated (e.g. on pause)? | inspect after pause and after an explicit snapshot |
| S6 | Default snapshot TTL when none is set; max snapshot TTL | create without `ttl`, read `expire_time` |
| S7 | Can a snapshot be restored after its source sandbox is deleted? After source TTL expiry? | delete source, then restore |
| S8 | `parent_snapshot` chains — second snapshot of a restored sandbox; delete parent, restore child | build a chain of 2 |
| S9 | Does passing `post_snapshot_action=PAUSE` via raw HTTP work? | `http_options` / `client.api` escape hatch |
| S10 | Quota and billing for snapshots | check quotas page + billing SKU names; note entity counts |

**Gate:** if S2 shows snapshots don't capture `/workspace`, or S7 shows restore
needs a live source, the snapshot half of the demo changes shape — stop and
report before Phase 1.

## 4. User-visible demo (Playground script)

One session, six prompts. Each maps to a tool call whose response carries
`sandbox_name`, `state` and `expire_time`, so the Playground's Events tab shows
the whole story.

1. *"Show me my sandbox's lifecycle."* → `get_sandbox_lifecycle`: name, state
   `STATE_RUNNING`, TTL, `expire_time`, seconds remaining, snapshots (none).
2. *"Write `notes.txt` with 'before pause', then pause the sandbox."* →
   `write_text_file`, `pause_sandbox` → state `STATE_PAUSED`, measured pause time.
3. *"Read notes.txt."* → transparent resume (already in the manager) → content
   intact, response flags `resumed: true` and resume latency.
4. *"Snapshot this sandbox as 'checkpoint-1', then delete notes.txt."* →
   `snapshot_sandbox` → snapshot name, `size_bytes`, snapshot `expire_time`.
5. *"Restore checkpoint-1 and read notes.txt."* → `restore_snapshot` → a **new**
   sandbox name, `sandbox_history` shows the old one, file is back.
6. *"Show the lifecycle again."* → new sandbox, restored-from snapshot, one
   snapshot listed, TTL reset.

TTL segment, run with a short demo TTL (`SANDBOX_TTL_SECONDS=180` or the minimum
from T5):

7. Wait past expiry, then *"Read notes.txt."* → manager finds the binding dead
   (`NOT_FOUND`), and — new in this plan — offers/auto-performs restore from the
   session's latest snapshot instead of handing back an empty sandbox. The
   response says so plainly.

## 5. Design

### 5.1 New and changed tools

All are `FunctionTool`s resolving through `SessionSandboxManager`, returning
JSON with `sandbox_name`, like the existing six.

| Tool | Behaviour |
| --- | --- |
| `get_sandbox_lifecycle()` | `get` + derived `seconds_until_expiry`, `restored_from`, session's snapshot list. Read-only; does **not** create a sandbox if none is bound (returns `bound: false`). |
| `pause_sandbox()` | Explicit pause. No-op with a message if already paused. |
| `resume_sandbox()` | Explicit resume (implicit resume on any other tool already exists). Only from `STATE_PAUSED`, per the docs' `FAILED_PRECONDITION` rule. |
| `snapshot_sandbox(label: str)` | `snapshots.create` with `display_name=<prefix>-<user>-<session>-<label>` and `ttl=SANDBOX_SNAPSHOT_TTL_SECONDS`. Appends to `state["sandbox_snapshots"]`. |
| `list_snapshots()` | This session's snapshots only, from state, each confirmed with `get` (lists can be stale — see the template lesson). |
| `restore_snapshot(label_or_name: str)` | §5.3. Only snapshots recorded in *this* session's state are accepted. |
| `delete_snapshot(label_or_name: str)` | Delete + remove from state. |
| `get_sandbox_info` (changed) | Add `expire_time`, `seconds_until_expiry`, `restored_from`. |

Rejecting snapshot names that aren't in the session's own state is the isolation
rule for snapshots: a snapshot is session data, and restoring someone else's is
exactly the cross-session leak the invariant exists to prevent.

### 5.2 State model

```python
state["sandbox"]           # existing binding; add "restored_from": snapshot name | None
state["sandbox_history"]   # existing
state["sandbox_snapshots"] = [
  {"name": ".../sandboxEnvironmentSnapshots/<id>", "label": "checkpoint-1",
   "created_at": ..., "expire_time": ..., "size_bytes": ...,
   "source_sandbox": ".../sandboxEnvironments/<id>", "auto": False},
]
```

New settings: `SANDBOX_SNAPSHOT_TTL_SECONDS` (default 86400), `SANDBOX_AUTO_SNAPSHOT_ON_IDLE_DELETE`
(default true), `SANDBOX_AUTO_RESTORE_ON_EXPIRY` (default true),
`SANDBOX_MAX_SNAPSHOTS_PER_SESSION` (default 5, oldest auto-snapshot evicted first).

### 5.3 Restore without a two-sandbox window

Restore necessarily creates a new sandbox. Two orderings:

- **Create new, then delete old** — safest against a failed restore, but for a
  few seconds the session has two live sandboxes. Violates the invariant and
  would fail the existing "exactly two sandboxes" integration assertion.
- **Delete old, then create from snapshot** — never two live sandboxes. If the
  restore fails, the snapshot is still there and restore can be retried; the
  session is briefly *unbound*, which the manager already handles (next tool
  call re-resolves).

**Decision: delete-then-restore**, under the per-session lock:

```
async with lock[key]:
    snap = session_snapshot(label)            # must belong to this session
    await to_thread(snapshots.get, snap)      # still alive? else error, no side effects
    if binding: delete(binding.name); history.append(binding.name); clear binding
    env = create(runtime, config={sandbox_environment_snapshot: snap, ttl, display_name,
                                  sandbox_environment_template: pinned_or_None})
    probe execute_bash("true") with readiness retry
    write binding (restored_from=snap)
```

The snapshot-existence check comes *before* the delete, so a bad label never
destroys the live sandbox. If S7 shows restore needs a live source, this
ordering is impossible and the plan falls back to create-then-delete with the
invariant relaxed to "at most one *bound* sandbox, overlap reaped" — a decision
for Oliver, not a silent change.

### 5.4 Making idle-delete and TTL expiry non-destructive

Today the idle reaper pauses at 10 min and deletes at 1 h, and TTL expiry loses
everything. With snapshots:

- **Idle delete becomes snapshot-then-delete** (`auto: true` snapshot) when
  `SANDBOX_AUTO_SNAPSHOT_ON_IDLE_DELETE` is on.
- **TTL expiry can't be intercepted** (it can happen with the process dead), so
  the recovery is on the *next* resolve: binding dead → if the session has a live
  snapshot and `SANDBOX_AUTO_RESTORE_ON_EXPIRY`, restore from the newest one
  instead of creating empty. The tool response reports `restored_from` and the
  snapshot age so the model tells the user their files are from time X.
- Optional, depending on T1/T2: a pre-expiry auto-snapshot from the idle task
  when `seconds_until_expiry < 5 min` and the sandbox has been active. Only
  worth it if activity *doesn't* reset TTL — otherwise an active session never
  expires.

### 5.5 Explaining TTL honestly

Because TTL can't be updated, `get_sandbox_lifecycle` reports it as measured:
if T1 confirms `execute_bash` resets it, say "each command pushes expiry to now +
TTL"; if not, say "expires at X regardless of activity; take a snapshot to keep
your files". The system prompt gets one line on this so the model doesn't
promise an extension it can't perform.

### 5.6 Pinned template first

Restore will likely go through the same hidden-template path as create (S4).
The pinned-template change recommended in `docs/sandbox-learnings.md` should land
**before** this work: it removes ~78 s from every create *and* every restore,
which is the difference between a snappy restore demo and a 90-second wait.

## 6. Tests

### Unit (fake client, no network)

Extend `tests/fakes.py` with pause/resume state transitions, snapshots
(create/get/delete, TTL), restore-from-snapshot copying a fake filesystem, and
injectable expiry.

- pause → state paused; resolve → exactly one resume, no create.
- snapshot records into this session's state only; two sessions never see each
  other's snapshots.
- `restore_snapshot` with another session's snapshot name → rejected, no delete.
- restore with a dead snapshot → error, **old sandbox untouched**.
- restore ordering: fake records call order; assert `delete(old)` precedes
  `create(from snapshot)` and never two live sandboxes for the key.
- expiry + live snapshot → auto-restore (1 create with `sandbox_environment_snapshot`);
  expiry + no snapshot → plain create; `sandbox_history` correct in both.
- idle-delete with auto-snapshot → snapshot then delete, in that order.
- snapshot cap: 6th auto-snapshot evicts the oldest auto one, never a manual one.

### Live integration (`-m integration`, new file `test_lifecycle_live.py`)

Non-LLM, driving the manager directly — lifecycle is about platform behaviour,
and the model adds nothing but flake:

1. **Pause preserves disk:** write marker → pause → assert `STATE_PAUSED` → read
   marker (implicit resume) → equal.
2. **Snapshot round trip:** marker → snapshot → overwrite marker → restore →
   original marker back; new sandbox name ≠ old; old sandbox `NOT_FOUND`;
   exactly one live sandbox for the key throughout (poll the list between steps).
3. **TTL expiry recovery** (`@pytest.mark.slow`, short TTL from T5): marker →
   snapshot → wait past `expire_time` → resolve → restored, marker present,
   `restored_from` set.

One LLM-driven test through the apiserver, for the demo script's steps 2–5, with
the same assert-on-structured-data rule as the existing isolation test.

Cost: ~4 sandboxes and ~3 snapshots per run. The session reaper fixture must
also delete this run's snapshots.

## 7. Cleanup tooling

- `reap_sandboxes.py --snapshots`: list/delete snapshots on the runtime matching
  the display-name prefix and older than `--older-than-hours`. Confirm each with
  `get` before counting (don't trust `list`).
- Order matters if S8 shows chains: delete children before parents.
- README cleanup section and `docs/sandbox-learnings.md` updated with measured
  snapshot semantics.

## 8. Risks

| Risk | Mitigation |
| --- | --- |
| Snapshots don't capture `/workspace` or need a live source | Phase 0 gate (S2, S7) before any build |
| Restore reintroduces the ~78 s template wait and template leak | Land pinned template first (§5.6); reaper covers templates already |
| Short TTL below the accepted minimum | Measure T5; use the minimum, mark the test `slow` |
| Auto-restore surprises a user with stale files | Response always reports `restored_from` + snapshot age; the model must say it |
| Snapshot storage cost accumulates | Snapshot TTL default 24 h, per-session cap, reaper `--snapshots` |
| `post_snapshot_action` unreachable from the SDK | Two calls (snapshot, then pause); raw request only if S9 shows it's worth it |
| Readiness race after resume/restore | Reuse existing Bad Gateway retry; probe with `true` before returning a binding |
| Quota: sandbox entity + resource-write limits | Reuse runtime; restore = 1 delete + 1 create; tests stay under 10 writes/min |

## 9. Phases

0. **Spike** (§3). Output: measured answers written into
   `docs/sandbox-learnings.md`; go/no-go on snapshots.
1. **Pinned template** (prerequisite, §5.6), with a unit test and a live check
   that N creates leave one template.
2. **Pause/resume + lifecycle visibility:** `get_sandbox_lifecycle`,
   `pause_sandbox`, `resume_sandbox`, `expire_time` on info. Unit + live test 1.
3. **Snapshots:** `snapshot_sandbox`, `list_snapshots`, `delete_snapshot`,
   `restore_snapshot` with delete-then-restore. Unit + live test 2. Reaper
   `--snapshots`.
4. **Non-destructive expiry/idle:** auto-snapshot on idle delete, auto-restore
   on expiry, snapshot cap. Unit + live test 3.
5. **Demo polish:** Playground script in the README, system-prompt lines on
   TTL/snapshot semantics, apiserver LLM test for the script, a short screen
   recording.

## 10. Needs Oliver

1. **Restore is a platform bug — do we file it with Google and wait, or cut the
   snapshot half of the demo?** Everything else works; restore is the only
   blocker, and we cannot fix it from this side. Phase 0 evidence is in
   `sandbox-learnings.md` §12.
2. **Should `restore_snapshot` and `list_snapshots` stay shipped as tools while
   restore is broken?** Today `restore_snapshot` always ends in
   `restore_unusable` plus a fresh empty sandbox, which is safe but a bad demo
   beat. The alternative is hiding the tools behind a flag until the platform
   is fixed.
3. **Does the TTL finding change the demo?** Activity does *not* extend TTL, so
   a busy session dies at exactly one hour with no warning and — because
   restore is broken — no way to bring its files back. Options: a much longer
   TTL, or a tool that tells the user how long they have left.
4. **Keep `pause_sandbox` as a user-facing tool?** Pausing is safe only if the
   very next thing you do resumes it, which is not a promise we can make to a
   model deciding when to call tools. Prospect: drop the tool and keep pause as
   an internal step of snapshotting, or keep it with a blunt warning in the
   response.
5. **Snapshot retention default** — we set 24h explicitly; the platform default
   is **30 days**, which is a real cost/retention footgun if anyone forgets the
   `ttl`. Keep 24h, and 5 per session?
6. **Cross-session restore/fork** stays out unless he wants it — it is the one
   feature here that deliberately moves data between sessions.
7. **The runtime is shared with other agents.** Phase 0 saw another session
   creating `adk-demo-*` sandboxes on the same runtime concurrently. The test
   reaper is now scoped to this suite's own test users, but
   `scripts/reap_sandboxes.py --delete` still matches the bare prefix and will
   take someone else's sandboxes with it. Worth a dedicated prefix per operator
   if this keeps happening.
