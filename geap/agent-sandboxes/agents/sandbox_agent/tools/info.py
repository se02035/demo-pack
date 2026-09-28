"""Sandbox identity and teardown tools."""

from __future__ import annotations

import asyncio
from typing import Any

from sandbox_agent.config import get_settings
from sandbox_agent.sandbox.errors import SandboxError
from sandbox_agent.sandbox.manager import seconds_until_expiry
from sandbox_agent.sandbox import runtime as sandbox_runtime
from sandbox_agent.tools.output import error_payload, shape_bash_result


async def get_sandbox_info(tool_context: Any) -> dict[str, Any]:
  """Return the sandbox resource name, state, and whoami/hostname/pwd."""
  mgr = sandbox_runtime.get_manager()
  settings = get_settings()
  try:
    binding = await mgr.resolve(tool_context)
    env = await asyncio.to_thread(mgr._client.get, name=binding.name)
    who = await asyncio.to_thread(
        mgr._client.execute_bash,
        name=binding.name,
        command="whoami && hostname && pwd",
        timeout=settings.default_timeout_seconds,
    )
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)

  return shape_bash_result(
      sandbox_name=binding.name,
      result=who,
      max_chars=settings.max_output_chars,
      extra={
          "ok": True,
          "display_name": binding.display_name,
          "state": env.get("state"),
          "create_time": env.get("create_time"),
          "expire_time": env.get("expire_time"),
          "seconds_until_expiry": seconds_until_expiry(env.get("expire_time")),
          "restored_from": binding.restored_from,
          "whoami_stdout": who.get("stdout") or "",
      },
  )


async def end_sandbox_session(tool_context: Any) -> dict[str, Any]:
  """Delete this session's sandbox and clear the durable binding."""
  mgr = sandbox_runtime.get_manager()
  try:
    result = await mgr.end_session(tool_context)
    result["ok"] = True
    return result
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)
