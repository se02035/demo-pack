"""Process-wide sandbox manager wiring."""

from __future__ import annotations

from functools import lru_cache

from sandbox_agent.sandbox.client import SandboxClient
from sandbox_agent.sandbox.manager import SessionSandboxManager


@lru_cache(maxsize=1)
def get_manager() -> SessionSandboxManager:
  from sandbox_agent.config import require_runtime_configured

  settings = require_runtime_configured()
  client = SandboxClient(project=settings.project, location=settings.sandbox_location)
  return SessionSandboxManager(client=client, settings=settings)


def reset_manager_for_tests() -> None:
  """Clear the process-wide manager cache (tests only)."""
  get_manager.cache_clear()
