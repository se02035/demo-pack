"""Assemble the agent's FunctionTool list."""

from __future__ import annotations

from google.adk.tools import FunctionTool

from sandbox_agent.tools.files import read_text_file, write_text_file
from sandbox_agent.tools.info import end_sandbox_session, get_sandbox_info
from sandbox_agent.tools.lifecycle import (
    delete_snapshot,
    get_sandbox_lifecycle,
    list_snapshots,
    pause_sandbox,
    restore_snapshot,
    resume_sandbox,
    snapshot_sandbox,
)
from sandbox_agent.tools.shell import list_directory, run_shell_command


def build_tools() -> list[FunctionTool]:
  return [
      FunctionTool(get_sandbox_info),
      FunctionTool(get_sandbox_lifecycle),
      FunctionTool(run_shell_command),
      FunctionTool(list_directory),
      FunctionTool(write_text_file),
      FunctionTool(read_text_file),
      FunctionTool(pause_sandbox),
      FunctionTool(resume_sandbox),
      FunctionTool(snapshot_sandbox),
      FunctionTool(list_snapshots),
      FunctionTool(restore_snapshot),
      FunctionTool(delete_snapshot),
      FunctionTool(end_sandbox_session),
  ]
