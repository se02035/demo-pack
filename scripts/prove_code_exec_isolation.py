#!/usr/bin/env python3
"""Prove that AgentEngineSandboxCodeExecutor uses one sandbox per ADK session.

Drives ``adk api_server`` (or a local Runner fallback), runs two sessions, and
asserts:

1. Each session stores a distinct ``_code_execution_context.sandbox_name``.
2. Session A's Python variable does not leak into session B (NameError).
3. Filesystem isolation: neither sandbox can see the other's token files
   (checked via the executor directly, without the model).

Requires ADC (or GOOGLE_APPLICATION_CREDENTIALS) and a real
SANDBOX_RUNTIME_NAME. Deletes the sandboxes it created unless ``--keep``.

Usage:
  export GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT
  export SANDBOX_RUNTIME_NAME=projects/.../reasoningEngines/...
  python scripts/prove_code_exec_isolation.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"


def _env_ready() -> str:
  runtime = os.environ.get("SANDBOX_RUNTIME_NAME", "").strip()
  if not runtime or runtime.endswith("/RUNTIME_ID"):
    raise SystemExit(
        "Set SANDBOX_RUNTIME_NAME to a real runtime resource name before running."
    )
  if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
    raise SystemExit("Set GOOGLE_CLOUD_PROJECT.")
  return runtime


def _free_port() -> int:
  with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    return int(s.getsockname()[1])


def _sandbox_name_from_state(state: dict) -> str | None:
  ctx = state.get("_code_execution_context") or {}
  if isinstance(ctx, dict) and ctx.get("sandbox_name"):
    return str(ctx["sandbox_name"])
  top = state.get("sandbox_name")
  return str(top) if top else None


async def _run_via_runner(runtime: str) -> dict:
  """Drive two sessions through ADK Runner + InMemorySessionService."""
  from google.adk.agents.llm_agent import Agent
  from google.adk.artifacts import InMemoryArtifactService
  from google.adk.code_executors.agent_engine_sandbox_code_executor import (
      AgentEngineSandboxCodeExecutor,
  )
  from google.adk.runners import Runner
  from google.adk.sessions import InMemorySessionService
  from google.genai import types

  agent = Agent(
      name="code_exec_agent",
      model=os.environ.get("CODE_EXEC_AGENT_MODEL", "gemini-3.8-flash"),
      instruction=(
          "Answer by replying with Python code in a ```python fenced block; it "
          "will be executed for you and the output shown back. Variables "
          "persist between code blocks within this conversation. Always print "
          "results."
      ),
      code_executor=AgentEngineSandboxCodeExecutor(
          agent_engine_resource_name=runtime,
          code_block_delimiters=[("```python\n", "\n```")],
      ),
  )
  svc = InMemorySessionService()
  runner = Runner(
      app_name="code_exec_agent",
      agent=agent,
      session_service=svc,
      artifact_service=InMemoryArtifactService(),
  )
  user = "prove_user"
  s_a = await svc.create_session(app_name="code_exec_agent", user_id=user)
  s_b = await svc.create_session(app_name="code_exec_agent", user_id=user)

  async def say(session_id: str, text: str) -> tuple[list[str], str | None]:
    outputs: list[str] = []
    async for ev in runner.run_async(
        user_id=user,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
    ):
      for part in (ev.content.parts if ev.content else []) or []:
        if part.code_execution_result:
          outputs.append(part.code_execution_result.output or "")
    st = (
        await svc.get_session(
            app_name="code_exec_agent", user_id=user, session_id=session_id
        )
    ).state
    return outputs, _sandbox_name_from_state(dict(st))

  a1_out, a1_sb = await say(s_a.id, "Set marker = 'alpha' and print it.")
  a2_out, a2_sb = await say(s_a.id, "Print marker again.")
  b1_out, b1_sb = await say(s_b.id, "Print marker.")
  b2_out, b2_sb = await say(s_b.id, "Set marker = 'beta' and print it.")
  a3_out, a3_sb = await say(s_a.id, "Print marker.")

  return {
      "A": {
          "session_id": s_a.id,
          "sandbox_name": a3_sb,
          "turns": [
              {"prompt": "set alpha", "outputs": a1_out, "sandbox": a1_sb},
              {"prompt": "print marker", "outputs": a2_out, "sandbox": a2_sb},
              {"prompt": "print marker again", "outputs": a3_out, "sandbox": a3_sb},
          ],
      },
      "B": {
          "session_id": s_b.id,
          "sandbox_name": b2_sb,
          "turns": [
              {"prompt": "print marker", "outputs": b1_out, "sandbox": b1_sb},
              {"prompt": "set beta", "outputs": b2_out, "sandbox": b2_sb},
          ],
      },
  }


def _assert_marker_isolation(report: dict) -> None:
  a_name = report["A"]["sandbox_name"]
  b_name = report["B"]["sandbox_name"]
  if not a_name or not b_name:
    raise AssertionError(
        f"Missing sandbox names after agent turns: A={a_name!r} B={b_name!r}. "
        "Check model/tool_code fencing and that SANDBOX_RUNTIME_NAME is real."
    )
  if a_name == b_name:
    raise AssertionError(f"Sessions shared a sandbox: {a_name}")

  a_sandboxes = {t["sandbox"] for t in report["A"]["turns"] if t["sandbox"]}
  if a_sandboxes != {a_name}:
    raise AssertionError(f"Session A sandbox changed across turns: {a_sandboxes}")

  a_last = "\n".join(report["A"]["turns"][-1]["outputs"])
  if "alpha" not in a_last:
    raise AssertionError(f"Session A did not keep marker=alpha; got {a_last!r}")

  b_first = "\n".join(report["B"]["turns"][0]["outputs"])
  if "NameError" not in b_first and "not defined" not in b_first:
    raise AssertionError(
        f"Session B should not see A's marker; expected NameError, got {b_first!r}"
    )

  b_last = "\n".join(report["B"]["turns"][-1]["outputs"])
  if "beta" not in b_last:
    raise AssertionError(f"Session B did not set marker=beta; got {b_last!r}")


def _filesystem_isolation(runtime: str, a_name: str, b_name: str) -> dict:
  """Write unique tokens in each sandbox; assert neither can see the other's."""
  from google.adk.code_executors.agent_engine_sandbox_code_executor import (
      AgentEngineSandboxCodeExecutor,
  )
  from google.adk.code_executors.code_execution_utils import CodeExecutionInput

  ex = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=runtime)
  tok_a = f"TOKA_{uuid.uuid4().hex}"
  tok_b = f"TOKB_{uuid.uuid4().hex}"

  def ctx(name: str) -> SimpleNamespace:
    return SimpleNamespace(session=SimpleNamespace(state={"sandbox_name": name}))

  def run(c: SimpleNamespace, code: str) -> str:
    result = ex.execute_code(c, CodeExecutionInput(code=code))
    return (result.stdout or "") + (result.stderr or "")

  write = """
import os
tok = %r
written = []
for d in [os.getcwd(), os.path.expanduser("~"), "/tmp", "/var/tmp", "/dev/shm"]:
  try:
    path = os.path.join(d, "iso_" + tok + ".txt")
    open(path, "w").write(tok)
    written.append(path)
  except Exception:
    pass
print("WROTE", written)
"""
  search = """
import os, subprocess
tok = %r
hits = []
for dp, dn, fn in os.walk("/"):
  if dp.startswith(("/proc", "/sys", "/dev/pts")):
    dn[:] = []
    continue
  for name in fn:
    if tok in name:
      hits.append(os.path.join(dp, name))
print("NAME_HITS", hits)
r = subprocess.run(
  ["grep", "-rl", "--exclude-dir=proc", "--exclude-dir=sys", tok,
   "/tmp", "/var/tmp", "/dev/shm", os.getcwd(), os.path.expanduser("~")],
  capture_output=True, text=True,
)
print("CONTENT_HITS", r.stdout.split())
"""

  a_ctx, b_ctx = ctx(a_name), ctx(b_name)
  run(a_ctx, write % tok_a)
  run(b_ctx, write % tok_b)
  a_sees_b = run(a_ctx, search % tok_b)
  b_sees_a = run(b_ctx, search % tok_a)
  a_sees_a = run(a_ctx, search % tok_a)

  if "NAME_HITS []" not in a_sees_b or "CONTENT_HITS []" not in a_sees_b:
    raise AssertionError(f"A can see B's files: {a_sees_b}")
  if "NAME_HITS []" not in b_sees_a or "CONTENT_HITS []" not in b_sees_a:
    raise AssertionError(f"B can see A's files: {b_sees_a}")
  if "NAME_HITS []" in a_sees_a:
    raise AssertionError(f"Control failed; A cannot see its own token: {a_sees_a}")

  return {
      "a_sees_b": "none",
      "b_sees_a": "none",
      "a_control_hits": True,
  }


