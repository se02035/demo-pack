"""Live integration tests: one distinct sandbox per ADK session."""

from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import httpx
import pytest

from tests.integration.conftest import requires_live

pytestmark = [pytest.mark.integration, requires_live]


def _extract_sandbox_names_from_events(events: list) -> set[str]:
  names: set[str] = set()
  for event in events:
    content = event.get("content") or {}
    for part in content.get("parts") or []:
      fr = part.get("functionResponse") or {}
      resp = fr.get("response") or {}
      if isinstance(resp, dict) and resp.get("sandbox_name"):
        names.add(resp["sandbox_name"])
  return names


def _tool_responses(events: list, tool_name: str | None = None) -> list[dict]:
  """Structured functionResponse payloads, never the model's prose."""
  out: list[dict] = []
  for event in events:
    content = event.get("content") or {}
    for part in content.get("parts") or []:
      fr = part.get("functionResponse") or {}
      if not fr:
        continue
      if tool_name is not None and fr.get("name") != tool_name:
        continue
      resp = fr.get("response")
      if isinstance(resp, dict):
        out.append(resp)
  return out


@pytest.mark.asyncio
async def test_manager_creates_distinct_sandboxes_live(live_settings, sandbox_reaper):
  """Non-LLM control: two session keys -> two platform sandboxes."""
  from sandbox_agent.sandbox.client import SandboxClient
  from sandbox_agent.sandbox.manager import SessionSandboxManager

  client = SandboxClient(
      project=live_settings.project, location=live_settings.sandbox_location
  )
  manager = SessionSandboxManager(client=client, settings=live_settings)

  def ctx(session_id: str):
    return SimpleNamespace(
        session=SimpleNamespace(
            app_name="sandbox_agent", user_id="iso_user", id=session_id
        ),
        state={},
    )

  sid_a = f"ctrl_a_{uuid.uuid4().hex[:8]}"
  sid_b = f"ctrl_b_{uuid.uuid4().hex[:8]}"
  ctx_a, ctx_b = ctx(sid_a), ctx(sid_b)
  a = await manager.resolve(ctx_a)
  b = await manager.resolve(ctx_b)
  assert a.name != b.name

  got_a = client.get(name=a.name)
  got_b = client.get(name=b.name)
  assert got_a["state"] == "STATE_RUNNING"
  assert got_b["state"] == "STATE_RUNNING"
  assert sid_a in (got_a.get("display_name") or a.display_name)
  assert sid_b in (got_b.get("display_name") or b.display_name)

  try:
    # Re-resolving the same session must reuse, not provision again.
    assert (await manager.resolve(ctx_a)).name == a.name
    assert manager.create_counts[manager.session_key_from_context(ctx_a)] == 1

    # Filesystem isolation, measured directly rather than through the model.
    client.execute_bash(name=a.name, command="echo CTRL_ALPHA > /workspace/who")
    client.execute_bash(name=b.name, command="echo CTRL_BETA > /workspace/who")
    out_a = client.execute_bash(name=a.name, command="cat /workspace/who")["stdout"]
    out_b = client.execute_bash(name=b.name, command="cat /workspace/who")["stdout"]
    assert "CTRL_ALPHA" in out_a and "CTRL_BETA" not in out_a, out_a
    assert "CTRL_BETA" in out_b and "CTRL_ALPHA" not in out_b, out_b
  finally:
    # end_session resolves the binding from the manager cache, so the original
    # contexts are reused here.
    await manager.end_session(ctx_a)
    await manager.end_session(ctx_b)


