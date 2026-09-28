"""ADK plugin for sandbox lifecycle bookkeeping and idle reaping."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.plugins import BasePlugin

from sandbox_agent.config import get_settings
from sandbox_agent.sandbox.models import STATE_SANDBOX_REQUESTED_AT_KEY, utc_now_iso
from sandbox_agent.sandbox.runtime import get_manager

logger = logging.getLogger(__name__)


class SandboxLifecyclePlugin(BasePlugin):
  """Stamps session activity and runs an idle pause/delete reaper."""

  def __init__(self) -> None:
    super().__init__(name="sandbox_lifecycle")
    self._reaper_task: asyncio.Task | None = None
    self._stop = asyncio.Event()

  async def before_run_callback(
      self, *, invocation_context: Any
  ) -> None:
    session = invocation_context.session
    # Stamp activity; do NOT provision eagerly (lazy on first tool call).
    try:
      session.state[STATE_SANDBOX_REQUESTED_AT_KEY] = utc_now_iso()
    except Exception as exc:  # noqa: BLE001
      logger.debug("Could not stamp sandbox_requested_at: %s", exc)

    mgr = None
    try:
      from sandbox_agent.config import get_settings

      if not get_settings().runtime_is_placeholder:
        mgr = get_manager()
    except Exception as exc:  # noqa: BLE001
      logger.debug("Sandbox manager unavailable in before_run: %s", exc)

    if mgr is not None:
      from sandbox_agent.sandbox.models import SessionKey

      key = SessionKey(
          app_name=session.app_name,
          user_id=session.user_id,
          session_id=session.id,
      )
      mgr.touch(key)
      self._ensure_reaper()
    return None

  def _ensure_reaper(self) -> None:
    if self._reaper_task is not None and not self._reaper_task.done():
      return
    try:
      loop = asyncio.get_running_loop()
    except RuntimeError:
      return
    self._stop.clear()
    self._reaper_task = loop.create_task(self._reaper_loop(), name="sandbox-idle-reaper")

  async def _reaper_loop(self) -> None:
    settings = get_settings()
    mgr = get_manager()
    while not self._stop.is_set():
      try:
        if settings.idle_pause_seconds:
          await mgr.pause_idle(older_than_seconds=settings.idle_pause_seconds)
        await mgr.delete_idle(older_than_seconds=settings.idle_delete_seconds)
      except Exception as exc:  # noqa: BLE001
        logger.warning("Idle reaper iteration failed: %s", exc)
      try:
        await asyncio.wait_for(self._stop.wait(), timeout=30.0)
      except asyncio.TimeoutError:
        continue

  async def close(self) -> None:
    self._stop.set()
    if self._reaper_task is not None:
      self._reaper_task.cancel()
      try:
        await self._reaper_task
      except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
      self._reaper_task = None
    try:
      await get_manager().close_all()
    except Exception as exc:  # noqa: BLE001
      logger.warning("Sandbox close_all failed: %s", exc)
