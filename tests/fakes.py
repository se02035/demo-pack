"""In-memory fake sandbox client for unit tests."""

from __future__ import annotations

import itertools
import threading
import time
from typing import Any, Callable


class FakeSandboxClient:
  def __init__(self) -> None:
    self._lock = threading.Lock()
    self._seq = itertools.count(1)
    self.sandboxes: dict[str, dict[str, Any]] = {}
    self.create_calls = 0
    self.get_calls = 0
    self.delete_calls = 0
    self.pause_calls = 0
    self.resume_calls = 0
    self.execute_calls: list[dict[str, Any]] = []
    self.create_latency_s = 0.0
    self.fail_create_with: Exception | None = None
    self.fail_get_names: set[str] = set()
    self.create_hook: Callable[[], None] | None = None

  def create(
      self,
      *,
      runtime_name: str,
      display_name: str,
      ttl: str,
      wait_for_completion: bool = True,
  ) -> dict[str, Any]:
    if self.create_hook:
      self.create_hook()
    if self.fail_create_with is not None:
      raise self.fail_create_with
    if self.create_latency_s:
      time.sleep(self.create_latency_s)
    with self._lock:
      self.create_calls += 1
      sandbox_id = next(self._seq)
      name = f"{runtime_name}/sandboxEnvironments/{sandbox_id}"
      env = {
          "name": name,
          "display_name": display_name,
          "state": "STATE_RUNNING",
          "create_time": "2026-01-01T00:00:00+00:00",
          "update_time": "2026-01-01T00:00:00+00:00",
          "expire_time": "",
          "ttl": ttl,
          "files": {},
      }
      self.sandboxes[name] = env
      return dict(env)

  def get(self, *, name: str) -> dict[str, Any]:
    from sandbox_agent.sandbox.errors import SandboxNotFound

    with self._lock:
      self.get_calls += 1
      if name in self.fail_get_names or name not in self.sandboxes:
        raise SandboxNotFound(name)
      return dict(self.sandboxes[name])

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

  def pause(self, *, name: str, wait_for_completion: bool = True) -> dict[str, Any]:
    with self._lock:
      self.pause_calls += 1
      env = self.sandboxes[name]
      env["state"] = "STATE_PAUSED"
      return dict(env)

  def resume(self, *, name: str, wait_for_completion: bool = True) -> dict[str, Any]:
    with self._lock:
      self.resume_calls += 1
      env = self.sandboxes[name]
      env["state"] = "STATE_RUNNING"
      return dict(env)

  def execute_bash(
      self,
      *,
      name: str,
      command: str,
      cwd: str | None = None,
      timeout: int | None = None,
  ) -> dict[str, Any]:
    from sandbox_agent.sandbox.errors import SandboxNotFound

    with self._lock:
      if name not in self.sandboxes:
        raise SandboxNotFound(name)
      env = self.sandboxes[name]
      self.execute_calls.append(
          {"name": name, "command": command, "cwd": cwd, "timeout": timeout}
      )
      files: dict[str, str] = env.setdefault("files", {})

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
          return {"stdout": "", "stderr": "", "returncode": 0, "duration_ms": 1}

      if "cat --" in command:
        import shlex

        # command ends with: cat -- <path>
        parts = command.rsplit("cat --", 1)[-1]
        path = shlex.split(parts.strip())[0]
        if path not in files:
          return {
              "stdout": "",
              "stderr": "NOT_A_FILE\n",
              "returncode": 2,
              "duration_ms": 1,
          }
        return {
            "stdout": files[path],
            "stderr": "",
            "returncode": 0,
            "duration_ms": 1,
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
        }

      if command == "whoami && hostname && pwd":
        return {
            "stdout": "appuser\nsandbox-host\n/workspace\n",
            "stderr": "",
            "returncode": 0,
            "duration_ms": 1,
        }

      if command.startswith("exit "):
        code = int(command.split()[1])
        return {"stdout": "", "stderr": "forced\n", "returncode": code, "duration_ms": 1}

      return {
          "stdout": f"ran:{command}\n",
          "stderr": "",
          "returncode": 0,
          "duration_ms": 1,
      }
