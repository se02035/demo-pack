"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache

from sandbox_agent.sandbox.errors import SandboxConfigError

_FORBIDDEN_SANDBOX_LOCATIONS = frozenset({"global", "us", "eu"})
_RUNTIME_NAME_RE = re.compile(
    r"^projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)/reasoningEngines/(?P<id>[^/]+)$"
)
_PLACEHOLDER_RUNTIME_IDS = frozenset({"RUNTIME_ID", "REPLACE_ME", "YOUR_RUNTIME_ID"})


@dataclass(frozen=True)
class Settings:
  project: str
  model_location: str
  sandbox_location: str
  runtime_name: str
  ttl_seconds: int
  default_timeout_seconds: int
  provision_deadline_seconds: int
  max_output_chars: int
  idle_pause_seconds: int
  idle_delete_seconds: int
  display_name_prefix: str
  model: str

  @property
  def ttl(self) -> str:
    return f"{self.ttl_seconds}s"

  @property
  def runtime_is_placeholder(self) -> bool:
    match = _RUNTIME_NAME_RE.match(self.runtime_name)
    if not match:
      return True
    return match.group("id") in _PLACEHOLDER_RUNTIME_IDS


def _env(name: str, default: str | None = None) -> str:
  value = os.environ.get(name)
  if value is None or value.strip() == "":
    if default is not None:
      return default
    raise SandboxConfigError(f"Missing required environment variable: {name}")
  return value.strip()


def _int_env(name: str, default: int) -> int:
  raw = os.environ.get(name)
  if raw is None or raw.strip() == "":
    return default
  try:
    value = int(raw)
  except ValueError as exc:
    raise SandboxConfigError(f"{name} must be an integer, got {raw!r}") from exc
  if value <= 0:
    raise SandboxConfigError(f"{name} must be positive, got {value}")
  return value


def validate_settings(settings: Settings, *, require_real_runtime: bool = False) -> Settings:
  loc = settings.sandbox_location.lower()
  if loc in _FORBIDDEN_SANDBOX_LOCATIONS:
    raise SandboxConfigError(
        f"SANDBOX_LOCATION={settings.sandbox_location!r} is not valid for "
        "sandboxes. Use a regional location such as us-central1 "
        "(global / us / eu are not supported for sandboxes)."
    )

  match = _RUNTIME_NAME_RE.match(settings.runtime_name)
  if not match:
    raise SandboxConfigError(
        "SANDBOX_RUNTIME_NAME must look like "
        "projects/<project>/locations/<location>/reasoningEngines/<id>, "
        f"got {settings.runtime_name!r}"
    )
  if match.group("location") != settings.sandbox_location:
    raise SandboxConfigError(
        "SANDBOX_LOCATION "
        f"({settings.sandbox_location!r}) does not match the location "
        f"embedded in SANDBOX_RUNTIME_NAME ({match.group('location')!r})."
    )
  runtime_project = match.group("project")
  # The API returns runtime names keyed by project *number*, while
  # GOOGLE_CLOUD_PROJECT is normally a project *id*. The two cannot be compared
  # without a Resource Manager lookup, so only reject a mismatch when both sides
  # are the same kind of identifier.
  if runtime_project != settings.project and (
      runtime_project.isdigit() == settings.project.isdigit()
  ):
    raise SandboxConfigError(
        "GOOGLE_CLOUD_PROJECT "
        f"({settings.project!r}) does not match the project "
        f"embedded in SANDBOX_RUNTIME_NAME ({runtime_project!r})."
    )
  if require_real_runtime and settings.runtime_is_placeholder:
    raise SandboxConfigError(
        "SANDBOX_RUNTIME_NAME still has a placeholder id. Run "
        "`python scripts/bootstrap_runtime.py` and paste the printed resource "
        "name into agents/sandbox_agent/.env."
    )
  return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
  """Load settings from the environment.

  Call ``get_settings.cache_clear()`` in tests after mutating env vars.
  Structural validation always runs; placeholder runtime ids are allowed so the
  ADK agent module can import before bootstrap. Call
  ``require_runtime_configured()`` before live sandbox calls.
  """
  project = _env("GOOGLE_CLOUD_PROJECT", "crafty-progress-421108")
  sandbox_location = _env("SANDBOX_LOCATION", "us-central1")
  default_runtime = (
      f"projects/{project}/locations/{sandbox_location}/reasoningEngines/RUNTIME_ID"
  )
  settings = Settings(
      project=project,
      model_location=_env("GOOGLE_CLOUD_LOCATION", "us-central1"),
      sandbox_location=sandbox_location,
      runtime_name=_env("SANDBOX_RUNTIME_NAME", default_runtime),
      ttl_seconds=_int_env("SANDBOX_TTL_SECONDS", 3600),
      default_timeout_seconds=_int_env("SANDBOX_DEFAULT_TIMEOUT_SECONDS", 120),
      provision_deadline_seconds=_int_env("SANDBOX_PROVISION_DEADLINE_SECONDS", 180),
      max_output_chars=_int_env("SANDBOX_MAX_OUTPUT_CHARS", 20_000),
      idle_pause_seconds=_int_env("SANDBOX_IDLE_PAUSE_SECONDS", 600),
      idle_delete_seconds=_int_env("SANDBOX_IDLE_DELETE_SECONDS", 3600),
      display_name_prefix=_env("SANDBOX_DISPLAY_NAME_PREFIX", "adk-demo"),
      model=_env("SANDBOX_AGENT_MODEL", "gemini-2.5-flash"),
  )
  return validate_settings(settings, require_real_runtime=False)


def require_runtime_configured() -> Settings:
  settings = get_settings()
  return validate_settings(settings, require_real_runtime=True)
