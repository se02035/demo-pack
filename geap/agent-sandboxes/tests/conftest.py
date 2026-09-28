"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"
if str(AGENTS) not in sys.path:
  sys.path.insert(0, str(AGENTS))


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch):
  monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "crafty-progress-421108")
  monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
  monkeypatch.setenv("SANDBOX_LOCATION", "us-central1")
  monkeypatch.setenv(
      "SANDBOX_RUNTIME_NAME",
      "projects/crafty-progress-421108/locations/us-central1/reasoningEngines/test-runtime",
  )
  monkeypatch.setenv("SANDBOX_TTL_SECONDS", "3600")
  monkeypatch.setenv("SANDBOX_MAX_OUTPUT_CHARS", "100")
  monkeypatch.setenv("SANDBOX_DISPLAY_NAME_PREFIX", "adk-demo")
  monkeypatch.setenv("SANDBOX_PROVISION_DEADLINE_SECONDS", "5")
  monkeypatch.setenv("SANDBOX_SNAPSHOT_TTL_SECONDS", "86400")
  monkeypatch.setenv("SANDBOX_AUTO_SNAPSHOT_ON_IDLE_DELETE", "true")
  monkeypatch.setenv("SANDBOX_AUTO_RESTORE_ON_EXPIRY", "true")
  monkeypatch.setenv("SANDBOX_MAX_SNAPSHOTS_PER_SESSION", "5")
  monkeypatch.setenv("SANDBOX_TEMPLATE_NAME", "")
  from sandbox_agent.config import get_settings

  get_settings.cache_clear()
  yield get_settings()
  get_settings.cache_clear()


@pytest.fixture
def fake_client():
  from tests.fakes import FakeSandboxClient

  return FakeSandboxClient()


@pytest.fixture
def manager(settings_env, fake_client):
  from sandbox_agent.sandbox.manager import SessionSandboxManager

  return SessionSandboxManager(client=fake_client, settings=settings_env)
