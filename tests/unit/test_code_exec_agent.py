"""Unit tests for the Code Execution agent wiring (no network)."""

from __future__ import annotations

import importlib
import sys

import pytest


def test_code_exec_agent_omits_static_sandbox(monkeypatch):
  """Per-session sandboxes require omitting sandbox_resource_name."""
  monkeypatch.setenv(
      "SANDBOX_RUNTIME_NAME",
      "projects/example/locations/us-central1/reasoningEngines/123",
  )
  monkeypatch.setenv("CODE_EXEC_AGENT_MODEL", "gemini-3.8-flash")
  sys.modules.pop("code_exec_agent.agent", None)
  sys.modules.pop("code_exec_agent", None)
  mod = importlib.import_module("code_exec_agent.agent")
  executor = mod.root_agent.code_executor
  assert executor.sandbox_resource_name is None
  assert executor.agent_engine_resource_name.endswith("/reasoningEngines/123")
  assert executor.code_block_delimiters == [("```python\n", "\n```")]


def test_code_exec_agent_imports_without_runtime(monkeypatch):
  """Discovery must not crash when .env is still a placeholder."""
  monkeypatch.setenv(
      "SANDBOX_RUNTIME_NAME",
      "projects/YOUR_GCP_PROJECT/locations/us-central1/reasoningEngines/RUNTIME_ID",
  )
  sys.modules.pop("code_exec_agent.agent", None)
  sys.modules.pop("code_exec_agent", None)
  mod = importlib.import_module("code_exec_agent.agent")
  assert mod.root_agent.name == "code_exec_agent"
  assert mod.root_agent.code_executor.sandbox_resource_name is None
