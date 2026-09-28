"""Retry classification for failures seen against the live API."""

from __future__ import annotations

import pytest

from sandbox_agent.sandbox.client import SandboxClient, _is_retryable
from sandbox_agent.sandbox.errors import SandboxUnavailable

# Verbatim messages observed from the control plane in us-central1.
NOT_READY = (
    "400 FAILED_PRECONDITION. {'error': {'code': 400, 'message': 'Execution "
    "Failed. Error: INTERNAL on URL `https://x.us-central1.sandbox.vertexai."
    "goog/exec`. Error Details: Bad Gateway: Unable to reach the sandbox "
    "environment. (Request ID: abc)', 'status': 'FAILED_PRECONDITION'}}"
)
COMMAND_TIMEOUT = (
    "400 FAILED_PRECONDITION. {'error': {'code': 400, 'message': 'Execution "
    "Failed. Error: DEADLINE_EXCEEDED on URL `https://x.us-central1.sandbox."
    "vertexai.goog/exec`. Error Details: {\"detail\":\"command exceeded 2s and "
    "was killed\"}', 'status': 'FAILED_PRECONDITION'}}"
)


class _FakeSandboxes:
  def __init__(self, error: Exception | None = None):
    self._error = error
    self.calls = 0

  def execute_bash(self, **kwargs):
    self.calls += 1
    if self._error is not None:
      raise self._error
    return {"stdout": "hi", "stderr": "", "returncode": 0, "duration_ms": 3}


class _FakeApi:
  def __init__(self, sandboxes):
    self.sandboxes = sandboxes


def _client(sandboxes):
  return SandboxClient(project="p", location="us-central1", client=_FakeApi(sandboxes))


def test_sandbox_not_yet_reachable_is_retryable():
  assert _is_retryable(RuntimeError(NOT_READY)) is True


def test_command_timeout_is_not_retryable():
  assert _is_retryable(RuntimeError(COMMAND_TIMEOUT)) is False


def test_command_timeout_is_reported_once_as_data():
  """Re-running a command that timed out could repeat its side effects."""
  sandboxes = _FakeSandboxes(RuntimeError(COMMAND_TIMEOUT))
  result = _client(sandboxes).execute_bash(name="s", command="sleep 5", timeout=2)

  assert sandboxes.calls == 1
  assert result["timed_out"] is True
  assert result["returncode"] == 124
  assert "2s" in result["stderr"]


def test_transient_unreachable_sandbox_recovers():
  class Flaky(_FakeSandboxes):
    def execute_bash(self, **kwargs):
      self.calls += 1
      if self.calls == 1:
        raise RuntimeError(NOT_READY)
      return {"stdout": "hi", "stderr": "", "returncode": 0, "duration_ms": 3}

  sandboxes = Flaky()
  result = _client(sandboxes).execute_bash(name="s", command="echo hi")

  assert sandboxes.calls == 2
  assert result["stdout"] == "hi"
  assert result["timed_out"] is False


def test_persistent_transport_failure_still_raises():
  sandboxes = _FakeSandboxes(RuntimeError("503 UNAVAILABLE"))
  with pytest.raises(SandboxUnavailable):
    _client(sandboxes).execute_bash(name="s", command="echo hi")
  assert sandboxes.calls == 3
