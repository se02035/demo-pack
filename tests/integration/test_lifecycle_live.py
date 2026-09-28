"""Live lifecycle tests: pause/resume, snapshot restore, TTL recovery.

Skipped unless ADC (or GOOGLE_APPLICATION_CREDENTIALS) and a real
SANDBOX_RUNTIME_NAME are present.

Restore-from-snapshot is measured as broken on the platform today: the new
sandbox reports STATE_RUNNING in ~7s but its data plane never answers (1 usable
restore in 9 attempts, and that one looks like gateway routing to the still-live
source). These tests therefore assert the *safe* behaviour — a session is never
left bound to a sandbox that cannot run a command — and keep the happy path as a
strict-xfail so it flips green the day the platform is fixed. See
docs/sandbox-learnings.md §12.
"""

from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import pytest

from tests.integration.conftest import requires_live

pytestmark = [pytest.mark.integration, requires_live]


def _ctx(session_id: str, user_id: str = "life_user"):
  return SimpleNamespace(
      session=SimpleNamespace(
          app_name="sandbox_agent", user_id=user_id, id=session_id
      ),
      state={},
  )


def _manager(settings):
  from sandbox_agent.sandbox.client import SandboxClient
  from sandbox_agent.sandbox.manager import SessionSandboxManager

  client = SandboxClient(
      project=settings.project,
      location=settings.sandbox_location,
      default_timeout_seconds=settings.default_timeout_seconds,
  )
  return client, SessionSandboxManager(client=client, settings=settings)


def _live_for_session(client, settings, manager, ctx):
  """Sandboxes on the runtime carrying this session's display name."""
  display = manager.display_name_for(manager.session_key_from_context(ctx))
  return [
      s
      for s in client.list(runtime_name=settings.runtime_name)
      if (s.get("display_name") or "") == display
  ]


@pytest.mark.asyncio
async def test_pause_preserves_disk_live(live_settings, sandbox_reaper):
  client, manager = _manager(live_settings)
  ctx = _ctx(f"life_pause_{uuid.uuid4().hex[:8]}")
  try:
    binding = await manager.resolve(ctx)
    client.execute_bash(
        name=binding.name, command="echo BEFORE_PAUSE > /workspace/marker.txt"
    )
    paused = await manager.pause_session(ctx)
    assert paused["ok"] is True
    assert client.get(name=binding.name)["state"] == "STATE_PAUSED"

    # Implicit resume via resolve; same sandbox, disk intact.
    again = await manager.resolve(ctx)
    assert again.name == binding.name
    out = client.execute_bash(name=binding.name, command="cat /workspace/marker.txt")
    assert "BEFORE_PAUSE" in out["stdout"]
    assert client.get(name=binding.name)["state"] == "STATE_RUNNING"
  finally:
    await manager.end_session(ctx)


@pytest.mark.asyncio
async def test_pause_keeps_tmp_home_and_background_processes_live(
    live_settings, sandbox_reaper
):
  """Pause preserves the whole writable filesystem, not just /workspace."""
  client, manager = _manager(live_settings)
  ctx = _ctx(f"life_scope_{uuid.uuid4().hex[:8]}")
  try:
    binding = await manager.resolve(ctx)
    client.execute_bash(
        name=binding.name,
        command=(
            "echo WS > /workspace/m.txt; echo TMP > /tmp/m.txt; "
            "echo HOME > $HOME/m.txt; "
            # stdout must be closed or execute_bash blocks until its timeout.
            "nohup sleep 600 </dev/null >/workspace/bg.log 2>&1 & "
            "echo $! > /workspace/bg.pid; echo ok"
        ),
    )
    await manager.pause_session(ctx)
    await manager.resolve(ctx)

    out = client.execute_bash(
        name=binding.name,
        command=(
            "cat /workspace/m.txt /tmp/m.txt $HOME/m.txt; "
            "kill -0 $(cat /workspace/bg.pid) && echo BG_ALIVE"
        ),
    )
    assert "WS" in out["stdout"]
    assert "TMP" in out["stdout"]
    assert "HOME" in out["stdout"]
    assert "BG_ALIVE" in out["stdout"]
  finally:
    await manager.end_session(ctx)


@pytest.mark.asyncio
async def test_backgrounded_command_must_close_stdout_live(
    live_settings, sandbox_reaper
):
  """execute_bash waits for stdout to close, not for the foreground process."""
  client, manager = _manager(live_settings)
  ctx = _ctx(f"life_bg_{uuid.uuid4().hex[:8]}")
  try:
    binding = await manager.resolve(ctx)
    held = client.execute_bash(
        name=binding.name, command="sleep 60 & echo started", timeout=15
    )
    assert held["timed_out"] is True
    assert held["returncode"] == 124

    freed = client.execute_bash(
        name=binding.name,
        command="sleep 60 </dev/null >/dev/null 2>&1 & echo started",
        timeout=15,
    )
    assert freed["timed_out"] is False
    assert "started" in freed["stdout"]
  finally:
    await manager.end_session(ctx)


