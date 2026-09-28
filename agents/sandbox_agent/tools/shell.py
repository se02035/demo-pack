"""Shell command tools."""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from sandbox_agent.config import get_settings
from sandbox_agent.sandbox.errors import SandboxError
from sandbox_agent.sandbox import runtime as sandbox_runtime
from sandbox_agent.tools.output import error_payload, shape_bash_result


async def run_shell_command(
    command: str,
    tool_context: Any,
    cwd: str | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
  """Run a bash command in this session's sandbox and return stdout/stderr/returncode."""
  mgr = sandbox_runtime.get_manager()
  settings = get_settings()
  timeout = timeout_seconds or settings.default_timeout_seconds
  try:
    binding = await mgr.resolve(tool_context)
    result = await asyncio.to_thread(
        mgr._client.execute_bash,
        name=binding.name,
        command=command,
        cwd=cwd,
        timeout=timeout,
    )
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)

  return shape_bash_result(
      sandbox_name=binding.name,
      result=result,
      max_chars=settings.max_output_chars,
      extra={"ok": True, "command": command, "cwd": cwd},
  )


async def list_directory(
    tool_context: Any,
    path: str = "/workspace",
) -> dict[str, Any]:
  """List a directory inside the sandbox with ``ls -la``."""
  mgr = sandbox_runtime.get_manager()
  settings = get_settings()
  quoted = shlex.quote(path)
  command = f"ls -la -- {quoted}"
  try:
    binding = await mgr.resolve(tool_context)
    result = await asyncio.to_thread(
        mgr._client.execute_bash,
        name=binding.name,
        command=command,
        timeout=settings.default_timeout_seconds,
    )
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)

  entries = [
      line
      for line in (result.get("stdout") or "").splitlines()
      if line and not line.startswith("total ")
  ]
  return shape_bash_result(
      sandbox_name=binding.name,
      result=result,
      max_chars=settings.max_output_chars,
      extra={"ok": True, "path": path, "entries": entries, "command": command},
  )
