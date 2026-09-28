"""ADK agent: one shell sandbox per session."""

from __future__ import annotations

from google.adk import Agent
from google.adk.apps import App

from sandbox_agent.config import get_settings
from sandbox_agent.prompts import INSTRUCTION
from sandbox_agent.sandbox.plugin import SandboxLifecyclePlugin
from sandbox_agent.tools import build_tools

_settings = get_settings()

root_agent = Agent(
    name="sandbox_agent",
    model=_settings.model,
    description=(
        "Runs shell commands and file operations in a Gemini Enterprise "
        "Agent Platform sandbox dedicated to the current ADK session."
    ),
    instruction=INSTRUCTION,
    tools=build_tools(),
)

app = App(
    name="sandbox_agent",
    root_agent=root_agent,
    plugins=[SandboxLifecyclePlugin()],
)