def _delete_sandboxes(names: list[str]) -> None:
  import agentplatform

  project = os.environ["GOOGLE_CLOUD_PROJECT"]
  location = os.environ.get("SANDBOX_LOCATION", "us-central1")
  client = agentplatform.Client(project=project, location=location)
  for name in names:
    try:
      client.sandboxes.delete(name=name)
      print(f"deleted {name}")
    except Exception as exc:  # noqa: BLE001
      print(f"delete failed for {name}: {exc}", file=sys.stderr)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "--keep",
      action="store_true",
      help="Do not delete the sandboxes created by this run.",
  )
  parser.add_argument(
      "--json-out",
      type=Path,
      default=None,
      help="Optional path to write the evidence JSON.",
  )
  args = parser.parse_args()
  runtime = _env_ready()

  os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
  os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "TRUE")
  os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
  os.environ.setdefault("SANDBOX_LOCATION", "us-central1")

  print("Running two-session agent proof …")
  report = asyncio.run(_run_via_runner(runtime))
  _assert_marker_isolation(report)
  print(
      "marker isolation OK:\n"
      f"  A session={report['A']['session_id']} sandbox=…{report['A']['sandbox_name'].rsplit('/', 1)[-1]}\n"
      f"  B session={report['B']['session_id']} sandbox=…{report['B']['sandbox_name'].rsplit('/', 1)[-1]}"
  )

  print("Running filesystem isolation check …")
  fs = _filesystem_isolation(
      runtime, report["A"]["sandbox_name"], report["B"]["sandbox_name"]
  )
  report["filesystem"] = fs
  print("filesystem isolation OK (0 cross-sandbox hits)")

  if args.json_out:
    args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {args.json_out}")

  if not args.keep:
    _delete_sandboxes([report["A"]["sandbox_name"], report["B"]["sandbox_name"]])
  else:
    print("--keep: leaving sandboxes running")
  return 0


if __name__ == "__main__":
  # Ensure agents/ is importable if needed; keep PATH for local package.
  sys.path.insert(0, str(AGENTS))
  sys.path.insert(0, str(ROOT))
  raise SystemExit(main())
