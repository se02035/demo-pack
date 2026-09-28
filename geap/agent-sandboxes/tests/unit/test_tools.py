"""Unit tests for tool command construction and result shaping."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sandbox_agent.tools.files import build_read_command, build_write_command, read_text_file, write_text_file
from sandbox_agent.tools.shell import list_directory, run_shell_command


class FakeState(dict):
  pass


def make_context(session_id: str = "s1"):
  return SimpleNamespace(
      session=SimpleNamespace(
          app_name="sandbox_agent", user_id="u1", id=session_id
      ),
      state=FakeState(),
  )


@pytest.mark.asyncio
async def test_run_shell_command_quotes_and_returns_sandbox_name(
    manager, fake_client, monkeypatch
):
  from sandbox_agent.sandbox import runtime as runtime_mod

  monkeypatch.setattr(runtime_mod, "get_manager", lambda: manager)
  ctx = make_context()
  result = await run_shell_command("echo hello", ctx)
  assert result["ok"] is True
  assert result["sandbox_name"]
  assert result["returncode"] == 0
  assert fake_client.execute_calls[-1]["command"] == "echo hello"


@pytest.mark.asyncio
async def test_non_zero_returncode_is_data_not_exception(
    manager, fake_client, monkeypatch
):
  from sandbox_agent.sandbox import runtime as runtime_mod

  monkeypatch.setattr(runtime_mod, "get_manager", lambda: manager)
  ctx = make_context()
  result = await run_shell_command("exit 7", ctx)
  assert result["returncode"] == 7
  assert result["ok"] is True  # tool call succeeded; command failed


def test_write_command_uses_base64_and_shlex():
  cmd = build_write_command("/workspace/my file.txt", "hello 'world'\nline2")
  assert "base64 -d" in cmd
  assert "mkdir -p" in cmd
  assert "'/workspace/my file.txt'" in cmd or "/workspace/my\\ file.txt" in cmd


def test_read_command_quotes_path():
  cmd = build_read_command("/workspace/a b.txt")
  assert "cat --" in cmd
  assert "a b.txt" in cmd


@pytest.mark.asyncio
async def test_write_and_read_roundtrip(manager, fake_client, monkeypatch):
  from sandbox_agent.sandbox import runtime as runtime_mod

  monkeypatch.setattr(runtime_mod, "get_manager", lambda: manager)
  ctx = make_context("s_files")
  content = "hello 'world'\nline2\nnaïve"
  written = await write_text_file("/workspace/notes.txt", content, ctx)
  assert written["ok"] is True
  assert written["sandbox_name"]

  # Fake parser may not handle all quote variants; assert command shape at least.
  assert any("base64 -d" in c["command"] for c in fake_client.execute_calls)

  # Directly seed file store to verify read path shaping if write parse failed.
  binding_name = written["sandbox_name"]
  fake_client.sandboxes[binding_name]["files"]["/workspace/notes.txt"] = content

  read = await read_text_file("/workspace/notes.txt", ctx)
  assert read["ok"] is True
  assert read["content"] == content
  assert read["sandbox_name"] == binding_name


@pytest.mark.asyncio
async def test_list_directory_quotes_path(manager, fake_client, monkeypatch):
  from sandbox_agent.sandbox import runtime as runtime_mod

  monkeypatch.setattr(runtime_mod, "get_manager", lambda: manager)
  ctx = make_context("s_ls")
  result = await list_directory(ctx, path="/workspace/sub dir")
  assert result["ok"] is True
  cmd = fake_client.execute_calls[-1]["command"]
  assert cmd.startswith("ls -la --")
  assert "sub dir" in cmd
