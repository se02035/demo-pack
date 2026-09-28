"""Live integration tests: one distinct sandbox per ADK session."""

from __future__ import annotations

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
  a = await manager.resolve(ctx(sid_a))
  b = await manager.resolve(ctx(sid_b))
  assert a.name != b.name

  got_a = client.get(name=a.name)
  got_b = client.get(name=b.name)
  assert got_a["state"] == "STATE_RUNNING"
  assert got_b["state"] == "STATE_RUNNING"
  assert sid_a in (got_a.get("display_name") or a.display_name)
  assert sid_b in (got_b.get("display_name") or b.display_name)

  await manager.end_session(ctx(sid_a))
  # Rebuild a context with the binding still... end_session needs state.
  # We already deleted via manager cache; delete b too.
  client.delete(name=b.name)


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

    def run(session_id: str, marker: str):
      body = {
          "appName": "sandbox_agent",
          "userId": user,
          "sessionId": session_id,
          "newMessage": {
              "role": "user",
              "parts": [{"text": prompt.replace("MARKER_VALUE", marker)}],
          },
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

    # Assertion E — reuse within session
    events_a2 = run(s_alpha, "ALPHA2")
    sa2 = http.get(f"/apps/sandbox_agent/users/{user}/sessions/{s_alpha}").json()
    assert (sa2.get("state") or {}).get("sandbox", {}).get("name") == name_a
    names_a2 = _extract_sandbox_names_from_events(events_a2)
    if names_a2:
      assert names_a2 == {name_a}

    # Assertion F — explicit teardown via tool
    end_body = {
        "appName": "sandbox_agent",
        "userId": user,
        "sessionId": s_beta,
        "newMessage": {
            "role": "user",
            "parts": [{"text": "Call end_sandbox_session now."}],
        },
    }
    end_resp = http.post("/run", json=end_body)
    assert end_resp.status_code == 200, end_resp.text
