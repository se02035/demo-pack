"""SDK contract tests — no network, assert live package signatures."""

from __future__ import annotations

import inspect

import pytest


def test_agentplatform_sandboxes_signatures():
  import agentplatform
  from agentplatform._genai import sandboxes as sb

  create = inspect.signature(sb.Sandboxes.create)
  assert "name" in create.parameters
  assert "spec" in create.parameters
  assert "config" in create.parameters

  execute_bash = inspect.signature(sb.Sandboxes.execute_bash)
  for key in ("name", "command", "cwd", "timeout"):
    assert key in execute_bash.parameters

  for method in ("get", "list", "delete", "pause", "resume"):
    sig = inspect.signature(getattr(sb.Sandboxes, method))
    assert "name" in sig.parameters


def test_sandbox_state_enum_members():
  from agentplatform._genai.types import common as c

  needed = {
      "STATE_RUNNING",
      "STATE_PAUSED",
      "STATE_PROVISIONING",
      "STATE_RESUMING",
      "STATE_TERMINATED",
      "STATE_DELETED",
      "STATE_DEPROVISIONING",
      "STATE_PAUSING",
      "STATE_STOPPING",
  }
  have = {e.name for e in c.SandboxState}
  missing = needed - have
  assert not missing, f"SandboxState missing members: {missing}"


def test_create_runtime_sandbox_config_fields():
  from agentplatform._genai.types import common as c

  fields = set(c.CreateRuntimeSandboxConfig.model_fields)
  for key in (
      "display_name",
      "ttl",
      "wait_for_completion",
      "sandbox_environment_template",
      "sandbox_environment_snapshot",
  ):
    assert key in fields


def test_snapshots_and_templates_signatures():
  import agentplatform
  from agentplatform._genai.types import common as c

  client = agentplatform.Client(project="p", location="us-central1")
  snap_create = inspect.signature(client.sandboxes.snapshots.create)
  assert "source_sandbox_environment_name" in snap_create.parameters
  assert "config" in snap_create.parameters
  for method in ("get", "list", "delete"):
    assert "name" in inspect.signature(getattr(client.sandboxes.snapshots, method)).parameters

  tpl_create = inspect.signature(client.sandboxes.templates.create)
  assert "name" in tpl_create.parameters
  assert "display_name" in tpl_create.parameters

  fields = set(c.CreateRuntimeSandboxSnapshotConfig.model_fields)
  for key in ("display_name", "ttl", "wait_for_completion"):
    assert key in fields


def test_adk_function_tool_and_app_importable():
  from google.adk import Agent
  from google.adk.apps import App
  from google.adk.plugins import BasePlugin
  from google.adk.tools import FunctionTool

  assert Agent is not None
  assert App is not None
  assert BasePlugin is not None
  assert FunctionTool is not None


def test_config_rejects_global_sandbox_location(monkeypatch):
  from sandbox_agent.config import get_settings, validate_settings
  from sandbox_agent.sandbox.errors import SandboxConfigError

  monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "YOUR_GCP_PROJECT")
  monkeypatch.setenv("SANDBOX_LOCATION", "global")
  monkeypatch.setenv(
      "SANDBOX_RUNTIME_NAME",
      "projects/YOUR_GCP_PROJECT/locations/global/reasoningEngines/x",
  )
  get_settings.cache_clear()
  with pytest.raises(SandboxConfigError, match="not valid for sandboxes"):
    get_settings()
  get_settings.cache_clear()
