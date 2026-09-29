"""Unit tests for behaviour the live Phase 0 run forced into the design.

Measured on `crafty-progress-421108` / `us-central1`: a restore-from-snapshot
sandbox reports STATE_RUNNING within seconds but its data plane almost never
answers, and the API refuses to snapshot anything that is not exactly
STATE_RUNNING. See docs/sandbox-learnings.md §12.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sandbox_agent.sandbox.errors import SandboxRestoreUnusable


def _ctx(session_id: str = "s1", user_id: str = "u1", state: dict | None = None):
  return SimpleNamespace(
      session=SimpleNamespace(app_name="sandbox_agent", user_id=user_id, id=session_id),
      state=state if state is not None else {},
  )


@pytest.mark.asyncio
async def test_probe_ready_reports_unreachable_sandbox(manager, fake_client):
  binding = await manager.resolve(_ctx("s_probe"))
  fake_client.unreachable_names.add(binding.name)
  assert await manager._probe_ready(binding.name) is False


@pytest.mark.asyncio
async def test_probe_ready_retries_until_the_data_plane_wakes(manager, fake_client):
  """The first execute_bash after create can fail for ~20s; don't give up."""
  binding = await manager.resolve(_ctx("s_slow"))
  fake_client.unreachable_names.add(binding.name)
  calls = {"n": 0}
  original = fake_client.execute_bash

  def flaky(**kwargs):
    calls["n"] += 1
    if calls["n"] >= 2:
      fake_client.unreachable_names.discard(binding.name)
    return original(**kwargs)

  fake_client.execute_bash = flaky
  assert await manager._probe_ready(binding.name) is True
  assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_unusable_restore_falls_back_to_a_fresh_sandbox(manager, fake_client):
  ctx = _ctx("s_restore")
  original = await manager.resolve(ctx)
  snap = await manager.snapshot_session(ctx, label="ckpt")
  assert snap["ok"] is True

  fake_client.unreachable_from_snapshot = True
  result = await manager.restore_session(ctx, label_or_name="ckpt")

  assert result["restored"] is False
  assert result["reason"] == "restore_unusable"
  # The session still ends up on a sandbox that actually works.
  fresh = result["sandbox_name"]
  assert fresh not in fake_client.unreachable_names
  assert fake_client.get(name=fresh)["state"] == "STATE_RUNNING"
  assert manager.read_binding(ctx.state).name == fresh
  # And never more than one live sandbox for the session.
  assert original.name not in fake_client.sandboxes
  assert result["snapshot_name"] == snap["snapshot_name"]


@pytest.mark.asyncio
async def test_unusable_restore_is_deleted_not_leaked(manager, fake_client):
  ctx = _ctx("s_leak")
  await manager.resolve(ctx)
  await manager.snapshot_session(ctx, label="ckpt")
  fake_client.unreachable_from_snapshot = True

  result = await manager.restore_session(ctx, label_or_name="ckpt")

  live = [n for n in fake_client.sandboxes if n != result["sandbox_name"]]
  assert live == []


@pytest.mark.asyncio
async def test_auto_restore_on_expiry_prefers_a_working_empty_sandbox(
    manager, fake_client
):
  ctx = _ctx("s_expiry")
  binding = await manager.resolve(ctx)
  await manager.snapshot_session(ctx, label="pre-expiry")

  # TTL expiry is a hard delete: the name simply 404s afterwards.
  fake_client.delete(name=binding.name)
  fake_client.unreachable_from_snapshot = True

  recovered = await manager.resolve(ctx)

  assert recovered.name != binding.name
  assert recovered.restored_from is None
  assert recovered.name not in fake_client.unreachable_names
  assert fake_client.execute_bash(name=recovered.name, command="true")["returncode"] == 0


@pytest.mark.asyncio
async def test_auto_restore_used_when_the_restore_is_healthy(manager, fake_client):
  ctx = _ctx("s_expiry_ok")
  binding = await manager.resolve(ctx)
  snap = await manager.snapshot_session(ctx, label="pre-expiry")
  fake_client.delete(name=binding.name)

  recovered = await manager.resolve(ctx)

  assert recovered.restored_from == snap["snapshot_name"]


@pytest.mark.asyncio
async def test_snapshot_waits_for_running_instead_of_failing_on_resuming(
    manager, fake_client
):
  """Any execute_bash against a paused sandbox makes the platform start a
  resume, so STATE_RESUMING is easy to hit; snapshotting it is rejected."""
  ctx = _ctx("s_resuming")
  binding = await manager.resolve(ctx)
  await manager.pause_session(ctx)
  fake_client.pending_states[binding.name] = [
      "STATE_PAUSED",
      "STATE_RESUMING",
      "STATE_RESUMING",
  ]

  result = await manager.snapshot_session(ctx, label="ckpt")

  assert result["ok"] is True
  assert fake_client.snapshot_create_calls == 1
  assert fake_client.get(name=binding.name)["state"] == "STATE_RUNNING"


@pytest.mark.asyncio
async def test_snapshot_of_a_dead_sandbox_does_not_hang(manager, fake_client):
  ctx = _ctx("s_dead")
  binding = await manager.resolve(ctx)
  fake_client.pending_states[binding.name] = ["STATE_TERMINATED"] * 10

  from sandbox_agent.sandbox.errors import SandboxUnavailable

  with pytest.raises(SandboxUnavailable):
    await manager.snapshot_session(ctx, label="ckpt")
  assert fake_client.snapshot_create_calls == 0


@pytest.mark.asyncio
async def test_create_raises_restore_unusable_rather_than_binding_it(
    manager, fake_client
):
  ctx = _ctx("s_raise")
  await manager.resolve(ctx)
  snap = await manager.snapshot_session(ctx, label="ckpt")
  fake_client.unreachable_from_snapshot = True
  key = manager.session_key_from_context(ctx)

  with pytest.raises(SandboxRestoreUnusable):
    await manager._create(key, from_snapshot=snap["snapshot_name"])


@pytest.mark.asyncio
async def test_failed_resume_deletes_old_sandbox_before_replace(
    manager, fake_client
):
  """A paused sandbox whose data plane never wakes must not leave two live
  sandboxes for the session when resolve falls back to a fresh create."""
  from sandbox_agent.sandbox.models import STATE_SANDBOX_HISTORY_KEY

  ctx = _ctx("s_resume_dead")
  binding = await manager.resolve(ctx)
  await manager.pause_session(ctx)
  fake_client.unreachable_names.add(binding.name)

  recovered = await manager.resolve(ctx)

  assert recovered.name != binding.name
  assert binding.name not in fake_client.sandboxes
  assert recovered.name in fake_client.sandboxes
  assert ctx.state[STATE_SANDBOX_HISTORY_KEY] == [binding.name]
  # delete(old) must precede create(new)
  delete_idxs = [
      i for i, (op, name) in enumerate(fake_client.call_order)
      if op == "delete" and name == binding.name
  ]
  create_idxs = [
      i for i, (op, name) in enumerate(fake_client.call_order)
      if op == "create" and name == recovered.name
  ]
  assert delete_idxs and create_idxs
  assert delete_idxs[0] < create_idxs[0]
