"""Thin sandbox SDK wrapper with retries and error mapping.

All methods are synchronous. Callers in async ADK tools must hop via
``asyncio.to_thread`` (the manager does this).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Protocol

from sandbox_agent.sandbox.errors import (
    SandboxNotFound,
    SandboxQuotaExceeded,
    SandboxTimeout,
    SandboxUnavailable,
)

logger = logging.getLogger(__name__)


class SandboxClientProtocol(Protocol):
  """Minimal surface used by SessionSandboxManager and tools."""

  def create(
      self,
      *,
      runtime_name: str,
      display_name: str,
      ttl: str,
      wait_for_completion: bool = True,
      sandbox_environment_template: str | None = None,
      sandbox_environment_snapshot: str | None = None,
  ) -> dict[str, Any]: ...

  def get(self, *, name: str) -> dict[str, Any]: ...

  def list(self, *, runtime_name: str) -> list[dict[str, Any]]: ...

  def delete(self, *, name: str) -> None: ...

  def pause(self, *, name: str, wait_for_completion: bool = True) -> dict[str, Any]: ...

  def resume(self, *, name: str, wait_for_completion: bool = True) -> dict[str, Any]: ...

  def execute_bash(
      self,
      *,
      name: str,
      command: str,
      cwd: str | None = None,
      timeout: int | None = None,
  ) -> dict[str, Any]: ...

  def create_template(
      self,
      *,
      runtime_name: str,
      display_name: str,
      wait_for_completion: bool = True,
  ) -> dict[str, Any]: ...

  def list_templates(self, *, runtime_name: str) -> list[dict[str, Any]]: ...

  def get_template(self, *, name: str) -> dict[str, Any]: ...

  def create_snapshot(
      self,
      *,
      source_sandbox_name: str,
      display_name: str,
      ttl: str,
      wait_for_completion: bool = True,
  ) -> dict[str, Any]: ...

  def get_snapshot(self, *, name: str) -> dict[str, Any]: ...

  def list_snapshots(self, *, runtime_name: str) -> list[dict[str, Any]]: ...

  def delete_snapshot(self, *, name: str) -> None: ...


def _is_not_found(exc: BaseException) -> bool:
  text = str(exc).lower()
  name = type(exc).__name__.lower()
  code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
  if code in (404, "404", "NOT_FOUND"):
    return True
  return "not_found" in name or "not found" in text or "404" in text


def _is_quota(exc: BaseException) -> bool:
  text = str(exc).lower()
  name = type(exc).__name__.lower()
  return (
      "resource_exhausted" in name
      or "resource exhausted" in text
      or "quota" in text
      or "429" in text
  )


def _is_command_timeout(exc: BaseException) -> bool:
  """True when the *user's* command hit its timeout, not the transport.

  The control plane reports this as FAILED_PRECONDITION wrapping a
  DEADLINE_EXCEEDED, which is otherwise indistinguishable from a transport
  deadline. Retrying it would re-run a command that may not be idempotent.
  """
  text = str(exc).lower()
  return "command exceeded" in text and "was killed" in text


def _is_retryable(exc: BaseException) -> bool:
  text = str(exc).lower()
  name = type(exc).__name__.lower()
  if _is_not_found(exc) or _is_quota(exc) or _is_command_timeout(exc):
    return False
  return any(
      token in text or token in name
      for token in (
          "deadline",
          "unavailable",
          "internal",
          "timeout",
          "503",
          "500",
          "502",
          "504",
          # A sandbox can report STATE_RUNNING a beat before its data plane
          # accepts traffic; the control plane surfaces that as a
          # FAILED_PRECONDITION carrying one of these phrases.
          "bad gateway",
          "unable to reach the sandbox",
      )
  )


def _map_exception(exc: BaseException) -> Exception:
  if isinstance(exc, (SandboxUnavailable, SandboxTimeout, SandboxQuotaExceeded, SandboxNotFound)):
    return exc
  if _is_not_found(exc):
    return SandboxNotFound(str(exc))
  if _is_quota(exc):
    return SandboxQuotaExceeded(str(exc))
  if "timeout" in str(exc).lower() or "deadline" in str(exc).lower():
    return SandboxTimeout(str(exc))
  return SandboxUnavailable(str(exc))


def _sandbox_to_dict(env: Any) -> dict[str, Any]:
  state = getattr(env, "state", None)
  state_value = state.value if hasattr(state, "value") else str(state) if state is not None else None
  return {
      "name": getattr(env, "name", None),
      "display_name": getattr(env, "display_name", None),
      "state": state_value,
      "create_time": str(getattr(env, "create_time", "") or ""),
      "update_time": str(getattr(env, "update_time", "") or ""),
      "expire_time": str(getattr(env, "expire_time", "") or ""),
      "ttl": getattr(env, "ttl", None),
      "sandbox_environment_snapshot": getattr(env, "sandbox_environment_snapshot", None),
      "latest_sandbox_environment_snapshot": getattr(
          env, "latest_sandbox_environment_snapshot", None
      ),
      "sandbox_environment_template": getattr(env, "sandbox_environment_template", None),
  }


def _template_to_dict(tpl: Any) -> dict[str, Any]:
  return {
      "name": getattr(tpl, "name", None),
      "display_name": getattr(tpl, "display_name", None),
      "state": str(getattr(tpl, "state", "") or ""),
      "create_time": str(getattr(tpl, "create_time", "") or ""),
  }


def _snapshot_to_dict(snap: Any) -> dict[str, Any]:
  size = getattr(snap, "size_bytes", None)
  return {
      "name": getattr(snap, "name", None),
      "display_name": getattr(snap, "display_name", None),
      "create_time": str(getattr(snap, "create_time", "") or ""),
      "expire_time": str(getattr(snap, "expire_time", "") or ""),
      "ttl": getattr(snap, "ttl", None),
      "size_bytes": int(size) if size is not None else None,
      "source_sandbox_environment": getattr(snap, "source_sandbox_environment", None),
      "parent_snapshot": getattr(snap, "parent_snapshot", None),
  }


class SandboxClient:
  """Synchronous wrapper around ``agentplatform.Client().sandboxes``."""

  def __init__(
      self,
      *,
      project: str,
      location: str,
      max_retries: int = 3,
      client: Any | None = None,
  ) -> None:
    self._project = project
    self._location = location
    self._max_retries = max_retries
    self._client = client

  def _api(self) -> Any:
    if self._client is None:
      import agentplatform

      self._client = agentplatform.Client(project=self._project, location=self._location)
    return self._client

  def _retry(self, op_name: str, fn):
    last: BaseException | None = None
    for attempt in range(self._max_retries):
      try:
        return fn()
      except Exception as exc:  # noqa: BLE001 - map everything at the boundary
        last = exc
        if attempt + 1 >= self._max_retries or not _is_retryable(exc):
          raise _map_exception(exc) from exc
        sleep_s = (0.4 * (2**attempt)) + random.uniform(0, 0.2)
        logger.warning(
            "%s failed (attempt %s/%s): %s; retrying in %.2fs",
            op_name,
            attempt + 1,
            self._max_retries,
            exc,
            sleep_s,
        )
        time.sleep(sleep_s)
    assert last is not None
    raise _map_exception(last) from last

  def create(
      self,
      *,
      runtime_name: str,
      display_name: str,
      ttl: str,
      wait_for_completion: bool = True,
      sandbox_environment_template: str | None = None,
      sandbox_environment_snapshot: str | None = None,
  ) -> dict[str, Any]:
    def _call():
      config: dict[str, Any] = {
          "display_name": display_name,
          "ttl": ttl,
          "wait_for_completion": wait_for_completion,
      }
      if sandbox_environment_template:
        config["sandbox_environment_template"] = sandbox_environment_template
      if sandbox_environment_snapshot:
        config["sandbox_environment_snapshot"] = sandbox_environment_snapshot

      # Restore-from-snapshot does not need a shell spec; the snapshot carries
      # the environment. Fresh creates still use shell_environment.
      spec = None if sandbox_environment_snapshot else {"shell_environment": {}}

      operation = self._api().sandboxes.create(
          name=runtime_name,
          # Creation also provisions a sandbox template and can take ~85s; the
          # SDK's 0.1s default would poll the operation several hundred times.
          poll_interval_seconds=2.0,
          spec=spec,
          config=config,
      )
      env = getattr(operation, "response", None) or operation
      if env is None or not getattr(env, "name", None):
        raise SandboxUnavailable(f"create returned no sandbox: {operation!r}")
      return _sandbox_to_dict(env)

    try:
      return self._retry("sandboxes.create", _call)
    except SandboxQuotaExceeded:
      raise
    except Exception as exc:  # noqa: BLE001
      raise _map_exception(exc) from exc

  def get(self, *, name: str) -> dict[str, Any]:
    def _call():
      return _sandbox_to_dict(self._api().sandboxes.get(name=name))

    return self._retry("sandboxes.get", _call)

  def list(self, *, runtime_name: str) -> list[dict[str, Any]]:
    def _call():
      return [_sandbox_to_dict(s) for s in self._api().sandboxes.list(name=runtime_name)]

    return self._retry("sandboxes.list", _call)

  def delete(self, *, name: str) -> None:
    def _call():
      self._api().sandboxes.delete(name=name)

    try:
      self._retry("sandboxes.delete", _call)
    except SandboxNotFound:
      return

  def pause(self, *, name: str, wait_for_completion: bool = True) -> dict[str, Any]:
    def _call():
      operation = self._api().sandboxes.pause(
          name=name,
          poll_interval_seconds=2.0,
          config={"wait_for_completion": wait_for_completion},
      )
      env = getattr(operation, "response", None) or operation
      return _sandbox_to_dict(env)

    return self._retry("sandboxes.pause", _call)

  def resume(self, *, name: str, wait_for_completion: bool = True) -> dict[str, Any]:
    def _call():
      operation = self._api().sandboxes.resume(
          name=name,
          poll_interval_seconds=2.0,
          config={"wait_for_completion": wait_for_completion},
      )
      env = getattr(operation, "response", None) or operation
      return _sandbox_to_dict(env)

    return self._retry("sandboxes.resume", _call)

  def execute_bash(
      self,
      *,
      name: str,
      command: str,
      cwd: str | None = None,
      timeout: int | None = None,
  ) -> dict[str, Any]:
    def _call():
      result = self._api().sandboxes.execute_bash(
          name=name,
          command=command,
          cwd=cwd,
          timeout=timeout,
      )
      if not isinstance(result, dict):
        raise SandboxUnavailable(f"execute_bash returned unexpected type: {type(result)}")
      return {
          "stdout": result.get("stdout") or "",
          "stderr": result.get("stderr") or "",
          "returncode": int(result.get("returncode") or 0),
          "duration_ms": result.get("duration_ms"),
          "timed_out": False,
      }

    try:
      return self._retry("sandboxes.execute_bash", _call)
    except Exception as exc:  # noqa: BLE001
      if not _is_command_timeout(exc):
        raise
      # A command that outlives its timeout is data, not a failure, so the
      # model can decide what to do. The API returns no partial output.
      return {
          "stdout": "",
          "stderr": f"Command exceeded its {timeout}s timeout and was killed.",
          "returncode": 124,
          "duration_ms": None,
          "timed_out": True,
      }

  def create_template(
      self,
      *,
      runtime_name: str,
      display_name: str,
      wait_for_completion: bool = True,
  ) -> dict[str, Any]:
    def _call():
      import agentplatform
      from agentplatform._genai import types as ap_types

      category = ap_types.DefaultContainerCategory.DEFAULT_CONTAINER_CATEGORY_SHELL_SANDBOX
      default_env = ap_types.SandboxEnvironmentTemplateDefaultContainerEnvironment(
          default_container_category=category,
      )
      operation = self._api().sandboxes.templates.create(
          name=runtime_name,
          display_name=display_name,
          poll_interval_seconds=2.0,
          config={
              "wait_for_completion": wait_for_completion,
              "default_container_environment": default_env,
          },
      )
      tpl = getattr(operation, "response", None) or operation
      if tpl is None or not getattr(tpl, "name", None):
        # Operation may complete without embedding the resource; fetch via list.
        for candidate in self._api().sandboxes.templates.list(name=runtime_name):
          if getattr(candidate, "display_name", None) == display_name:
            return _template_to_dict(candidate)
        raise SandboxUnavailable(f"create_template returned no template: {operation!r}")
      return _template_to_dict(tpl)

    return self._retry("sandboxes.templates.create", _call)

  def list_templates(self, *, runtime_name: str) -> list[dict[str, Any]]:
    def _call():
      return [
          _template_to_dict(t)
          for t in self._api().sandboxes.templates.list(name=runtime_name)
      ]

    return self._retry("sandboxes.templates.list", _call)

  def get_template(self, *, name: str) -> dict[str, Any]:
    def _call():
      return _template_to_dict(self._api().sandboxes.templates.get(name=name))

    return self._retry("sandboxes.templates.get", _call)

  def create_snapshot(
      self,
      *,
      source_sandbox_name: str,
      display_name: str,
      ttl: str,
      wait_for_completion: bool = True,
  ) -> dict[str, Any]:
    def _call():
      operation = self._api().sandboxes.snapshots.create(
          source_sandbox_environment_name=source_sandbox_name,
          poll_interval_seconds=2.0,
          config={
              "display_name": display_name,
              "ttl": ttl,
              "wait_for_completion": wait_for_completion,
          },
      )
      snap = getattr(operation, "response", None) or operation
      if snap is None or not getattr(snap, "name", None):
        raise SandboxUnavailable(f"create_snapshot returned no snapshot: {operation!r}")
      return _snapshot_to_dict(snap)

    return self._retry("sandboxes.snapshots.create", _call)

  def get_snapshot(self, *, name: str) -> dict[str, Any]:
    def _call():
      return _snapshot_to_dict(self._api().sandboxes.snapshots.get(name=name))

    return self._retry("sandboxes.snapshots.get", _call)

  def list_snapshots(self, *, runtime_name: str) -> list[dict[str, Any]]:
    def _call():
      return [
          _snapshot_to_dict(s)
          for s in self._api().sandboxes.snapshots.list(name=runtime_name)
      ]

    return self._retry("sandboxes.snapshots.list", _call)

  def delete_snapshot(self, *, name: str) -> None:
    def _call():
      self._api().sandboxes.snapshots.delete(name=name)

    try:
      self._retry("sandboxes.snapshots.delete", _call)
    except SandboxNotFound:
      return
