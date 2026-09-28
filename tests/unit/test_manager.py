"""Unit tests for SessionSandboxManager (one-sandbox-per-session invariant)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sandbox_agent.sandbox.errors import SandboxNotFound, SandboxQuotaExceeded, SandboxUnavailable
from sandbox_agent.sandbox.models import STATE_SANDBOX_HISTORY_KEY, STATE_SANDBOX_KEY, SessionKey


class FakeState(dict):
  def get(self, key, default=None):  # noqa: A003
    return super().get(key, default)


def make_context(app_name: str, user_id: str, session_id: str, state: dict | None = None):
  return SimpleNamespace(
      session=SimpleNamespace(app_name=app_name, user_id=user_id, id=session_id),
      state=FakeState(state or {}),
  )


@pytest.mark.asyncio
async def test_one_resolution_creates_one_sandbox(manager, fake_client):
  ctx = make_context("sandbox_agent", "u1", "s1")
  binding = await manager.resolve(ctx)
  assert fake_client.create_calls == 1
  assert binding.name.endswith("/sandboxEnvironments/1")
  assert ctx.state[STATE_SANDBOX_KEY]["name"] == binding.name


@pytest.mark.asyncio
async def test_ten_resolutions_same_session_one_create(manager, fake_client):
  ctx = make_context("sandbox_agent", "u1", "s1")
  names = [(await manager.resolve(ctx)).name for _ in range(10)]
  assert fake_client.create_calls == 1
  assert len(set(names)) == 1


@pytest.mark.asyncio
async def test_concurrent_resolutions_same_session_one_create(manager, fake_client):
  fake_client.create_latency_s = 0.05
  ctx = make_context("sandbox_agent", "u1", "s-concurrent")

  results = await asyncio.gather(*[manager.resolve(ctx) for _ in range(10)])
  assert fake_client.create_calls == 1
  assert len({b.name for b in results}) == 1


@pytest.mark.asyncio
async def test_two_sessions_two_sandboxes(manager, fake_client):
  a = make_context("sandbox_agent", "u1", "s_alpha")
  b = make_context("sandbox_agent", "u1", "s_beta")
  ba = await manager.resolve(a)
  bb = await manager.resolve(b)
  assert fake_client.create_calls == 2
  assert ba.name != bb.name
  assert ba.name not in (bb.name,)
  assert a.state[STATE_SANDBOX_KEY]["name"] == ba.name
  assert b.state[STATE_SANDBOX_KEY]["name"] == bb.name


@pytest.mark.asyncio
async def test_same_session_id_different_users(manager, fake_client):
  a = make_context("sandbox_agent", "alice", "s_123")
  b = make_context("sandbox_agent", "bob", "s_123")
  ba = await manager.resolve(a)
  bb = await manager.resolve(b)
  assert ba.name != bb.name
  assert fake_client.create_calls == 2


@pytest.mark.asyncio
async def test_cache_miss_reuses_session_state(manager, fake_client):
  ctx = make_context("sandbox_agent", "u1", "s_persist")
  first = await manager.resolve(ctx)
  assert fake_client.create_calls == 1

  # Simulate process reload: clear in-process cache, keep session state.
  manager._cache.clear()
  second = await manager.resolve(ctx)
  assert fake_client.create_calls == 1
  assert second.name == first.name


@pytest.mark.asyncio
async def test_not_found_recreates_and_records_history(manager, fake_client):
  ctx = make_context("sandbox_agent", "u1", "s_gone")
  first = await manager.resolve(ctx)
  manager._cache.clear()
  fake_client.fail_get_names.add(first.name)
  # Also remove from store so get fails even after fail_get_names cleared later
  fake_client.sandboxes.pop(first.name, None)

  second = await manager.resolve(ctx)
  assert fake_client.create_calls == 2
  assert second.name != first.name
  assert first.name in ctx.state[STATE_SANDBOX_HISTORY_KEY]


@pytest.mark.asyncio
async def test_paused_sandbox_is_resumed(manager, fake_client):
  ctx = make_context("sandbox_agent", "u1", "s_paused")
  first = await manager.resolve(ctx)
  fake_client.sandboxes[first.name]["state"] = "STATE_PAUSED"
  manager._cache.clear()

  second = await manager.resolve(ctx)
  assert second.name == first.name
  assert fake_client.resume_calls == 1
  assert fake_client.create_calls == 1


@pytest.mark.asyncio
async def test_terminated_sandbox_is_recreated(manager, fake_client):
  ctx = make_context("sandbox_agent", "u1", "s_dead")
  first = await manager.resolve(ctx)
  fake_client.sandboxes[first.name]["state"] = "STATE_TERMINATED"
  manager._cache.clear()

  second = await manager.resolve(ctx)
  assert second.name != first.name
  assert fake_client.create_calls == 2


@pytest.mark.asyncio
async def test_create_failure_leaves_no_binding(manager, fake_client):
  fake_client.fail_create_with = SandboxUnavailable("boom")
  ctx = make_context("sandbox_agent", "u1", "s_fail")
  with pytest.raises(SandboxUnavailable):
    await manager.resolve(ctx)
  assert STATE_SANDBOX_KEY not in ctx.state
  assert manager._cache == {}


@pytest.mark.asyncio
async def test_quota_exceeded_propagates(manager, fake_client):
  fake_client.fail_create_with = SandboxQuotaExceeded("quota")
  ctx = make_context("sandbox_agent", "u1", "s_quota")
  with pytest.raises(SandboxQuotaExceeded):
    await manager.resolve(ctx)
  assert STATE_SANDBOX_KEY not in ctx.state


@pytest.mark.asyncio
async def test_end_session_deletes_and_clears(manager, fake_client):
  ctx = make_context("sandbox_agent", "u1", "s_end")
  binding = await manager.resolve(ctx)
  result = await manager.end_session(ctx)
  assert result["deleted"] is True
  assert result["sandbox_name"] == binding.name
  assert fake_client.delete_calls == 1
  assert binding.name not in fake_client.sandboxes
  assert manager._cache == {}

  # Next resolve creates a new sandbox.
  again = await manager.resolve(ctx)
  assert again.name != binding.name
  assert fake_client.create_calls == 2


@pytest.mark.asyncio
async def test_display_name_contains_session_id(manager, fake_client):
  ctx = make_context("sandbox_agent", "u1", "s_unique_42")
  binding = await manager.resolve(ctx)
  assert "s_unique_42" in binding.display_name
  assert binding.display_name.startswith("adk-demo-")
