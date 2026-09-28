"""Integration fixtures for live sandbox / api_server tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "agents"


def _has_live_credentials() -> bool:
  if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
    return False
  runtime = os.environ.get("SANDBOX_RUNTIME_NAME", "")
  if not runtime or runtime.endswith("/RUNTIME_ID"):
    return False
  # ADC present?
  adc = Path.home() / ".config/gcloud/application_default_credentials.json"
  if adc.exists():
    return True
  return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))


requires_live = pytest.mark.skipif(
    not _has_live_credentials(),
    reason="Needs ADC + GOOGLE_CLOUD_PROJECT + real SANDBOX_RUNTIME_NAME",
)


def _free_port() -> int:
  with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def live_settings():
  if not _has_live_credentials():
    pytest.skip("live credentials not configured")
  os.environ.setdefault("SANDBOX_LOCATION", "us-central1")
  os.environ.setdefault("SANDBOX_DISPLAY_NAME_PREFIX", "adk-demo")
  from sandbox_agent.config import get_settings, require_runtime_configured

  get_settings.cache_clear()
  return require_runtime_configured()


@pytest.fixture(scope="session")
def sandbox_reaper(live_settings):
  """Best-effort cleanup of adk-demo sandboxes created during the session."""
  import agentplatform

  client = agentplatform.Client(
      project=live_settings.project, location=live_settings.sandbox_location
  )
  prefix = live_settings.display_name_prefix
  before = {
      s.name
      for s in client.sandboxes.list(name=live_settings.runtime_name)
      if (s.display_name or "").startswith(prefix)
  }
  yield client
  after = list(client.sandboxes.list(name=live_settings.runtime_name))
  for sandbox in after:
    display = sandbox.display_name or ""
    if display.startswith(prefix) and sandbox.name not in before:
      try:
        client.sandboxes.delete(name=sandbox.name)
      except Exception as exc:  # noqa: BLE001
        print(f"reaper failed for {sandbox.name}: {exc}", file=sys.stderr)


@pytest.fixture(scope="session")
def api_server(live_settings):
  port = _free_port()
  env = os.environ.copy()
  env["PYTHONPATH"] = str(AGENTS) + os.pathsep + env.get("PYTHONPATH", "")
  proc = subprocess.Popen(
      [
          sys.executable,
          "-m",
          "google.adk.cli",
          "api_server",
          "--port",
          str(port),
          "--host",
          "127.0.0.1",
          "--no-reload",
      ],
      cwd=str(AGENTS),
      env=env,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
  )
  import httpx

  base = f"http://127.0.0.1:{port}"
  deadline = time.time() + 90
  last_err = None
  while time.time() < deadline:
    if proc.poll() is not None:
      out = proc.stdout.read() if proc.stdout else ""
      pytest.fail(f"api_server exited early: {out}")
    try:
      r = httpx.get(f"{base}/list-apps", timeout=2.0)
      if r.status_code == 200 and "sandbox_agent" in r.json():
        break
    except Exception as exc:  # noqa: BLE001
      last_err = exc
    time.sleep(0.5)
  else:
    proc.terminate()
    out = proc.stdout.read() if proc.stdout else ""
    pytest.fail(f"api_server did not become ready: {last_err}\n{out}")

  yield base
  proc.terminate()
  try:
    proc.wait(timeout=10)
  except subprocess.TimeoutExpired:
    proc.kill()