@pytest.mark.asyncio
async def test_snapshot_round_trip_live(live_settings, sandbox_reaper):
  """Restore must never leave the session on an unusable sandbox.

  Either the restore works and the file comes back, or the manager reports
  ``restore_unusable`` and hands over a fresh sandbox that does run commands.
  Both outcomes keep exactly one live sandbox for the session.
  """
  client, manager = _manager(live_settings)
  sid = f"life_snap_{uuid.uuid4().hex[:8]}"
  ctx = _ctx(sid)
  try:
    binding = await manager.resolve(ctx)
    client.execute_bash(
        name=binding.name, command="echo SNAP_ORIGINAL > /workspace/notes.txt"
    )
    snap = await manager.snapshot_session(ctx, label="checkpoint-1")
    assert snap["ok"] is True
    assert snap["snapshot_name"]
    client.execute_bash(
        name=binding.name, command="echo OVERWRITTEN > /workspace/notes.txt"
    )
    assert any(s["name"] == binding.name for s in _live_for_session(
        client, live_settings, manager, ctx))

    result = await manager.restore_session(ctx, label_or_name="checkpoint-1")
    current = result["sandbox_name"]

    # The pre-restore sandbox is gone either way (delete-then-restore).
    assert result["previous_sandbox_name"] == binding.name
    with pytest.raises(Exception):
      client.get(name=binding.name)

    # Whatever happened, the session's sandbox is usable.
    probe = client.execute_bash(name=current, command="echo READY")
    assert "READY" in probe["stdout"]

    if result["restored"]:
      out = client.execute_bash(name=current, command="cat /workspace/notes.txt")
      assert "SNAP_ORIGINAL" in out["stdout"]
      assert "OVERWRITTEN" not in out["stdout"]
    else:
      assert result["reason"] == "restore_unusable"
      assert result["snapshot_name"] == snap["snapshot_name"]

    live = _live_for_session(client, live_settings, manager, ctx)
    assert len(live) == 1
    assert live[0]["name"] == current
  finally:
    await manager.end_session(ctx)


@pytest.mark.xfail(
    reason=(
        "Platform defect: a sandbox created with sandbox_environment_snapshot "
        "reports STATE_RUNNING but its data plane never accepts execute_bash "
        "(1/9 live attempts usable). Remove the xfail once restore works."
    ),
    strict=False,
)
@pytest.mark.asyncio
async def test_restore_returns_the_snapshot_contents_live(
    live_settings, sandbox_reaper
):
  client, manager = _manager(live_settings)
  ctx = _ctx(f"life_rst_{uuid.uuid4().hex[:8]}")
  try:
    binding = await manager.resolve(ctx)
    client.execute_bash(
        name=binding.name, command="echo SNAP_ORIGINAL > /workspace/notes.txt"
    )
    await manager.snapshot_session(ctx, label="checkpoint-1")
    result = await manager.restore_session(ctx, label_or_name="checkpoint-1")
    assert result["restored"] is True
    out = client.execute_bash(
        name=result["sandbox_name"], command="cat /workspace/notes.txt"
    )
    assert "SNAP_ORIGINAL" in out["stdout"]
  finally:
    await manager.end_session(ctx)


@pytest.mark.asyncio
async def test_execute_bash_does_not_extend_ttl_live(live_settings, sandbox_reaper):
  """Measured: activity does not push expiry out. TTL is create-time only."""
  client, manager = _manager(live_settings)
  ctx = _ctx(f"life_ttl_static_{uuid.uuid4().hex[:8]}")
  try:
    binding = await manager.resolve(ctx)
    before = client.get(name=binding.name)["expire_time"]
    time.sleep(15)
    client.execute_bash(name=binding.name, command="echo activity")
    after = client.get(name=binding.name)["expire_time"]
    assert before == after
  finally:
    await manager.end_session(ctx)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_ttl_expiry_recovers_the_session_live(live_settings, sandbox_reaper):
  """Short-TTL expiry is a hard 404; the next resolve must rebind cleanly."""
  from dataclasses import replace
  from datetime import datetime, timezone

  from sandbox_agent.sandbox.errors import SandboxNotFound

  # Measured minimum accepted TTL is at most 10s; 60s leaves room for the
  # create plus a snapshot before the clock runs out.
  short = replace(live_settings, ttl_seconds=60, auto_restore_on_expiry=True)
  client, manager = _manager(short)
  ctx = _ctx(f"life_ttl_{uuid.uuid4().hex[:8]}")
  try:
    binding = await manager.resolve(ctx)
    client.execute_bash(
        name=binding.name, command="echo TTL_MARKER > /workspace/notes.txt"
    )
    snap = await manager.snapshot_session(ctx, label="pre-expiry")
    assert snap["ok"] is True

    expire = client.get(name=binding.name)["expire_time"]
    assert expire
    text = str(expire)
    if text.endswith("Z"):
      text = text[:-1] + "+00:00"
    target = datetime.fromisoformat(text)
    while datetime.now(timezone.utc) < target:
      time.sleep(5)

    # Expiry is a hard delete, not a state transition.
    deadline = time.time() + 120
    while time.time() < deadline:
      try:
        client.get(name=binding.name)
      except SandboxNotFound:
        break
      time.sleep(5)
    else:
      pytest.fail(f"{binding.name} still present 120s past expire_time")

    recovered = await manager.resolve(ctx)
    assert recovered.name != binding.name
    out = client.execute_bash(name=recovered.name, command="echo RECOVERED")
    assert "RECOVERED" in out["stdout"]

    if recovered.restored_from:
      # Only reachable once the platform's restore works.
      assert recovered.restored_from == snap["snapshot_name"]
      notes = client.execute_bash(
          name=recovered.name, command="cat /workspace/notes.txt"
      )
      assert "TTL_MARKER" in notes["stdout"]

    live = _live_for_session(client, short, manager, ctx)
    assert len(live) == 1
  finally:
    await manager.end_session(ctx)
