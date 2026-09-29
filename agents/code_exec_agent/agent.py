"""ADK agent: one Agent Platform Code Execution sandbox per session.

Uses ADK's built-in ``AgentEngineSandboxCodeExecutor``. Omitting
``sandbox_resource_name`` makes the executor create (and reuse) a sandbox per
ADK session, stored under
``session.state["_code_execution_context"]["sandbox_name"]``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)

# ADK also loads agents/<name>/.env; load here so importing the module for
# discovery / tests picks up a local .env when present.
load_dotenv(Path(__file__).resolve().parent / ".env")

_RUNTIME = os.environ.get("SANDBOX_RUNTIME_NAME", "").strip()
_PLACEHOLDER = not _RUNTIME or _RUNTIME.endswith("/RUNTIME_ID")

# gemini-3.8-flash returns MALFORMED_FUNCTION_CALL when prompted for the
# documented ```tool_code fences. Restrict delimiters to ```python so ADK
# also replays prior code with that fence (its default first delimiter is
# tool_code).
_CODE_BLOCK_DELIMITERS = [("```python\n", "\n```")]

_executor_kwargs: dict = {
    "code_block_delimiters": _CODE_BLOCK_DELIMITERS,
}
if not _PLACEHOLDER:
  _executor_kwargs["agent_engine_resource_name"] = _RUNTIME

root_agent = Agent(
    name="code_exec_agent",
    model=os.environ.get("CODE_EXEC_AGENT_MODEL", "gemini-3.8-flash"),
    description=(
        "Runs Python in a Gemini Enterprise Agent Platform Code Execution "
        "sandbox dedicated to the current ADK session."
    ),
    instruction=(
        "Answer by replying with Python code in a ```python fenced block; it "
        "will be executed for you and the output shown back. Variables "
        "persist between code blocks within this conversation. Always print "
        "results. If code execution fails because no runtime is configured, "
        "tell the user to set SANDBOX_RUNTIME_NAME in "
        "agents/code_exec_agent/.env."
    ),
    code_executor=AgentEngineSandboxCodeExecutor(**_executor_kwargs),
)
