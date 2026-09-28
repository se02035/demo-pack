"""Unit tests for pause/resume, snapshots, restore, and auto-recovery."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sandbox_agent.sandbox.models import STATE_SANDBOX_SNAPSHOTS_KEY


def _ctx(session_id: str = "s1", user_id: str = "u1", state: dict | None = None):
  return SimpleNamespace(
      session=SimpleNamespace(
          app_name="sandbox_agent", user_id=user_id, id=session_id
      ),
      state=state if state is not None else {},
  )


@pytest.mark.asyncio
async def test_pinned_template_reused_across_creates(manager, fake_client):
  a = await manager.resolve(_ctx("s_a"))
  b = await manager.resolve(_ctx("s_b"))
  assert a.name != b.name
  assert fake_client.template_create_calls == 1
  env_a = fake_client.get(name=a.name)
  env_b = fake_client.get(name=b.name)
  assert env_a["sandbox_environment_template"] == env_b["sandbox_environment_template"]
  assert env_a["sandbox_environment_template"]


@pytest.mark.asyncio
async def test_pause_then_resolve_resumes_without_create(manager, fake_client):
  ctx = _ctx("s_pause")
  binding = await manager.resolve(ctx)
  paused = await manager.pause_session(ctx)
  assert paused["paused"] is True
  assert fake_client.get(name=binding.name)["state"] == "STATE_PAUSED"

  creates_before = fake_client.create_calls
  resumes_before = fake_client.resume_calls
  again = await manager.resolve(ctx)
  assert again.name == binding.name
  assert fake_client.create_calls == creates_before
  assert fake_client.resume_calls == resumes_before + 1
  assert fake_client.get(name=binding.name)["state"] == "STATE_RUNNING"


@pytest.mark.asyncio
async def test_snapshot_is_session_scoped(manager, fake_client):
  ctx_a = _ctx("s_a", user_id="u_a")
  ctx_b = _ctx("s_b", user_id="u_b")
  await manager.resolve(ctx_a)
  await manager.resolve(ctx_b)

  snap_a = await manager.snapshot_session(ctx_a, label="ckpt")
  assert snap_a["ok"] is True
  assert manager.find_snapshot(ctx_a.state, "ckpt") is not None
  assert manager.find_snapshot(ctx_b.state, "ckpt") is None
  assert manager.find_snapshot(ctx_b.state, snap_a["snapshot_name"]) is None


@pytest.mark.asyncio
async def test_restore_rejects_foreign_snapshot_without_deleting(manager, fake_client):
  ctx_a = _ctx("s_a", user_id="u_a")
  ctx_b = _ctx("s_b", user_id="u_b")
  a = await manager.resolve(ctx_a)
  await manager.resolve(ctx_b)
  snap = await manager.snapshot_session(ctx_a, label="ckpt")

  deletes_before = fake_client.delete_calls
  result = await manager.restore_session(ctx_b, label_or_name=snap["snapshot_name"])
  assert result["ok"] is False
  assert result["reason"] == "snapshot_not_in_session"
  assert fake_client.delete_calls == deletes_before
  assert fake_client.get(name=a.name)["name"] == a.name


@pytest.mark.asyncio
async def test_restore_dead_snapshot_leaves_sandbox(manager, fake_client):
  ctx = _ctx("s_restore_dead")
  binding = await manager.resolve(ctx)
  snap = await manager.snapshot_session(ctx, label="ckpt")
  fake_client.fail_snapshot_names.add(snap["snapshot_name"])

  deletes_before = fake_client.delete_calls
  result = await manager.restore_session(ctx, label_or_name="ckpt")
  assert result["ok"] is False
  assert result["reason"] == "snapshot_not_found"
  assert fake_client.delete_calls == deletes_before
  assert fake_client.get(name=binding.name)["name"] == binding.name


@pytest.mark.asyncio
async def test_restore_delete_then_create_ordering_and_filesystem(manager, fake_client):
  ctx = _ctx("s_restore")
  binding = await manager.resolve(ctx)
  fake_client.sandboxes[binding.name]["files"]["/workspace/notes.txt"] = "before"
  snap = await manager.snapshot_session(ctx, label="ckpt")
  fake_client.sandboxes[binding.name]["files"]["/workspace/notes.txt"] = "after"

  fake_client.call_order.clear()
  result = await manager.restore_session(ctx, label_or_name="ckpt")
  assert result["ok"] is True
  assert result["restored"] is True
  assert result["sandbox_name"] != binding.name
  assert result["previous_sandbox_name"] == binding.name

  ops = [op for op, _ in fake_client.call_order if op in {"delete", "create"}]
  assert ops[:2] == ["delete", "create"]
  # Never two live sandboxes for this session's names mid-flight: old is gone.
  assert binding.name not in fake_client.sandboxes
  new_files = fake_client.sandboxes[result["sandbox_name"]]["files"]
  assert new_files.get("/workspace/notes.txt") == "before"
  assert ctx.state["sandbox"]["restored_from"] == snap["snapshot_name"]


@pytest.mark.asyncio
async def test_expiry_auto_restores_from_newest_snapshot(manager, fake_client, settings_env):
  assert settings_env.auto_restore_on_expiry is True
  ctx = _ctx("s_expiry")
  binding = await manager.resolve(ctx)
  fake_client.sandboxes[binding.name]["files"]["/workspace/notes.txt"] = "kept"
  snap = await manager.snapshot_session(ctx, label="ckpt")
  # Simulate TTL expiry / out-of-band delete.
  fake_client.sandboxes.pop(binding.name)

  creates_before = fake_client.create_calls
  recovered = await manager.resolve(ctx)
  assert recovered.name != binding.name
  assert recovered.restored_from == snap["snapshot_name"]
  assert fake_client.create_calls == creates_before + 1
  # The create used the snapshot seed.
  assert (
      fake_client.sandboxes[recovered.name]["sandbox_environment_snapshot"]
      == snap["snapshot_name"]
  )
  assert (
      fake_client.sandboxes[recovered.name]["files"]["/workspace/notes.txt"] == "kept"
  )


@pytest.mark.asyncio
async def test_expiry_without_snapshot_creates_empty(manager, fake_client):
  ctx = _ctx("s_expiry_empty")
  binding = await manager.resolve(ctx)
  fake_client.sandboxes.pop(binding.name)
  recovered = await manager.resolve(ctx)
  assert recovered.restored_from is None
  assert fake_client.sandboxes[recovered.name]["sandbox_environment_snapshot"] is None


@pytest.mark.asyncio
async def test_idle_delete_snapshots_then_deletes(manager, fake_client):
  ctx = _ctx("s_idle")
  binding = await manager.resolve(ctx)
  key = manager.session_key_from_context(ctx)
  # Force idle.
  manager._last_used[key] = 0.0
  fake_client.call_order.clear()
  deleted = await manager.delete_idle(older_than_seconds=0)
  assert binding.name in deleted
  ops = [op for op, _ in fake_client.call_order]
  assert "create_snapshot" in ops
  assert ops.index("create_snapshot") < ops.index("delete")
  assert binding.name not in fake_client.sandboxes


@pytest.mark.asyncio
async def test_snapshot_cap_evicts_oldest_auto_only(manager, fake_client, settings_env, monkeypatch):
  monkeypatch.setenv("SANDBOX_MAX_SNAPSHOTS_PER_SESSION", "3")
  from sandbox_agent.config import get_settings

  get_settings.cache_clear()
  manager._settings = get_settings()

  ctx = _ctx("s_cap")
  await manager.resolve(ctx)
  await manager.snapshot_session(ctx, label="manual", auto=False)
  for i in range(4):
    await manager.snapshot_session(ctx, label=f"auto-{i}", auto=True)

  records = manager.read_snapshots(ctx.state)
  assert len(records) <= 3
  labels = {r.label for r in records}
  assert "manual" in labels
  assert fake_client.snapshot_create_calls >= 5


@pytest.mark.asyncio
async def test_lifecycle_tools_wire_through(manager, fake_client, monkeypatch):
  from sandbox_agent.sandbox import runtime as sandbox_runtime
  from sandbox_agent.tools import lifecycle

  monkeypatch.setattr(sandbox_runtime, "get_manager", lambda: manager)
  ctx = _ctx("s_tools")
  # get_sandbox_lifecycle does not create.
  life = await lifecycle.get_sandbox_lifecycle(ctx)
  assert life["bound"] is False

  paused = await lifecycle.pause_sandbox(ctx)
  assert paused["ok"] is True
  assert fake_client.create_calls == 1

  snap = await lifecycle.snapshot_sandbox("demo", ctx)
  assert snap["ok"] is True
  listed = await lifecycle.list_snapshots(ctx)
  assert listed["count"] == 1

  restored = await lifecycle.restore_snapshot("demo", ctx)
  assert restored["restored"] is True
  assert STATE_SANDBOX_SNAPSHOTS_KEY in ctx.state
