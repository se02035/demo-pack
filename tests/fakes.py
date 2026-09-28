"""In-memory fake sandbox client for unit tests."""

from __future__ import annotations

import itertools
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


class FakeSandboxClient:
  def __init__(self) -> None:
    self._lock = threading.Lock()
    self._seq = itertools.count(1)
    self.sandboxes: dict[str, dict[str, Any]] = {}
    self.templates: dict[str, dict[str, Any]] = {}
    self.snapshots: dict[str, dict[str, Any]] = {}
    self.create_calls = 0
    self.get_calls = 0
    self.delete_calls = 0
    self.pause_calls = 0
    self.resume_calls = 0
    self.template_create_calls = 0
    self.snapshot_create_calls = 0
    self.execute_calls: list[dict[str, Any]] = []
    self.call_order: list[tuple[str, str]] = []
    self.create_latency_s = 0.0
    self.fail_create_with: Exception | None = None
    self.fail_get_names: set[str] = set()
    self.fail_snapshot_names: set[str] = set()
    self.create_hook: Callable[[], None] | None = None
    self.default_ttl_seconds = 3600
    # Sandboxes that come up RUNNING but whose data plane never answers, the
    # way restore-from-snapshot behaves on the live platform.
    self.unreachable_names: set[str] = set()
    self.unreachable_from_snapshot = False
    # Extra states `get` yields before the sandbox's real state, so tests can
    # drive transitions such as STATE_RESUMING.
    self.pending_states: dict[str, list[str]] = {}

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
    if self.create_hook:
      self.create_hook()
    if self.fail_create_with is not None:
      raise self.fail_create_with
    if self.create_latency_s:
      time.sleep(self.create_latency_s)
    with self._lock:
      if sandbox_environment_snapshot:
        if sandbox_environment_snapshot not in self.snapshots:
          from sandbox_agent.sandbox.errors import SandboxNotFound

          raise SandboxNotFound(sandbox_environment_snapshot)
        source_files = dict(self.snapshots[sandbox_environment_snapshot].get("files") or {})
      else:
        source_files = {}
      self.create_calls += 1
      sandbox_id = next(self._seq)
      name = f"{runtime_name}/sandboxEnvironments/{sandbox_id}"
      ttl_seconds = int(str(ttl).rstrip("s") or self.default_ttl_seconds)
      expire = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
      env = {
          "name": name,
          "display_name": display_name,
          "state": "STATE_RUNNING",
          "create_time": datetime.now(timezone.utc).isoformat(),
          "update_time": datetime.now(timezone.utc).isoformat(),
          "expire_time": expire.isoformat(),
          "ttl": ttl,
          "files": source_files,
          "sandbox_environment_template": sandbox_environment_template,
          "sandbox_environment_snapshot": sandbox_environment_snapshot,
          "latest_sandbox_environment_snapshot": None,
      }
      self.sandboxes[name] = env
      if sandbox_environment_snapshot and self.unreachable_from_snapshot:
        self.unreachable_names.add(name)
      self.call_order.append(("create", name))
      return dict(env)

  def get(self, *, name: str) -> dict[str, Any]:
    from sandbox_agent.sandbox.errors import SandboxNotFound

    with self._lock:
      self.get_calls += 1
      if name in self.fail_get_names or name not in self.sandboxes:
        raise SandboxNotFound(name)
      env = dict(self.sandboxes[name])
      queued = self.pending_states.get(name)
      if queued:
        env["state"] = queued.pop(0)
      return env

  def list(self, *, runtime_name: str) -> list[dict[str, Any]]:
    with self._lock:
      return [
          dict(env)
          for name, env in self.sandboxes.items()
          if name.startswith(runtime_name + "/")
      ]

  def delete(self, *, name: str) -> None:
    with self._lock:
      self.delete_calls += 1
      self.sandboxes.pop(name, None)
      self.call_order.append(("delete", name))

  def pause(self, *, name: str, wait_for_completion: bool = True) -> dict[str, Any]:
    with self._lock:
      self.pause_calls += 1
      env = self.sandboxes[name]
      env["state"] = "STATE_PAUSED"
      self.call_order.append(("pause", name))
      return dict(env)

  def resume(self, *, name: str, wait_for_completion: bool = True) -> dict[str, Any]:
    with self._lock:
      self.resume_calls += 1
      env = self.sandboxes[name]
      env["state"] = "STATE_RUNNING"
      self.call_order.append(("resume", name))
      return dict(env)

  def create_template(
      self,
      *,
      runtime_name: str,
      display_name: str,
      wait_for_completion: bool = True,
  ) -> dict[str, Any]:
    with self._lock:
      self.template_create_calls += 1
      tid = next(self._seq)
      name = f"{runtime_name}/sandboxEnvironmentTemplates/{tid}"
      tpl = {
          "name": name,
          "display_name": display_name,
          "state": "ACTIVE",
          "create_time": datetime.now(timezone.utc).isoformat(),
      }
      self.templates[name] = tpl
      self.call_order.append(("create_template", name))
      return dict(tpl)

  def list_templates(self, *, runtime_name: str) -> list[dict[str, Any]]:
    with self._lock:
      return [
          dict(t)
          for name, t in self.templates.items()
          if name.startswith(runtime_name + "/")
      ]

  def get_template(self, *, name: str) -> dict[str, Any]:
    from sandbox_agent.sandbox.errors import SandboxNotFound

    with self._lock:
      if name not in self.templates:
        raise SandboxNotFound(name)
      return dict(self.templates[name])

  def create_snapshot(
      self,
      *,
      source_sandbox_name: str,
      display_name: str,
      ttl: str,
      wait_for_completion: bool = True,
  ) -> dict[str, Any]:
    from sandbox_agent.sandbox.errors import SandboxNotFound

    with self._lock:
      if source_sandbox_name not in self.sandboxes:
        raise SandboxNotFound(source_sandbox_name)
      self.snapshot_create_calls += 1
      sid = next(self._seq)
      # Derive runtime prefix from source name.
      runtime = source_sandbox_name.rsplit("/sandboxEnvironments/", 1)[0]
      name = f"{runtime}/sandboxEnvironmentSnapshots/{sid}"
      ttl_seconds = int(str(ttl).rstrip("s") or 86400)
      expire = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
      files = dict(self.sandboxes[source_sandbox_name].get("files") or {})
      snap = {
          "name": name,
          "display_name": display_name,
          "create_time": datetime.now(timezone.utc).isoformat(),
          "expire_time": expire.isoformat(),
          "ttl": ttl,
          "size_bytes": sum(len(v.encode()) for v in files.values()),
          "source_sandbox_environment": source_sandbox_name,
          "parent_snapshot": None,
          "files": files,
      }
      self.snapshots[name] = snap
      self.sandboxes[source_sandbox_name]["latest_sandbox_environment_snapshot"] = name
      self.call_order.append(("create_snapshot", name))
      return dict(snap)

  def get_snapshot(self, *, name: str) -> dict[str, Any]:
    from sandbox_agent.sandbox.errors import SandboxNotFound

    with self._lock:
      if name in self.fail_snapshot_names or name not in self.snapshots:
        raise SandboxNotFound(name)
      return dict(self.snapshots[name])

  def list_snapshots(self, *, runtime_name: str) -> list[dict[str, Any]]:
    with self._lock:
      return [
          dict(s)
          for name, s in self.snapshots.items()
          if name.startswith(runtime_name + "/")
      ]

  def delete_snapshot(self, *, name: str) -> None:
    with self._lock:
      self.snapshots.pop(name, None)
      self.call_order.append(("delete_snapshot", name))

  def execute_bash(
      self,
      *,
      name: str,
      command: str,
      cwd: str | None = None,
      timeout: int | None = None,
  ) -> dict[str, Any]:
    from sandbox_agent.sandbox.errors import SandboxNotFound, SandboxUnavailable

    with self._lock:
      if name not in self.sandboxes:
        raise SandboxNotFound(name)
      env = self.sandboxes[name]
      if env.get("state") == "STATE_PAUSED":
        raise SandboxUnavailable("sandbox is paused")
      if name in self.unreachable_names:
        raise SandboxUnavailable(
            "Execution Failed. Error: DEADLINE_EXCEEDED on URL .../exec"
        )
      self.execute_calls.append(
          {"name": name, "command": command, "cwd": cwd, "timeout": timeout}
      )
      self.call_order.append(("execute_bash", name))
      files: dict[str, str] = env.setdefault("files", {})

      if command == "true":
        return {"stdout": "", "stderr": "", "returncode": 0, "duration_ms": 1, "timed_out": False}

      # Minimal command simulation for unit tests.
      if "base64 -d >" in command and "printf %s" in command:
        import base64
        import re
        import shlex

        m = re.search(r"printf %s (.+) \| base64 -d > (.+)$", command)
        if m:
          encoded = shlex.split(m.group(1))[0]
          path = shlex.split(m.group(2))[0]
          content = base64.b64decode(encoded.encode("ascii")).decode("utf-8")
          files[path] = content
          return {"stdout": "", "stderr": "", "returncode": 0, "duration_ms": 1, "timed_out": False}

      if "cat --" in command:
        import shlex

        parts = command.rsplit("cat --", 1)[-1]
        path = shlex.split(parts.strip())[0]
        if path not in files:
          return {
              "stdout": "",
              "stderr": "NOT_A_FILE\n",
              "returncode": 2,
              "duration_ms": 1,
              "timed_out": False,
          }
        return {
            "stdout": files[path],
            "stderr": "",
            "returncode": 0,
            "duration_ms": 1,
            "timed_out": False,
        }

      if command.startswith("ls -la --"):
        import shlex

        path = shlex.split(command[len("ls -la --") :].strip())[0]
        lines = ["total 0"]
        prefix = path.rstrip("/") + "/"
        for fpath in sorted(files):
          if fpath.startswith(prefix) or fpath == path:
            lines.append(
                f"-rw-r--r-- 1 appuser appuser 0 Jan 1 00:00 {fpath.split('/')[-1]}"
            )
        return {
            "stdout": "\n".join(lines) + "\n",
            "stderr": "",
            "returncode": 0,
            "duration_ms": 1,
            "timed_out": False,
        }

      if command == "whoami && hostname && pwd":
        return {
            "stdout": "appuser\nsandbox-host\n/workspace\n",
            "stderr": "",
            "returncode": 0,
            "duration_ms": 1,
            "timed_out": False,
        }

      if command.startswith("exit "):
        code = int(command.split()[1])
        return {
            "stdout": "",
            "stderr": "forced\n",
            "returncode": code,
            "duration_ms": 1,
            "timed_out": False,
        }

      return {
          "stdout": f"ran:{command}\n",
          "stderr": "",
          "returncode": 0,
          "duration_ms": 1,
          "timed_out": False,
      }
