"""SessionSandboxManager: exactly one sandbox per ADK session."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Mapping, MutableMapping

from sandbox_agent.config import Settings
from sandbox_agent.sandbox.client import SandboxClientProtocol
from sandbox_agent.sandbox.errors import (
    SandboxNotFound,
    SandboxQuotaExceeded,
    SandboxUnavailable,
)
from sandbox_agent.sandbox.models import (
    STATE_SANDBOX_HISTORY_KEY,
    STATE_SANDBOX_KEY,
    SandboxBinding,
    SessionKey,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

_RUNNING = "STATE_RUNNING"
_PAUSED = "STATE_PAUSED"
_PROVISIONING = "STATE_PROVISIONING"
_RESUMING = "STATE_RESUMING"
_DEAD = frozenset({
    "STATE_TERMINATED",
    "STATE_DELETED",
    "STATE_DEPROVISIONING",
    "STATE_PAUSING",
    "STATE_STOPPING",
    "STATE_UNSPECIFIED",
})


class SessionSandboxManager:
  """Owns the one-sandbox-per-session invariant.

  Resolution is keyed by ``(app_name, user_id, session_id)`` and protected by a
  per-key ``asyncio.Lock``. Bindings are mirrored into ADK session state so a
  process reload can reclaim an existing sandbox instead of orphaning it.
  """

  def __init__(
      self,
      *,
      client: SandboxClientProtocol,
      settings: Settings,
  ) -> None:
    self._client = client
    self._settings = settings
    self._cache: dict[SessionKey, SandboxBinding] = {}
    self._locks: dict[SessionKey, asyncio.Lock] = defaultdict(asyncio.Lock)
    self._last_used: dict[SessionKey, float] = {}
    self._create_counts: dict[SessionKey, int] = defaultdict(int)

  @property
  def create_counts(self) -> Mapping[SessionKey, int]:
    return dict(self._create_counts)

  def _lock_for(self, key: SessionKey) -> asyncio.Lock:
    return self._locks[key]

  def session_key_from_context(self, tool_context: Any) -> SessionKey:
    session = tool_context.session
    return SessionKey(
        app_name=session.app_name,
        user_id=session.user_id,
        session_id=session.id,
    )

  def read_binding(self, state: Mapping[str, Any] | Any) -> SandboxBinding | None:
    raw = None
    if hasattr(state, "get"):
      raw = state.get(STATE_SANDBOX_KEY)
    elif STATE_SANDBOX_KEY in state:
      raw = state[STATE_SANDBOX_KEY]
    if not isinstance(raw, Mapping):
      return None
    return SandboxBinding.from_state(raw)

  def write_binding(self, state: MutableMapping[str, Any] | Any, binding: SandboxBinding) -> None:
    existing = self.read_binding(state)
    if existing and existing.name != binding.name:
      history: list[str] = []
      if hasattr(state, "get"):
        hist_raw = state.get(STATE_SANDBOX_HISTORY_KEY) or []
      else:
        hist_raw = state[STATE_SANDBOX_HISTORY_KEY] if STATE_SANDBOX_HISTORY_KEY in state else []
      if isinstance(hist_raw, list):
        history = list(hist_raw)
      history.append(existing.name)
      state[STATE_SANDBOX_HISTORY_KEY] = history
    state[STATE_SANDBOX_KEY] = binding.to_state()

  def clear_binding(self, state: MutableMapping[str, Any] | Any) -> SandboxBinding | None:
    existing = self.read_binding(state)
    if existing is not None:
      # Prefer pop when available; otherwise overwrite with None.
      if hasattr(state, "pop"):
        try:
          state.pop(STATE_SANDBOX_KEY, None)
        except TypeError:
          state[STATE_SANDBOX_KEY] = None
      else:
        state[STATE_SANDBOX_KEY] = None
    return existing

  def display_name_for(self, key: SessionKey) -> str:
    prefix = self._settings.display_name_prefix
    return f"{prefix}-{key.display_suffix()}"[:120]

  async def resolve(self, tool_context: Any) -> SandboxBinding:
    key = self.session_key_from_context(tool_context)
    async with self._lock_for(key):
      binding = self._cache.get(key) or self.read_binding(tool_context.state)
      if binding is not None:
        recovered = await self._try_reuse(binding)
        if recovered is not None:
          self._cache[key] = recovered
          self.write_binding(tool_context.state, recovered)
          self._last_used[key] = time.monotonic()
          return recovered
        # Dead / missing — fall through to create, keeping history.
        logger.info("Sandbox %s is not reusable; creating a replacement", binding.name)

      created = await self._create(key)
      self._cache[key] = created
      self.write_binding(tool_context.state, created)
      self._last_used[key] = time.monotonic()
      return created

  async def _try_reuse(self, binding: SandboxBinding) -> SandboxBinding | None:
    try:
      env = await asyncio.to_thread(self._client.get, name=binding.name)
    except SandboxNotFound:
      return None

    state = env.get("state")
    if state == _RUNNING:
      return binding
    if state == _PAUSED:
      await asyncio.to_thread(
          self._client.resume,
          name=binding.name,
          wait_for_completion=True,
      )
      return binding
    if state in {_PROVISIONING, _RESUMING}:
      return await self._wait_until_running(binding)
    if state in _DEAD or state is None:
      return None
    # Unknown state — be conservative and re-create.
    logger.warning("Unrecognized sandbox state %r for %s", state, binding.name)
    return None

  async def _wait_until_running(self, binding: SandboxBinding) -> SandboxBinding | None:
    deadline = time.monotonic() + self._settings.provision_deadline_seconds
    while time.monotonic() < deadline:
      env = await asyncio.to_thread(self._client.get, name=binding.name)
      state = env.get("state")
      if state == _RUNNING:
        return binding
      if state in _DEAD:
        return None
      await asyncio.sleep(1.0)
    raise SandboxUnavailable(
        f"Sandbox {binding.name} did not reach STATE_RUNNING within "
        f"{self._settings.provision_deadline_seconds}s"
    )

  async def _create(self, key: SessionKey) -> SandboxBinding:
    display_name = self.display_name_for(key)
    try:
      env = await asyncio.to_thread(
          self._client.create,
          runtime_name=self._settings.runtime_name,
          display_name=display_name,
          ttl=self._settings.ttl,
          wait_for_completion=True,
      )
    except SandboxQuotaExceeded:
      raise
    except Exception as exc:  # noqa: BLE001
      raise SandboxUnavailable(f"Failed to create sandbox: {exc}") from exc

    name = env.get("name")
    if not name:
      raise SandboxUnavailable(f"create returned no name: {env!r}")

    state = env.get("state")
    if state not in {None, _RUNNING}:
      # wait_for_completion should have blocked; poll as a safety net.
      provisional = SandboxBinding(
          name=name,
          display_name=env.get("display_name") or display_name,
          created_at=utc_now_iso(),
          session_id=key.session_id,
          user_id=key.user_id,
          app_name=key.app_name,
      )
      recovered = await self._wait_until_running(provisional)
      if recovered is None:
        raise SandboxUnavailable(f"Newly created sandbox {name} never became RUNNING")
      name = recovered.name

    self._create_counts[key] += 1
    return SandboxBinding(
        name=name,
        display_name=env.get("display_name") or display_name,
        created_at=utc_now_iso(),
        session_id=key.session_id,
        user_id=key.user_id,
        app_name=key.app_name,
    )

  async def end_session(self, tool_context: Any) -> dict[str, Any]:
    key = self.session_key_from_context(tool_context)
    async with self._lock_for(key):
      binding = self._cache.pop(key, None) or self.read_binding(tool_context.state)
      self.clear_binding(tool_context.state)
      self._last_used.pop(key, None)
      if binding is None:
        return {"deleted": False, "reason": "no_sandbox_bound"}
      try:
        await asyncio.to_thread(self._client.delete, name=binding.name)
      except SandboxNotFound:
        pass
      return {
          "deleted": True,
          "sandbox_name": binding.name,
          "display_name": binding.display_name,
      }

  def cached_bindings(self) -> list[SandboxBinding]:
    return list(self._cache.values())

  def touch(self, key: SessionKey) -> None:
    self._last_used[key] = time.monotonic()

  def idle_keys(self, *, older_than_seconds: float) -> list[SessionKey]:
    now = time.monotonic()
    return [
        key
        for key, last in self._last_used.items()
        if now - last >= older_than_seconds and key in self._cache
    ]

  async def pause_idle(self, *, older_than_seconds: float) -> list[str]:
    paused: list[str] = []
    for key in self.idle_keys(older_than_seconds=older_than_seconds):
      binding = self._cache.get(key)
      if binding is None:
        continue
      try:
        await asyncio.to_thread(
            self._client.pause,
            name=binding.name,
            wait_for_completion=True,
        )
        paused.append(binding.name)
      except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to pause idle sandbox %s: %s", binding.name, exc)
    return paused

  async def delete_idle(self, *, older_than_seconds: float) -> list[str]:
    deleted: list[str] = []
    for key in self.idle_keys(older_than_seconds=older_than_seconds):
      binding = self._cache.pop(key, None)
      self._last_used.pop(key, None)
      if binding is None:
        continue
      try:
        await asyncio.to_thread(self._client.delete, name=binding.name)
        deleted.append(binding.name)
      except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete idle sandbox %s: %s", binding.name, exc)
    return deleted

  async def close_all(self) -> None:
    bindings = list(self._cache.values())
    self._cache.clear()
    self._last_used.clear()
    for binding in bindings:
      try:
        await asyncio.to_thread(self._client.delete, name=binding.name)
      except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete sandbox %s on close: %s", binding.name, exc)
