"""Session-scoped Agent Platform sandboxes behind ADK BaseEnvironment.

Stock EnvironmentToolset keeps one BaseEnvironment for the process and never
passes the ADK session into execute/read/write. This module binds the current
ToolContext on a ContextVar (set by a plugin before each tool call) so each
session lazily owns its own shell and code sandboxes.

Bindings are written to ``tool_context.state`` (ADK's delta-aware State), not
raw ``session.state``, so they ride the tool event's ``state_delta`` and survive
across turns in the Playground session store.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shlex
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal

from google.adk.environment import BaseEnvironment, ExecutionResult
from google.adk.plugins import BasePlugin

logger = logging.getLogger(__name__)

Flavour = Literal["shell", "code"]

_WORKING_DIR = Path("/workspace")
_TOOL_CONTEXT: ContextVar[Any | None] = ContextVar(
    "env_sandbox_tool_context", default=None
)
_locks: dict[tuple[str, Flavour], asyncio.Lock] = {}
_client: Any | None = None

STATE_KEY = {
    "shell": "sandbox_shell",
    "code": "sandbox_code",
}


def set_current_tool_context(tool_context: Any) -> None:
  _TOOL_CONTEXT.set(tool_context)


def get_current_tool_context() -> Any:
  tool_context = _TOOL_CONTEXT.get()
  if tool_context is None:
    raise RuntimeError(
        "No ADK tool context bound. SessionBindPlugin must run before "
        "environment tools."
    )
  return tool_context


def _lock_for(session_id: str, flavour: Flavour) -> asyncio.Lock:
  key = (session_id, flavour)
  if key not in _locks:
    _locks[key] = asyncio.Lock()
  return _locks[key]


def _client_api():
  global _client
  if _client is None:
    import agentplatform

    _client = agentplatform.Client(
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("SANDBOX_LOCATION", "us-central1"),
    )
  return _client


def _runtime_name() -> str:
  name = os.environ.get("SANDBOX_RUNTIME_NAME", "").strip()
  if not name or name.endswith("/RUNTIME_ID"):
    raise RuntimeError(
        "SANDBOX_RUNTIME_NAME is missing or still a placeholder. "
        "Copy .env.example to .env and paste a real reasoningEngines/... name."
    )
  return name


def _ttl() -> str:
  return f"{os.environ.get('SANDBOX_TTL_SECONDS', '3600')}s"


def _display_name(session_id: str, flavour: Flavour) -> str:
  safe = session_id.replace("/", "-")[:48]
  return f"sandbox-{safe}-{flavour}"


def _is_not_found(exc: BaseException) -> bool:
  text = str(exc).lower()
  return "not_found" in text or "404" in text or "not found" in text


def _create_sandbox(flavour: Flavour, display_name: str) -> str:
  api = _client_api()
  spec = (
      {"shell_environment": {}}
      if flavour == "shell"
      else {"code_execution_environment": {}}
  )
  operation = api.sandboxes.create(
      name=_runtime_name(),
      poll_interval_seconds=2.0,
      spec=spec,
      config={
          "display_name": display_name,
          "ttl": _ttl(),
          "wait_for_completion": True,
      },
  )
  env = getattr(operation, "response", None) or operation
  name = getattr(env, "name", None)
  if not name:
    raise RuntimeError(f"sandbox create returned no name: {operation!r}")
  return str(name)


def _get_sandbox(name: str) -> Any:
  return _client_api().sandboxes.get(name=name)


def _delete_sandbox(name: str) -> None:
  try:
    _client_api().sandboxes.delete(name=name)
  except Exception as exc:  # noqa: BLE001
    if not _is_not_found(exc):
      logger.warning("Failed to delete sandbox %s: %s", name, exc)


def _execute_bash(name: str, command: str, *, timeout: float | None) -> dict[str, Any]:
  budget = int(timeout) if timeout is not None else 45
  result = _client_api().sandboxes.execute_bash(
      name=name,
      command=command,
      cwd=str(_WORKING_DIR),
      timeout=budget,
      config={"http_options": {"timeout": (budget + 25) * 1000}},
  )
  if not isinstance(result, dict):
    raise RuntimeError(f"execute_bash returned unexpected type: {type(result)}")
  return {
      "stdout": result.get("stdout") or "",
      "stderr": result.get("stderr") or "",
      "returncode": int(result.get("returncode") or 0),
      "timed_out": False,
  }


def _parse_execute_code(response: Any) -> ExecutionResult:
  stdout = ""
  stderr = ""
  outputs = getattr(response, "outputs", None) or []
  for chunk in outputs:
    mime = getattr(chunk, "mime_type", "") or ""
    data = getattr(chunk, "data", b"") or b""
    if isinstance(data, str):
      raw = data.encode("utf-8")
    else:
      raw = bytes(data)
    if mime == "application/json":
      try:
        payload = json.loads(raw.decode("utf-8"))
      except (json.JSONDecodeError, UnicodeDecodeError):
        continue
      stdout += str(payload.get("msg_out") or "")
      stderr += str(payload.get("msg_err") or "")
    elif mime.startswith("text/"):
      stdout += raw.decode("utf-8", errors="replace")
  exit_code = 1 if stderr and not stdout else 0
  if stderr and "Error" in stderr:
    exit_code = 1
  return ExecutionResult(exit_code=exit_code, stdout=stdout, stderr=stderr)


def _execute_code(name: str, code: str) -> ExecutionResult:
  response = _client_api().sandboxes.execute_code(
      name=name,
      input_data={"code": code},
  )
  return _parse_execute_code(response)


def _probe_ready(name: str, flavour: Flavour) -> None:
  import time

  deadline = float(os.environ.get("SANDBOX_PROVISION_DEADLINE_SECONDS", "180"))
  t0 = time.monotonic()
  last_err: Exception | None = None
  while time.monotonic() - t0 < deadline:
    try:
      if flavour == "shell":
        result = _execute_bash(name, "true", timeout=30)
        if result["returncode"] == 0:
          return
        last_err = RuntimeError(result.get("stderr") or "probe failed")
      else:
        result = _execute_code(name, "print(1)")
        if result.exit_code == 0:
          return
        last_err = RuntimeError(result.stderr or "probe failed")
    except Exception as exc:  # noqa: BLE001
      last_err = exc
    time.sleep(2.0)
  raise RuntimeError(f"Sandbox not ready within {deadline}s: {last_err}")


async def resolve_sandbox(flavour: Flavour) -> str:
  """Return the platform resource name for the current session + flavour."""
  tool_context = get_current_tool_context()
  session = tool_context.session
  # Must use tool_context.state so ADK records state_delta on the tool event.
  state = tool_context.state
  key = STATE_KEY[flavour]
  async with _lock_for(session.id, flavour):
    binding = state.get(key) if hasattr(state, "get") else None
    if binding is None and key in state:
      binding = state[key]
    if isinstance(binding, dict) and binding.get("name"):
      name = str(binding["name"])
      try:
        await asyncio.to_thread(_get_sandbox, name)
        return name
      except Exception as exc:  # noqa: BLE001
        if not _is_not_found(exc):
          raise
        logger.info("Stale %s binding for session %s; recreating", flavour, session.id)

    display = _display_name(session.id, flavour)

    def _provision() -> str:
      name = _create_sandbox(flavour, display)
      _probe_ready(name, flavour)
      return name

    name = await asyncio.to_thread(_provision)
    state[key] = {"name": name, "display_name": display}
    return name


class SessionBindPlugin(BasePlugin):
  """Publishes the ADK ToolContext to a ContextVar for environment tools."""

  def __init__(self) -> None:
    super().__init__(name="session_bind")

  async def before_tool_callback(
      self,
      *,
      tool: Any,
      tool_args: dict[str, Any],
      tool_context: Any,
  ) -> None:
    set_current_tool_context(tool_context)
    return None


class SessionSandboxEnvironment(BaseEnvironment):
  """Custom BaseEnvironment backed by one Agent Platform sandbox per session.

  Pass flavour=\"shell\" for execute_bash sandboxes, or flavour=\"code\" for
  execute_code sandboxes. Display names look like sandbox-{session}-shell.
  """

  def __init__(self, flavour: Flavour) -> None:
    if flavour not in ("shell", "code"):
      raise ValueError(f"Unsupported flavour: {flavour!r}")
    self._flavour: Flavour = flavour

  @property
  def working_dir(self) -> Path:
    return _WORKING_DIR

  async def initialize(self) -> None:
    # Deliberately empty: EnvironmentToolset initializes once per process.
    # Sandboxes are created lazily on the first session-scoped operation.
    self.is_initialized = True

  async def close(self) -> None:
    self.is_initialized = False

  def _resolve_path(self, path: Path | str) -> Path:
    p = Path(path)
    if not p.is_absolute():
      p = self.working_dir / p
    return p

  async def execute(
      self,
      command: str,
      *,
      timeout: float | None = None,
  ) -> ExecutionResult:
    name = await resolve_sandbox(self._flavour)
    if self._flavour == "shell":

      def _run() -> ExecutionResult:
        result = _execute_bash(name, command, timeout=timeout)
        return ExecutionResult(
            exit_code=int(result["returncode"]),
            stdout=str(result["stdout"]),
            stderr=str(result["stderr"]),
            timed_out=bool(result.get("timed_out")),
        )

      return await asyncio.to_thread(_run)

    # Code sandbox: the EnvironmentToolset "command" is treated as Python source.
    return await asyncio.to_thread(_execute_code, name, command)

  async def read_file(self, path: Path) -> bytes:
    name = await resolve_sandbox(self._flavour)
    target = self._resolve_path(path)
    if self._flavour == "shell":
      quoted = shlex.quote(str(target))
      command = (
          f"if [ ! -f {quoted} ]; then echo 'NOT_A_FILE' >&2; exit 2; fi; "
          f"base64 -w0 -- {quoted}"
      )

      def _run() -> bytes:
        result = _execute_bash(name, command, timeout=60)
        if result["returncode"] != 0:
          raise FileNotFoundError(str(target))
        return base64.b64decode(result["stdout"].strip())

      return await asyncio.to_thread(_run)

    code = (
        "import base64, pathlib, sys\n"
        f"p = pathlib.Path({str(target)!r})\n"
        "if not p.is_file():\n"
        "  sys.stderr.write('NOT_A_FILE')\n"
        "  raise SystemExit(2)\n"
        "print(base64.b64encode(p.read_bytes()).decode('ascii'))\n"
    )

    def _run_code() -> bytes:
      result = _execute_code(name, code)
      if result.exit_code != 0 or "NOT_A_FILE" in result.stderr:
        raise FileNotFoundError(str(target))
      return base64.b64decode(result.stdout.strip())

    return await asyncio.to_thread(_run_code)

  async def write_file(self, path: Path, content: str | bytes) -> None:
    name = await resolve_sandbox(self._flavour)
    target = self._resolve_path(path)
    raw = content.encode("utf-8") if isinstance(content, str) else content
    encoded = base64.b64encode(raw).decode("ascii")
    if self._flavour == "shell":
      quoted_path = shlex.quote(str(target))
      parent = shlex.quote(str(target.parent))
      command = (
          f"mkdir -p -- {parent} && "
          f"printf %s {shlex.quote(encoded)} | base64 -d > {quoted_path}"
      )

      def _run() -> None:
        result = _execute_bash(name, command, timeout=60)
        if result["returncode"] != 0:
          raise RuntimeError(result["stderr"] or f"write failed: {target}")

      await asyncio.to_thread(_run)
      return

    code = (
        "import base64, pathlib\n"
        f"p = pathlib.Path({str(target)!r})\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        f"p.write_bytes(base64.b64decode({encoded!r}))\n"
    )
    result = await asyncio.to_thread(_execute_code, name, code)
    if result.exit_code != 0:
      raise RuntimeError(result.stderr or f"write failed: {target}")
