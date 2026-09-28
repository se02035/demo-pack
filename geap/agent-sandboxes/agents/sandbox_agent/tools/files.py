"""File read/write tools that shell out via execute_bash."""

from __future__ import annotations

import asyncio
import base64
import shlex
from pathlib import Path
from typing import Any

from sandbox_agent.config import get_settings
from sandbox_agent.sandbox.errors import SandboxError
from sandbox_agent.sandbox import runtime as sandbox_runtime
from sandbox_agent.tools.output import error_payload, shape_bash_result, truncate_text


def build_write_command(path: str, content: str) -> str:
  """Build a bash command that writes ``content`` to ``path`` via base64."""
  encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
  quoted_path = shlex.quote(path)
  parent = shlex.quote(str(Path(path).parent))
  return (
      f"mkdir -p -- {parent} && "
      f"printf %s {shlex.quote(encoded)} | base64 -d > {quoted_path}"
  )


def build_read_command(path: str) -> str:
  quoted = shlex.quote(path)
  return (
      f"if [ ! -f {quoted} ]; then "
      f"echo 'NOT_A_FILE' >&2; exit 2; "
      f"fi; "
      f"cat -- {quoted}"
  )


async def write_text_file(
    path: str,
    content: str,
    tool_context: Any,
) -> dict[str, Any]:
  """Create or overwrite a text file in the sandbox."""
  mgr = sandbox_runtime.get_manager()
  settings = get_settings()
  command = build_write_command(path, content)
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

  return shape_bash_result(
      sandbox_name=binding.name,
      result=result,
      max_chars=settings.max_output_chars,
      extra={
          "ok": result.get("returncode", 1) == 0,
          "path": path,
          "bytes_written": len(content.encode("utf-8")),
      },
  )


async def read_text_file(
    path: str,
    tool_context: Any,
    max_chars: int | None = None,
) -> dict[str, Any]:
  """Read a text file from the sandbox."""
  mgr = sandbox_runtime.get_manager()
  settings = get_settings()
  limit = max_chars if max_chars is not None else settings.max_output_chars
  command = build_read_command(path)
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

  content, truncated = truncate_text(result.get("stdout") or "", limit)
  return {
      "ok": result.get("returncode", 1) == 0,
      "sandbox_name": binding.name,
      "path": path,
      "content": content,
      "truncated": truncated,
      "stdout": content,
      "stderr": result.get("stderr") or "",
      "returncode": int(result.get("returncode") or 0),
      "duration_ms": result.get("duration_ms"),
  }
