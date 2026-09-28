"""Live lifecycle tests: pause/resume, snapshot restore, TTL recovery.

Skipped unless ADC + a real SANDBOX_RUNTIME_NAME are present. This session's
revoked key cannot run them — use a fresh agent run after rotating the secret.
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


@pytest.mark.asyncio
async def test_pause_preserves_disk_live(live_settings, sandbox_reaper):
  from sandbox_agent.sandbox.client import SandboxClient
  from sandbox_agent.sandbox.manager import SessionSandboxManager

  client = SandboxClient(
      project=live_settings.project, location=live_settings.sandbox_location
  )
  manager = SessionSandboxManager(client=client, settings=live_settings)
  ctx = _ctx(f"life_pause_{uuid.uuid4().hex[:8]}")
  try:
    binding = await manager.resolve(ctx)
    client.execute_bash(
        name=binding.name, command="echo BEFORE_PAUSE > /workspace/marker.txt"
    )
    paused = await manager.pause_session(ctx)
    assert paused["ok"] is True
    env = client.get(name=binding.name)
    assert env["state"] == "STATE_PAUSED"

    # Implicit resume via resolve / read.
    again = await manager.resolve(ctx)
    assert again.name == binding.name
    out = client.execute_bash(name=binding.name, command="cat /workspace/marker.txt")
    assert "BEFORE_PAUSE" in out["stdout"]
    assert client.get(name=binding.name)["state"] == "STATE_RUNNING"
  finally:
    await manager.end_session(ctx)


@pytest.mark.asyncio
async def test_snapshot_round_trip_live(live_settings, sandbox_reaper):
  from sandbox_agent.sandbox.client import SandboxClient
  from sandbox_agent.sandbox.manager import SessionSandboxManager

  client = SandboxClient(
      project=live_settings.project, location=live_settings.sandbox_location
  )
  manager = SessionSandboxManager(client=client, settings=live_settings)
  sid = f"life_snap_{uuid.uuid4().hex[:8]}"
  ctx = _ctx(sid)
  try:
    binding = await manager.resolve(ctx)
    client.execute_bash(
        name=binding.name, command="echo SNAP_ORIGINAL > /workspace/notes.txt"
    )
    snap = await manager.snapshot_session(ctx, label="checkpoint-1")
    assert snap["ok"] is True
    client.execute_bash(
        name=binding.name, command="echo OVERWRITTEN > /workspace/notes.txt"
    )

    # Exactly one live sandbox for this session before restore.
    owned_prefix = f"{live_settings.display_name_prefix}-life_user-{sid}"
    # display_name is prefix-user-session
    owned_prefix = manager.display_name_for(manager.session_key_from_context(ctx))
    before = [
        s for s in client.list(runtime_name=live_settings.runtime_name)
        if (s.get("display_name") or "") == owned_prefix
        or (s.get("display_name") or "").startswith(owned_prefix)
    ]
    # May be exactly 1 with our display name.
    assert any(s["name"] == binding.name for s in before)

    restored = await manager.restore_session(ctx, label_or_name="checkpoint-1")
    assert restored["restored"] is True
    assert restored["sandbox_name"] != binding.name
    assert restored["previous_sandbox_name"] == binding.name

    # Old sandbox gone.
    try:
      client.get(name=binding.name)
      pytest.fail("old sandbox still present after restore")
    except Exception:
      pass

    out = client.execute_bash(
        name=restored["sandbox_name"], command="cat /workspace/notes.txt"
    )
    assert "SNAP_ORIGINAL" in out["stdout"]
    assert "OVERWRITTEN" not in out["stdout"]

    live = [
        s for s in client.list(runtime_name=live_settings.runtime_name)
        if (s.get("display_name") or "").startswith(
            f"{live_settings.display_name_prefix}-life_user-"
        )
        and sid in (s.get("display_name") or "")
    ]
    assert len(live) == 1
    assert live[0]["name"] == restored["sandbox_name"]
  finally:
    await manager.end_session(ctx)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_ttl_expiry_auto_restore_live(live_settings, sandbox_reaper, monkeypatch):
  """Short-TTL expiry → auto-restore from snapshot. Needs a real short TTL."""
  from sandbox_agent.config import Settings, get_settings
  from sandbox_agent.sandbox.client import SandboxClient
  from sandbox_agent.sandbox.manager import SessionSandboxManager

  # Use the shortest TTL we dare without a Phase-0 measurement; 120s is the
  # documented quickstart-ish floor we use in demos. Marked slow.
  short = Settings(
      **{
          **live_settings.__dict__,
          "ttl_seconds": 120,
          "auto_restore_on_expiry": True,
      }
  )
  client = SandboxClient(
      project=short.project, location=short.sandbox_location
  )
  manager = SessionSandboxManager(client=client, settings=short)
  ctx = _ctx(f"life_ttl_{uuid.uuid4().hex[:8]}")
  try:
    binding = await manager.resolve(ctx)
    client.execute_bash(
        name=binding.name, command="echo TTL_MARKER > /workspace/notes.txt"
    )
    snap = await manager.snapshot_session(ctx, label="pre-expiry")
    assert snap["ok"] is True

    env = client.get(name=binding.name)
    expire = env.get("expire_time")
    assert expire, env

    # Wait until past expire_time + a small grace.
    from datetime import datetime, timezone

    text = str(expire)
    if text.endswith("Z"):
      text = text[:-1] + "+00:00"
    target = datetime.fromisoformat(text)
    while datetime.now(timezone.utc) < target:
      time.sleep(5)
    time.sleep(30)

    # Binding should be dead (or becoming so); resolve must restore.
    recovered = await manager.resolve(ctx)
    assert recovered.restored_from == snap["snapshot_name"]
    out = client.execute_bash(
        name=recovered.name, command="cat /workspace/notes.txt"
    )
    assert "TTL_MARKER" in out["stdout"]
  finally:
    await manager.end_session(ctx)
    get_settings.cache_clear()
