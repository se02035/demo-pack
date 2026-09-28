"""Sandbox binding models and session-state keys."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


STATE_SANDBOX_KEY = "sandbox"
STATE_SANDBOX_HISTORY_KEY = "sandbox_history"
STATE_SANDBOX_REQUESTED_AT_KEY = "sandbox_requested_at"


@dataclass(frozen=True)
class SessionKey:
  app_name: str
  user_id: str
  session_id: str

  def display_suffix(self) -> str:
    # Keep display names short and uniquely attributable to the session.
    safe_session = self.session_id.replace("/", "-")[:48]
    safe_user = self.user_id.replace("/", "-")[:16]
    return f"{safe_user}-{safe_session}"


@dataclass(frozen=True)
class SandboxBinding:
  name: str
  display_name: str
  created_at: str
  session_id: str
  user_id: str
  app_name: str

  def to_state(self) -> dict[str, Any]:
    return asdict(self)

  @classmethod
  def from_state(cls, data: Mapping[str, Any]) -> SandboxBinding | None:
    try:
      return cls(
          name=str(data["name"]),
          display_name=str(data.get("display_name") or ""),
          created_at=str(data.get("created_at") or ""),
          session_id=str(data.get("session_id") or ""),
          user_id=str(data.get("user_id") or ""),
          app_name=str(data.get("app_name") or ""),
      )
    except (KeyError, TypeError, ValueError):
      return None


def utc_now_iso() -> str:
  return datetime.now(timezone.utc).isoformat()
