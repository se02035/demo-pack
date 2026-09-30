"""Live isolation proof for SessionSandboxEnvironment (ADC, no LLM)."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import load_dotenv
from google.adk.sessions.state import State

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "agents" / "env_sandbox_agent" / ".env"
if ENV_FILE.exists():
  load_dotenv(ENV_FILE, override=False)

from tests.integration.conftest import requires_live  # noqa: E402

pytestmark = [pytest.mark.integration, requires_live]


def _tool_context(
    session_id: str,
    *,
    value: dict | None = None,
    delta: dict | None = None,
) -> SimpleNamespace:
  """Mimic ADK ToolContext with delta-aware ``State`` (like production)."""
  session_value = value if value is not None else {}
  state_delta = delta if delta is not None else {}
  session = SimpleNamespace(
      id=session_id,
      user_id="iso_user",
      app_name="env_sandbox_agent",
      state=session_value,
  )
  return SimpleNamespace(
      session=session,
      state=State(value=session_value, delta=state_delta),
  )


@pytest.mark.asyncio
async def test_shell_environment_session_isolation():
  """Write on session A; session B must not see the file."""
  from env_sandbox_agent.environment import (
      SessionSandboxEnvironment,
      _delete_sandbox,
      set_current_tool_context,
  )

  env = SessionSandboxEnvironment("shell")
  await env.initialize()

  sid_a = f"env_a_{uuid.uuid4().hex[:8]}"
  sid_b = f"env_b_{uuid.uuid4().hex[:8]}"
  state_a: dict = {}
  state_b: dict = {}
  ctx_a = SimpleNamespace(
      session=SimpleNamespace(
          id=sid_a, user_id="iso_user", app_name="env_sandbox_agent", state=state_a
      ),
      state=state_a,
  )
  ctx_b = SimpleNamespace(
      session=SimpleNamespace(
          id=sid_b, user_id="iso_user", app_name="env_sandbox_agent", state=state_b
      ),
      state=state_b,
  )
  marker = f"secret-from-{sid_a}"
  path = Path("/workspace/secret-a.txt")
  created: list[str] = []

  try:
    set_current_tool_context(ctx_a)
    await env.write_file(path, marker)
    content_a = await env.read_file(path)
    assert content_a.decode("utf-8") == marker

    binding_a = state_a["sandbox_shell"]
    assert binding_a["display_name"] == f"sandbox-{sid_a}-shell"
    created.append(binding_a["name"])

    set_current_tool_context(
        SimpleNamespace(
            session=SimpleNamespace(
                id=sid_a,
                user_id="iso_user",
                app_name="env_sandbox_agent",
                state=state_a,
            ),
            state=state_a,
        )
    )
    again = await env.execute("true")
    assert again.exit_code == 0
    assert state_a["sandbox_shell"]["name"] == binding_a["name"]

    set_current_tool_context(ctx_b)
    with pytest.raises(FileNotFoundError):
      await env.read_file(path)

    binding_b = state_b["sandbox_shell"]
    assert binding_b["name"] != binding_a["name"]
    assert binding_b["display_name"] == f"sandbox-{sid_b}-shell"
    created.append(binding_b["name"])
  finally:
    for name in created:
      _delete_sandbox(name)


@pytest.mark.asyncio
async def test_sandbox_reused_across_turns_via_state_delta(monkeypatch):
  """Regression: binding must persist via tool_context.state state_delta.

  Reproduces the Playground failure mode: turn 1 creates a sandbox; turn 2
  loads only what ADK would have committed from the tool event's state_delta.
  Exactly one platform create must happen.
  """
  import env_sandbox_agent.environment as env_mod
  from env_sandbox_agent.environment import (
      SessionSandboxEnvironment,
      _delete_sandbox,
      set_current_tool_context,
  )

  create_calls: list[str] = []
  real_create = env_mod._create_sandbox

  def counting_create(flavour, display_name):
    name = real_create(flavour, display_name)
    create_calls.append(name)
    return name

  monkeypatch.setattr(env_mod, "_create_sandbox", counting_create)

  env = SessionSandboxEnvironment("shell")
  await env.initialize()

  sid = f"env_reuse_{uuid.uuid4().hex[:8]}"
  path = Path("/workspace/reuse-marker.txt")
  marker = f"reuse-{sid}"
  created: list[str] = []

  try:
    # --- Turn 1: empty session; tool writes into State delta ---
    turn1_value: dict = {}
    turn1_delta: dict = {}
    set_current_tool_context(_tool_context(sid, value=turn1_value, delta=turn1_delta))
    await env.write_file(path, marker)

    assert "sandbox_shell" in turn1_delta, (
        "binding must land in state_delta so ADK can persist it"
    )
    binding = turn1_delta["sandbox_shell"]
    created.append(binding["name"])
    assert len(create_calls) == 1

    # --- Session service commit: only state_delta is saved ---
    committed = dict(turn1_delta)

    # --- Turn 2: fresh ToolContext, committed state, empty delta ---
    set_current_tool_context(_tool_context(sid, value=committed, delta={}))
    content = await env.read_file(path)
    assert content.decode("utf-8") == marker
    assert len(create_calls) == 1, (
        f"expected reuse; create was called {len(create_calls)} times: {create_calls}"
    )
    assert committed["sandbox_shell"]["name"] == binding["name"]
  finally:
    for name in created:
      _delete_sandbox(name)
