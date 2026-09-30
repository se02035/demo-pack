"""Unit tests: sandbox binding must persist via tool_context.state delta."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.adk.sessions.state import State


@pytest.mark.asyncio
async def test_resolve_writes_binding_into_state_delta(monkeypatch):
  """ADK only persists event state_delta — not raw session.state mutations."""
  import env_sandbox_agent.environment as env_mod
  from env_sandbox_agent.environment import resolve_sandbox, set_current_tool_context

  monkeypatch.setattr(
      env_mod, "_create_sandbox", lambda flavour, display_name: "projects/x/sandboxes/1"
  )
  monkeypatch.setattr(env_mod, "_probe_ready", lambda name, flavour: None)
  monkeypatch.setattr(
      env_mod, "_get_sandbox", lambda name: {"name": name, "state": "STATE_RUNNING"}
  )

  session_value: dict = {}
  state_delta: dict = {}
  session = SimpleNamespace(id="111", state=session_value)
  tool_context = SimpleNamespace(
      session=session,
      state=State(value=session_value, delta=state_delta),
  )
  set_current_tool_context(tool_context)

  name = await resolve_sandbox("shell")
  assert name == "projects/x/sandboxes/1"
  assert "sandbox_shell" in state_delta
  assert state_delta["sandbox_shell"]["name"] == name
  assert state_delta["sandbox_shell"]["display_name"] == "sandbox-111-shell"

  # Simulate ADK session commit + next turn (only delta is restored).
  committed = dict(state_delta)
  creates = {"n": 0}

  def create_again(flavour, display_name):
    creates["n"] += 1
    return "projects/x/sandboxes/SHOULD_NOT_HAPPEN"

  monkeypatch.setattr(env_mod, "_create_sandbox", create_again)
  set_current_tool_context(
      SimpleNamespace(
          session=SimpleNamespace(id="111", state=committed),
          state=State(value=committed, delta={}),
      )
  )
  reused = await resolve_sandbox("shell")
  assert reused == name
  assert creates["n"] == 0


@pytest.mark.asyncio
async def test_raw_session_state_write_would_not_survive_commit():
  """Documents the bug: writing session.state alone leaves an empty delta."""
  session_value: dict = {}
  state_delta: dict = {}
  # What the old code did: mutate session.state (the value dict) directly.
  session_value["sandbox_shell"] = {"name": "projects/x/sandboxes/1"}
  # What ADK would commit from the tool event:
  committed = dict(state_delta)
  assert committed == {}
  assert "sandbox_shell" not in committed
