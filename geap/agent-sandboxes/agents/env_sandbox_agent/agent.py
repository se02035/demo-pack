"""ADK agent: EnvironmentToolset + session-scoped Agent Platform sandboxes."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.apps import App
from google.adk.tools.environment import EnvironmentToolset

from env_sandbox_agent.environment import SessionBindPlugin, SessionSandboxEnvironment

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

_MODEL = os.environ.get("SANDBOX_AGENT_MODEL", "gemini-3.8-flash")
_MAX_CHARS = int(os.environ.get("SANDBOX_MAX_OUTPUT_CHARS", "20000"))

INSTRUCTION = """\
You are a demo agent that uses ADK EnvironmentToolset tools backed by
Gemini Enterprise Agent Platform sandboxes.

Each conversation session gets two isolated sandboxes:
- shell_* tools: bash + files on sandbox-<session_id>-shell
- code_* tools: Python source via code_Execute on sandbox-<session_id>-code

Rules:
- Use shell_WriteFile / shell_ReadFile / shell_EditFile for shell-sandbox files.
- Use shell_Execute for bash commands (including `python3 script.py` in the
  shell image when needed).
- Use code_Execute with a Python program as the `command` argument (not bash).
- Use code_WriteFile / code_ReadFile for the code-execution sandbox filesystem.
- Never claim a file from another session exists; sandboxes are not shared.
"""

root_agent = Agent(
    name="env_sandbox_agent",
    model=_MODEL,
    description=(
        "Demonstrates a custom BaseEnvironment on EnvironmentToolset with "
        "one shell sandbox and one code sandbox per ADK session."
    ),
    instruction=INSTRUCTION,
    tools=[
        EnvironmentToolset(
            environment=SessionSandboxEnvironment("shell"),
            tool_name_prefix="shell",
            max_output_chars=_MAX_CHARS,
        ),
        EnvironmentToolset(
            environment=SessionSandboxEnvironment("code"),
            tool_name_prefix="code",
            max_output_chars=_MAX_CHARS,
        ),
    ],
)

app = App(
    name="env_sandbox_agent",
    root_agent=root_agent,
    plugins=[SessionBindPlugin()],
)
