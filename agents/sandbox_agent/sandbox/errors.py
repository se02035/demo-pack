"""Sandbox-related exceptions."""

from __future__ import annotations


class SandboxError(Exception):
  """Base class for sandbox errors."""


class SandboxUnavailable(SandboxError):
  """Sandbox could not be provisioned or reached a usable state in time."""


class SandboxTimeout(SandboxError):
  """A sandbox control-plane or data-plane call timed out."""


class SandboxQuotaExceeded(SandboxError):
  """Create/list/delete hit a platform quota limit."""


class SandboxNotFound(SandboxError):
  """A sandbox resource name no longer exists."""


class SandboxRestoreUnusable(SandboxError):
  """A restored-from-snapshot sandbox came up but never accepted traffic.

  Measured live: restore reports ``STATE_RUNNING`` within seconds but the data
  plane usually never answers. Callers fall back to a fresh sandbox rather than
  binding a session to one that can never run a command.
  """


class SandboxConfigError(SandboxError, ValueError):
  """Local configuration is invalid."""
