"""Lifecycle tools: pause/resume, snapshots, restore, TTL visibility."""

from __future__ import annotations

import asyncio
from typing import Any

from sandbox_agent.config import get_settings
from sandbox_agent.sandbox.errors import SandboxError
from sandbox_agent.sandbox.manager import seconds_until_expiry
from sandbox_agent.sandbox import runtime as sandbox_runtime
from sandbox_agent.tools.output import error_payload


async def get_sandbox_lifecycle(tool_context: Any) -> dict[str, Any]:
  """Report sandbox state, TTL/expiry, restored_from, and this session's snapshots.

  Read-only: does not create a sandbox if none is bound.
  """
  mgr = sandbox_runtime.get_manager()
  binding = mgr.read_binding(tool_context.state)
  snaps = await mgr.list_session_snapshots(tool_context)
  if binding is None:
    return {
        "ok": True,
        "bound": False,
        "sandbox_name": None,
        "snapshots": snaps.get("snapshots") or [],
        "detail": "No sandbox is bound to this session yet. Call a tool that needs one.",
    }
  try:
    env = await asyncio.to_thread(mgr.client.get, name=binding.name)
  except SandboxError as exc:
    return error_payload(sandbox_name=binding.name, error=str(exc), code=type(exc).__name__)

  expire = env.get("expire_time")
  return {
      "ok": True,
      "bound": True,
      "sandbox_name": binding.name,
      "display_name": binding.display_name,
      "state": env.get("state"),
      "create_time": env.get("create_time"),
      "expire_time": expire,
      "seconds_until_expiry": seconds_until_expiry(expire),
      "ttl_configured_seconds": get_settings().ttl_seconds,
      "restored_from": binding.restored_from,
      "snapshots": snaps.get("snapshots") or [],
      "detail": (
          "TTL is set at create time and cannot be extended via an API update. "
          "Take a snapshot to keep files past expiry."
      ),
  }


async def pause_sandbox(tool_context: Any) -> dict[str, Any]:
  """Pause this session's sandbox (releases compute; disk is preserved)."""
  mgr = sandbox_runtime.get_manager()
  try:
    # Ensure a sandbox exists first so "pause" after "hi" still works.
    await mgr.resolve(tool_context)
    return await mgr.pause_session(tool_context)
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)


async def resume_sandbox(tool_context: Any) -> dict[str, Any]:
  """Resume this session's paused sandbox."""
  mgr = sandbox_runtime.get_manager()
  try:
    return await mgr.resume_session(tool_context)
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)


async def snapshot_sandbox(label: str, tool_context: Any) -> dict[str, Any]:
  """Checkpoint this session's sandbox disk under ``label``."""
  mgr = sandbox_runtime.get_manager()
  label = (label or "").strip()
  if not label:
    return error_payload(
        sandbox_name=None, error="label is required", code="SandboxConfigError"
    )
  try:
    await mgr.resolve(tool_context)
    return await mgr.snapshot_session(tool_context, label=label, auto=False)
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)


async def list_snapshots(tool_context: Any) -> dict[str, Any]:
  """List snapshots belonging to this session (confirmed live via get)."""
  mgr = sandbox_runtime.get_manager()
  try:
    return await mgr.list_session_snapshots(tool_context)
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)


async def restore_snapshot(label_or_name: str, tool_context: Any) -> dict[str, Any]:
  """Restore a session snapshot: delete the live sandbox, then create from the snapshot.

  Only snapshots recorded in this session's state are accepted.
  """
  mgr = sandbox_runtime.get_manager()
  label_or_name = (label_or_name or "").strip()
  if not label_or_name:
    return error_payload(
        sandbox_name=None,
        error="label_or_name is required",
        code="SandboxConfigError",
    )
  try:
    return await mgr.restore_session(tool_context, label_or_name=label_or_name)
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)


async def delete_snapshot(label_or_name: str, tool_context: Any) -> dict[str, Any]:
  """Delete a snapshot that belongs to this session."""
  mgr = sandbox_runtime.get_manager()
  label_or_name = (label_or_name or "").strip()
  if not label_or_name:
    return error_payload(
        sandbox_name=None,
        error="label_or_name is required",
        code="SandboxConfigError",
    )
  try:
    return await mgr.delete_session_snapshot(tool_context, label_or_name=label_or_name)
  except SandboxError as exc:
    return error_payload(sandbox_name=None, error=str(exc), code=type(exc).__name__)