@pytest.mark.asyncio
async def test_api_server_session_sandbox_isolation(
    live_settings, sandbox_reaper, api_server
):
  base = api_server
  user = f"u_iso_{uuid.uuid4().hex[:6]}"
  s_alpha = f"s_alpha_{uuid.uuid4().hex[:6]}"
  s_beta = f"s_beta_{uuid.uuid4().hex[:6]}"

  with httpx.Client(base_url=base, timeout=180.0) as http:
    for sid in (s_alpha, s_beta):
      r = http.post(f"/apps/sandbox_agent/users/{user}/sessions/{sid}", json={})
      assert r.status_code in (200, 201), r.text

    prompt = (
        "Call get_sandbox_info, then write the text MARKER_VALUE to "
        "/workspace/marker.txt using write_text_file, then call list_directory "
        "on /workspace. Do not skip the tools."
    )

    def run_prompt(session_id: str, text: str):
      body = {
          "appName": "sandbox_agent",
          "userId": user,
          "sessionId": session_id,
          "newMessage": {"role": "user", "parts": [{"text": text}]},
      }
      resp = http.post("/run", json=body)
      assert resp.status_code == 200, resp.text
      events = resp.json()
      assert isinstance(events, list)
      has_tool = any(
          any((p.get("functionCall") or p.get("functionResponse")) for p in ((e.get("content") or {}).get("parts") or []))
          for e in events
      )
      assert has_tool, f"Model did not call tools for {session_id}: {events!r}"
      return events

    def run(session_id: str, marker: str):
      return run_prompt(session_id, prompt.replace("MARKER_VALUE", marker))

    events_a = run(s_alpha, "ALPHA")
    events_b = run(s_beta, "BETA")

    # Assertion A — session state bindings
    sa = http.get(f"/apps/sandbox_agent/users/{user}/sessions/{s_alpha}").json()
    sb = http.get(f"/apps/sandbox_agent/users/{user}/sessions/{s_beta}").json()
    name_a = (sa.get("state") or {}).get("sandbox", {}).get("name")
    name_b = (sb.get("state") or {}).get("sandbox", {}).get("name")
    assert name_a and name_b, (sa, sb)
    assert name_a != name_b
    assert "/sandboxEnvironments/" in name_a
    assert "/sandboxEnvironments/" in name_b

    # Assertion B — platform ground truth
    import agentplatform

    client = agentplatform.Client(
        project=live_settings.project, location=live_settings.sandbox_location
    )
    env_a = client.sandboxes.get(name=name_a)
    env_b = client.sandboxes.get(name=name_b)
    assert str(env_a.state).endswith("RUNNING") or env_a.state.value == "STATE_RUNNING"
    assert str(env_b.state).endswith("RUNNING") or env_b.state.value == "STATE_RUNNING"
    assert s_alpha in (env_a.display_name or "")
    assert s_beta in (env_b.display_name or "")

    # Assertion C — tool responses also agree
    names_from_events = _extract_sandbox_names_from_events(events_a) | _extract_sandbox_names_from_events(events_b)
    assert name_a in names_from_events
    assert name_b in names_from_events

    # Assertion D — exactly two sandboxes for this user, not three.
    # Catches accidental extra provisioning (e.g. an eager create racing a
    # lazy one). Filtered client-side: the list filter grammar for
    # sandboxEnvironments is undocumented.
    owned_prefix = f"{live_settings.display_name_prefix}-{user}-"
    owned = [
        s
        for s in client.sandboxes.list(name=live_settings.runtime_name)
        if (s.display_name or "").startswith(owned_prefix)
    ]
    assert len(owned) == 2, [
        (s.display_name, s.name, str(s.state)) for s in owned
    ]
    assert {s.name for s in owned} == {name_a, name_b}

    # Assertion E — the isolation is real, not just distinct resource names.
    # s_beta must never see the marker s_alpha wrote.
    read_events = run_prompt(
        s_beta,
        "Use read_text_file to read /workspace/marker.txt and show me exactly "
        "what it contains.",
    )
    beta_reads = [
        resp
        for resp in _tool_responses(read_events, "read_text_file")
        if resp.get("sandbox_name") == name_b
    ]
    assert beta_reads, _tool_responses(read_events)
    beta_content = " ".join(
        str(r.get("content") or r.get("stdout") or "") for r in beta_reads
    )
    assert "BETA" in beta_content, beta_content
    assert "ALPHA" not in beta_content, beta_content

    # Assertion F — one sandbox per session, not one per turn.
    events_a2 = run(s_alpha, "ALPHA2")
    sa2 = http.get(f"/apps/sandbox_agent/users/{user}/sessions/{s_alpha}").json()
    assert (sa2.get("state") or {}).get("sandbox", {}).get("name") == name_a
    names_a2 = _extract_sandbox_names_from_events(events_a2)
    if names_a2:
      assert names_a2 == {name_a}
    still_owned = [
        s
        for s in client.sandboxes.list(name=live_settings.runtime_name)
        if (s.display_name or "").startswith(owned_prefix)
    ]
    assert len(still_owned) == 2, [
        (s.display_name, s.name) for s in still_owned
    ]

    # Assertion G — explicit teardown really deletes the platform resource.
    run_prompt(s_beta, "Call end_sandbox_session now.")

  gone = False
  for _ in range(10):
    try:
      env = client.sandboxes.get(name=name_b)
    except Exception:  # noqa: BLE001 - NOT_FOUND is the success case
      gone = True
      break
    if str(env.state).endswith(("DELETED", "TERMINATED", "DEPROVISIONING")):
      gone = True
      break
    time.sleep(2)
  assert gone, f"{name_b} survived end_sandbox_session"
