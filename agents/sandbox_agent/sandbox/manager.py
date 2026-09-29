"""SessionSandboxManager: exactly one sandbox per ADK session."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping

from sandbox_agent.config import Settings
from sandbox_agent.sandbox.client import SandboxClientProtocol
from sandbox_agent.sandbox.errors import (
    SandboxNotFound,
    SandboxQuotaExceeded,
    SandboxRestoreUnusable,
    SandboxUnavailable,
)
from sandbox_agent.sandbox.models import (
    STATE_SANDBOX_HISTORY_KEY,
    STATE_SANDBOX_KEY,
    STATE_SANDBOX_SNAPSHOTS_KEY,
    SandboxBinding,
    SessionKey,
    SnapshotRecord,
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


def _parse_expire_time(value: object) -> datetime | None:
  if value is None:
    return None
  if isinstance(value, datetime):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
  text = str(value).strip()
  if not text:
    return None
  try:
    if text.endswith("Z"):
      text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
  except ValueError:
    return None


def seconds_until_expiry(expire_time: object) -> int | None:
  parsed = _parse_expire_time(expire_time)
  if parsed is None:
    return None
  return int((parsed - datetime.now(timezone.utc)).total_seconds())


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
    self._template_name: str | None = settings.template_name or None
    self._template_lock = asyncio.Lock()

  @property
  def create_counts(self) -> Mapping[SessionKey, int]:
    return dict(self._create_counts)

  @property
  def client(self) -> SandboxClientProtocol:
    return self._client

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
      if hasattr(state, "pop"):
        try:
          state.pop(STATE_SANDBOX_KEY, None)
        except TypeError:
          state[STATE_SANDBOX_KEY] = None
      else:
        state[STATE_SANDBOX_KEY] = None
    return existing

  def read_snapshots(self, state: Mapping[str, Any] | Any) -> list[SnapshotRecord]:
    raw = None
    if hasattr(state, "get"):
      raw = state.get(STATE_SANDBOX_SNAPSHOTS_KEY)
    elif STATE_SANDBOX_SNAPSHOTS_KEY in state:
      raw = state[STATE_SANDBOX_SNAPSHOTS_KEY]
    if not isinstance(raw, list):
      return []
    out: list[SnapshotRecord] = []
    for item in raw:
      if isinstance(item, Mapping):
        rec = SnapshotRecord.from_state(item)
        if rec is not None:
          out.append(rec)
    return out

  def write_snapshots(
      self, state: MutableMapping[str, Any] | Any, records: list[SnapshotRecord]
  ) -> None:
    state[STATE_SANDBOX_SNAPSHOTS_KEY] = [r.to_state() for r in records]

  def display_name_for(self, key: SessionKey) -> str:
    prefix = self._settings.display_name_prefix
    return f"{prefix}-{key.display_suffix()}"[:120]

  def snapshot_display_name(self, key: SessionKey, label: str) -> str:
    safe_label = label.replace("/", "-").replace(" ", "-")[:40]
    return f"{self._settings.display_name_prefix}-{key.display_suffix()}-{safe_label}"[:120]

  async def ensure_template(self) -> str:
    """Return a reusable shell template name, creating one if needed."""
    async with self._template_lock:
      if self._template_name:
        try:
          await asyncio.to_thread(self._client.get_template, name=self._template_name)
          return self._template_name
        except SandboxNotFound:
          logger.warning(
              "Configured SANDBOX_TEMPLATE_NAME %s is gone; recreating",
              self._template_name,
          )
          self._template_name = None

      display = self._settings.template_display_name
      # Prefer an existing live template with our display name.
      try:
        listed = await asyncio.to_thread(
            self._client.list_templates, runtime_name=self._settings.runtime_name
        )
      except Exception as exc:  # noqa: BLE001
        logger.warning("list_templates failed: %s", exc)
        listed = []
      for tpl in listed:
        if tpl.get("display_name") != display or not tpl.get("name"):
          continue
        try:
          await asyncio.to_thread(self._client.get_template, name=tpl["name"])
        except SandboxNotFound:
          continue
        self._template_name = tpl["name"]
        return self._template_name

      created = await asyncio.to_thread(
          self._client.create_template,
          runtime_name=self._settings.runtime_name,
          display_name=display,
          wait_for_completion=True,
      )
      name = created.get("name")
      if not name:
        raise SandboxUnavailable(f"create_template returned no name: {created!r}")
      self._template_name = name
      logger.info(
          "Pinned shell template %s (set SANDBOX_TEMPLATE_NAME=%s to reuse across processes)",
          name,
          name,
      )
      return name

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
        logger.info("Sandbox %s is not reusable; replacing", binding.name)
        # Delete the dead/unusable sandbox *before* creating a replacement.
        # Otherwise a failed resume (common platform defect) leaves two live
        # sandboxes with the same display name and breaks the one-per-session
        # invariant until TTL or the reaper catches up.
        self._cache.pop(key, None)
        try:
          await asyncio.to_thread(self._client.delete, name=binding.name)
        except SandboxNotFound:
          pass
        except Exception as exc:  # noqa: BLE001
          logger.warning(
              "Failed to delete unusable sandbox %s during replace: %s",
              binding.name,
              exc,
          )
        self.clear_binding(tool_context.state)
        history: list[str] = []
        if hasattr(tool_context.state, "get"):
          hist_raw = tool_context.state.get(STATE_SANDBOX_HISTORY_KEY) or []
        else:
          hist_raw = []
        if isinstance(hist_raw, list):
          history = list(hist_raw)
        history.append(binding.name)
        tool_context.state[STATE_SANDBOX_HISTORY_KEY] = history

        if self._settings.auto_restore_on_expiry:
          restored = await self._try_auto_restore(tool_context, key)
          if restored is not None:
            self._cache[key] = restored
            self.write_binding(tool_context.state, restored)
            self._last_used[key] = time.monotonic()
            return restored

      created = await self._create(key)
      self._cache[key] = created
      self.write_binding(tool_context.state, created)
      self._last_used[key] = time.monotonic()
      return created

  async def _try_auto_restore(
      self, tool_context: Any, key: SessionKey
  ) -> SandboxBinding | None:
    candidates: list[tuple[str, str]] = []  # (name, label-ish)
    for snap in reversed(self.read_snapshots(tool_context.state)):
      candidates.append((snap.name, snap.label))

    if not candidates:
      # Idle-delete auto-snapshots may exist only on the platform (no tool_context
      # to write session state). Find them by display-name prefix.
      prefix = f"{self._settings.display_name_prefix}-{key.display_suffix()}-"
      try:
        listed = await asyncio.to_thread(
            self._client.list_snapshots, runtime_name=self._settings.runtime_name
        )
      except Exception as exc:  # noqa: BLE001
        logger.warning("list_snapshots during auto-restore failed: %s", exc)
        listed = []
      matched = [
          s for s in listed
          if (s.get("display_name") or "").startswith(prefix) and s.get("name")
      ]
      # Newest last in list order is undefined; sort by create_time if present.
      matched.sort(key=lambda s: str(s.get("create_time") or ""))
      for s in reversed(matched):
        candidates.append((s["name"], s.get("display_name") or ""))

    for name, _label in candidates:
      try:
        await asyncio.to_thread(self._client.get_snapshot, name=name)
      except SandboxNotFound:
        continue
      logger.info("Auto-restoring session %s from snapshot %s", key.session_id, name)
      try:
        return await self._create(
            key,
            from_snapshot=name,
            restored_from=name,
        )
      except SandboxRestoreUnusable as exc:
        # Restore is unreliable on the platform today; an empty-but-working
        # sandbox beats a dead one, so fall through to a plain create.
        logger.warning("Auto-restore from %s unusable: %s", name, exc)
        return None
    return None

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
      return binding if await self._probe_ready(binding.name) else None
    if state in {_PROVISIONING, _RESUMING}:
      recovered = await self._wait_until_running(binding)
      if recovered is None:
        return None
      return recovered if await self._probe_ready(binding.name) else None
    if state in _DEAD or state is None:
      return None
    logger.warning("Unrecognized sandbox state %r for %s", state, binding.name)
    return None

  async def _probe_ready(self, name: str, *, deadline_seconds: float | None = None) -> bool:
    """Absorb the post-create/resume readiness race; report whether it worked.

    ``STATE_RUNNING`` only means the control plane is done — the data plane can
    still refuse traffic for ~20s after create, and a restored-from-snapshot
    sandbox may never accept it at all. Short probes keep the common case
    cheap; the boolean lets callers reject a sandbox that never came up.
    """
    budget = (
        self._settings.readiness_deadline_seconds
        if deadline_seconds is None
        else deadline_seconds
    )
    deadline = time.monotonic() + budget
    attempt = 0
    while True:
      attempt += 1
      try:
        # One attempt per iteration: this loop *is* the retry, and stacking the
        # client's own backoff on top turns a 60s budget into several minutes.
        await asyncio.to_thread(
            self._client.execute_bash,
            name=name,
            command="true",
            timeout=10,
            max_retries=1,
        )
        return True
      except Exception as exc:  # noqa: BLE001
        if time.monotonic() >= deadline:
          logger.warning(
              "Sandbox %s never accepted traffic within %.0fs (%s attempts): %s",
              name,
              budget,
              attempt,
              exc,
          )
          return False
        await asyncio.sleep(2.0)

  async def _ensure_running_for_snapshot(self, name: str) -> str:
    """Bring a sandbox to exactly ``STATE_RUNNING`` before snapshotting it.

    The API rejects a snapshot of anything else ("must be in RUNNING state to
    be snapshotted"), and `STATE_RESUMING` is easy to hit: any `execute_bash`
    against a paused sandbox makes the platform start a resume on its own.
    """
    deadline = time.monotonic() + self._settings.provision_deadline_seconds
    resumed = False
    while True:
      env = await asyncio.to_thread(self._client.get, name=name)
      state = env.get("state")
      if state == _RUNNING:
        return state
      if state == _PAUSED and not resumed:
        resumed = True
        await asyncio.to_thread(
            self._client.resume, name=name, wait_for_completion=True
        )
      elif state in _DEAD or state is None:
        raise SandboxUnavailable(
            f"Cannot snapshot {name}: state is {state!r}"
        )
      if time.monotonic() >= deadline:
        raise SandboxUnavailable(
            f"Sandbox {name} did not reach STATE_RUNNING for snapshot "
            f"within {self._settings.provision_deadline_seconds}s (state {state!r})"
        )
      await asyncio.sleep(2.0)

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

  async def _create(
      self,
      key: SessionKey,
      *,
      from_snapshot: str | None = None,
      restored_from: str | None = None,
  ) -> SandboxBinding:
    display_name = self.display_name_for(key)
    template = None if from_snapshot else await self.ensure_template()
    try:
      env = await asyncio.to_thread(
          self._client.create,
          runtime_name=self._settings.runtime_name,
          display_name=display_name,
          ttl=self._settings.ttl,
          wait_for_completion=True,
          sandbox_environment_template=template,
          sandbox_environment_snapshot=from_snapshot,
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
      provisional = SandboxBinding(
          name=name,
          display_name=env.get("display_name") or display_name,
          created_at=utc_now_iso(),
          session_id=key.session_id,
          user_id=key.user_id,
          app_name=key.app_name,
          restored_from=restored_from,
      )
      recovered = await self._wait_until_running(provisional)
      if recovered is None:
        raise SandboxUnavailable(f"Newly created sandbox {name} never became RUNNING")
      name = recovered.name

    ready = await self._probe_ready(name)
    if not ready and from_snapshot:
      # Don't bind a session to a sandbox that can never run a command; the
      # caller falls back to a fresh one.
      try:
        await asyncio.to_thread(self._client.delete, name=name)
      except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete unusable restored sandbox %s: %s", name, exc)
      raise SandboxRestoreUnusable(
          f"Sandbox restored from {from_snapshot} reported RUNNING but never "
          "accepted commands."
      )
    self._create_counts[key] += 1
    return SandboxBinding(
        name=name,
        display_name=env.get("display_name") or display_name,
        created_at=utc_now_iso(),
        session_id=key.session_id,
        user_id=key.user_id,
        app_name=key.app_name,
        restored_from=restored_from or env.get("sandbox_environment_snapshot"),
    )

  async def pause_session(self, tool_context: Any) -> dict[str, Any]:
    key = self.session_key_from_context(tool_context)
    async with self._lock_for(key):
      binding = self._cache.get(key) or self.read_binding(tool_context.state)
      if binding is None:
        return {"ok": False, "paused": False, "reason": "no_sandbox_bound"}
      env = await asyncio.to_thread(self._client.get, name=binding.name)
      if env.get("state") == _PAUSED:
        return {
            "ok": True,
            "paused": False,
            "already_paused": True,
            "sandbox_name": binding.name,
            "state": _PAUSED,
        }
      t0 = time.monotonic()
      paused = await asyncio.to_thread(
          self._client.pause, name=binding.name, wait_for_completion=True
      )
      self._last_used[key] = time.monotonic()
      return {
          "ok": True,
          "paused": True,
          "sandbox_name": binding.name,
          "state": paused.get("state") or _PAUSED,
          "pause_seconds": round(time.monotonic() - t0, 3),
          "expire_time": paused.get("expire_time") or env.get("expire_time"),
      }

  async def resume_session(self, tool_context: Any) -> dict[str, Any]:
    key = self.session_key_from_context(tool_context)
    async with self._lock_for(key):
      binding = self._cache.get(key) or self.read_binding(tool_context.state)
      if binding is None:
        return {"ok": False, "resumed": False, "reason": "no_sandbox_bound"}
      env = await asyncio.to_thread(self._client.get, name=binding.name)
      if env.get("state") == _RUNNING:
        return {
            "ok": True,
            "resumed": False,
            "already_running": True,
            "sandbox_name": binding.name,
            "state": _RUNNING,
        }
      if env.get("state") != _PAUSED:
        return {
            "ok": False,
            "resumed": False,
            "reason": f"cannot_resume_from_{env.get('state')}",
            "sandbox_name": binding.name,
            "state": env.get("state"),
        }
      t0 = time.monotonic()
      resumed = await asyncio.to_thread(
          self._client.resume, name=binding.name, wait_for_completion=True
      )
      await self._probe_ready(binding.name)
      self._last_used[key] = time.monotonic()
      return {
          "ok": True,
          "resumed": True,
          "sandbox_name": binding.name,
          "state": resumed.get("state") or _RUNNING,
          "resume_seconds": round(time.monotonic() - t0, 3),
          "expire_time": resumed.get("expire_time") or env.get("expire_time"),
      }

  def find_snapshot(
      self, state: Mapping[str, Any] | Any, label_or_name: str
  ) -> SnapshotRecord | None:
    for snap in self.read_snapshots(state):
      if snap.label == label_or_name or snap.name == label_or_name:
        return snap
    return None

  async def snapshot_session(
      self,
      tool_context: Any,
      *,
      label: str,
      auto: bool = False,
  ) -> dict[str, Any]:
    key = self.session_key_from_context(tool_context)
    async with self._lock_for(key):
      binding = self._cache.get(key) or self.read_binding(tool_context.state)
      if binding is None:
        return {"ok": False, "reason": "no_sandbox_bound"}
      # The API only snapshots a sandbox in exactly STATE_RUNNING.
      await self._ensure_running_for_snapshot(binding.name)

      display = self.snapshot_display_name(key, label)
      t0 = time.monotonic()
      snap = await asyncio.to_thread(
          self._client.create_snapshot,
          source_sandbox_name=binding.name,
          display_name=display,
          ttl=self._settings.snapshot_ttl,
          wait_for_completion=True,
      )
      name = snap.get("name")
      if not name:
        raise SandboxUnavailable(f"create_snapshot returned no name: {snap!r}")

      records = self.read_snapshots(tool_context.state)
      # Replace same label if re-taken.
      records = [r for r in records if r.label != label]
      records.append(
          SnapshotRecord(
              name=name,
              label=label,
              created_at=utc_now_iso(),
              expire_time=str(snap.get("expire_time") or ""),
              size_bytes=snap.get("size_bytes"),
              source_sandbox=binding.name,
              auto=auto,
          )
      )
      records = await self._enforce_snapshot_cap(tool_context, records)
      self.write_snapshots(tool_context.state, records)
      self._last_used[key] = time.monotonic()
      return {
          "ok": True,
          "sandbox_name": binding.name,
          "snapshot_name": name,
          "label": label,
          "display_name": snap.get("display_name") or display,
          "expire_time": snap.get("expire_time"),
          "size_bytes": snap.get("size_bytes"),
          "auto": auto,
          "snapshot_seconds": round(time.monotonic() - t0, 3),
      }

  async def _enforce_snapshot_cap(
      self, tool_context: Any, records: list[SnapshotRecord]
  ) -> list[SnapshotRecord]:
    cap = self._settings.max_snapshots_per_session
    if len(records) <= cap:
      return records
    # Evict oldest auto snapshots first; never touch manuals until only autos left.
    autos = [r for r in records if r.auto]
    manuals = [r for r in records if not r.auto]
    while len(autos) + len(manuals) > cap and autos:
      victim = autos.pop(0)
      try:
        await asyncio.to_thread(self._client.delete_snapshot, name=victim.name)
      except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to evict snapshot %s: %s", victim.name, exc)
    return manuals + autos

  async def list_session_snapshots(self, tool_context: Any) -> dict[str, Any]:
    records = self.read_snapshots(tool_context.state)
    live: list[dict[str, Any]] = []
    kept: list[SnapshotRecord] = []
    for rec in records:
      try:
        snap = await asyncio.to_thread(self._client.get_snapshot, name=rec.name)
      except SandboxNotFound:
        continue
      kept.append(rec)
      live.append({
          "name": rec.name,
          "label": rec.label,
          "expire_time": snap.get("expire_time") or rec.expire_time,
          "size_bytes": snap.get("size_bytes") if snap.get("size_bytes") is not None else rec.size_bytes,
          "auto": rec.auto,
          "seconds_until_expiry": seconds_until_expiry(
              snap.get("expire_time") or rec.expire_time
          ),
      })
    self.write_snapshots(tool_context.state, kept)
    binding = self.read_binding(tool_context.state)
    return {
        "ok": True,
        "sandbox_name": binding.name if binding else None,
        "snapshots": live,
        "count": len(live),
    }

  async def restore_session(
      self, tool_context: Any, *, label_or_name: str
  ) -> dict[str, Any]:
    """Delete-then-restore under the session lock (never two live sandboxes)."""
    key = self.session_key_from_context(tool_context)
    async with self._lock_for(key):
      snap_rec = self.find_snapshot(tool_context.state, label_or_name)
      if snap_rec is None:
        return {
            "ok": False,
            "restored": False,
            "reason": "snapshot_not_in_session",
            "detail": (
                f"{label_or_name!r} is not a snapshot of this session. "
                "Cross-session restore is not allowed."
            ),
        }
      # Confirm snapshot is alive *before* deleting the sandbox.
      try:
        await asyncio.to_thread(self._client.get_snapshot, name=snap_rec.name)
      except SandboxNotFound:
        return {
            "ok": False,
            "restored": False,
            "reason": "snapshot_not_found",
            "snapshot_name": snap_rec.name,
            "detail": "Snapshot is gone; the live sandbox was left untouched.",
        }

      old = self._cache.pop(key, None) or self.read_binding(tool_context.state)
      old_name = old.name if old else None
      if old is not None:
        try:
          await asyncio.to_thread(self._client.delete, name=old.name)
        except SandboxNotFound:
          pass
        self.clear_binding(tool_context.state)
        # Keep history of the deleted name.
        if old:
          history = []
          if hasattr(tool_context.state, "get"):
            hist_raw = tool_context.state.get(STATE_SANDBOX_HISTORY_KEY) or []
          else:
            hist_raw = []
          if isinstance(hist_raw, list):
            history = list(hist_raw)
          history.append(old.name)
          tool_context.state[STATE_SANDBOX_HISTORY_KEY] = history

      t0 = time.monotonic()
      try:
        created = await self._create(
            key, from_snapshot=snap_rec.name, restored_from=snap_rec.name
        )
      except SandboxRestoreUnusable as exc:
        # The old sandbox is already gone, so leave the session with a working
        # (empty) one rather than unbound or bound to something unusable.
        fallback = await self._create(key)
        self._cache[key] = fallback
        self.write_binding(tool_context.state, fallback)
        self._last_used[key] = time.monotonic()
        return {
            "ok": False,
            "restored": False,
            "reason": "restore_unusable",
            "detail": (
                f"{exc} The session was given a fresh empty sandbox instead; "
                "the snapshot is still there and can be retried."
            ),
            "sandbox_name": fallback.name,
            "previous_sandbox_name": old_name,
            "snapshot_name": snap_rec.name,
            "label": snap_rec.label,
            "restore_seconds": round(time.monotonic() - t0, 3),
        }
      self._cache[key] = created
      self.write_binding(tool_context.state, created)
      self._last_used[key] = time.monotonic()
      return {
          "ok": True,
          "restored": True,
          "sandbox_name": created.name,
          "previous_sandbox_name": old_name,
          "restored_from": snap_rec.name,
          "label": snap_rec.label,
          "restore_seconds": round(time.monotonic() - t0, 3),
      }

  async def delete_session_snapshot(
      self, tool_context: Any, *, label_or_name: str
  ) -> dict[str, Any]:
    snap_rec = self.find_snapshot(tool_context.state, label_or_name)
    if snap_rec is None:
      return {"ok": False, "deleted": False, "reason": "snapshot_not_in_session"}
    try:
      await asyncio.to_thread(self._client.delete_snapshot, name=snap_rec.name)
    except SandboxNotFound:
      pass
    kept = [r for r in self.read_snapshots(tool_context.state) if r.name != snap_rec.name]
    self.write_snapshots(tool_context.state, kept)
    return {
        "ok": True,
        "deleted": True,
        "snapshot_name": snap_rec.name,
        "label": snap_rec.label,
    }

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
      binding = self._cache.get(key)
      if binding is None:
        continue
      if self._settings.auto_snapshot_on_idle_delete:
        try:
          display = self.snapshot_display_name(key, f"auto-idle-{int(time.time())}")
          await self._ensure_running_for_snapshot(binding.name)
          await asyncio.to_thread(
              self._client.create_snapshot,
              source_sandbox_name=binding.name,
              display_name=display,
              ttl=self._settings.snapshot_ttl,
              wait_for_completion=True,
          )
        except SandboxNotFound:
          pass
        except Exception as exc:  # noqa: BLE001
          logger.warning(
              "Auto-snapshot before idle delete failed for %s: %s", binding.name, exc
          )
      self._cache.pop(key, None)
      self._last_used.pop(key, None)
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
