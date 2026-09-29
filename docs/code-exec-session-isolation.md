# Code-execution session isolation

Minimal ADK agent (`code_exec_agent`) that uses Google's built-in
[`AgentEngineSandboxCodeExecutor`](https://adk.dev/integrations/code-exec-agent-runtime/)
to prove **one Code Execution sandbox per ADK session**.

Lifecycle management (pause, TTL, snapshots) is out of scope here. The sibling
`sandbox_agent` covers Shell sandboxes and lifecycle tooling.

## How the executor picks a sandbox

Construct the executor with `agent_engine_resource_name` (your Agent Platform
runtime) and **omit** `sandbox_resource_name`:

```python
code_executor=AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=os.environ["SANDBOX_RUNTIME_NAME"],
    code_block_delimiters=[("```python\n", "\n```")],
)
```

On each code run ADK passes the current session into the executor. The
executor:

1. Reads `session.state["_code_execution_context"]["sandbox_name"]`.
2. Creates a new Code Execution sandbox under the runtime if that key is
   missing or the sandbox is gone / not `STATE_RUNNING`.
3. Writes the name back into `_code_execution_context` (ADK persists that via
   a state delta).

The executor object is shared across sessions; the sandbox binding is
per-session. Passing a static `sandbox_resource_name` instead shares one
sandbox across every session — ADK warns about that.

**Note:** the executor also sets a top-level `state["sandbox_name"]`, but that
write is not part of ADK's state delta, so it is **not** what survives a
session reload. Always read the nested key.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT
export SANDBOX_LOCATION=us-central1
# ADC or a service-account key with roles/aiplatform.user
gcloud auth application-default login
gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_PROJECT"

python scripts/bootstrap_runtime.py   # once; prints SANDBOX_RUNTIME_NAME
```

Copy `agents/code_exec_agent/.env.example` to `agents/code_exec_agent/.env`
and paste the printed runtime name (and your project id). Do not commit `.env`.

## Run the Playground

```bash
source .venv/bin/activate
cd agents
adk web --port 8766 --no-reload --session_service_uri memory://
```

Open the UI, select **code_exec_agent**, then:

| Session | Prompt | Expect |
| --- | --- | --- |
| A | *Set marker = 'alpha' and print it.* | `alpha` |
| A | *Print marker again.* | `alpha` (same sandbox) |
| B (New Session) | *Print marker.* | `NameError` / not defined |
| B | *Set marker = 'beta' and print it.* | `beta` |
| A | *Print marker.* | still `alpha` |

In each session's **State** tab, check
`_code_execution_context.sandbox_name`. The two sessions must show different
resource names.

Keep prompts short. Asking the model to "not define" a missing variable can
send it on a long exploration of the sandbox internals.

### Model / fencing note

With `gemini-3.8-flash`, prompting for the documented ```` ```tool_code ````
fences yields `MALFORMED_FUNCTION_CALL` (reproduced even without ADK). This
agent asks for ```` ```python ```` fences and restricts the executor's
`code_block_delimiters` accordingly. Older models such as `gemini-2.5-flash`
accept `tool_code` as documented.

## Scripted proof

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT
export SANDBOX_RUNTIME_NAME=projects/.../reasoningEngines/...
python scripts/prove_code_exec_isolation.py
```

The script drives two sessions through the ADK Runner, asserts distinct
sandbox names + marker isolation, then runs a **filesystem** check: each
sandbox writes a unique token under several writable paths and searches for
the other sandbox's token (expect 0 hits either way). It deletes both
sandboxes unless you pass `--keep`.

## Cleanup

Executor-created sandboxes use `display_name="default_sandbox"` and a
**1-year TTL**, so they are invisible to `reap_sandboxes.py`'s `adk-demo`
prefix. Prefer the proof script's automatic delete, or delete by exact name
from the State tab / script output:

```bash
# Example — substitute the full resource names from session state
python -c "
import agentplatform, os
c = agentplatform.Client(project=os.environ['GOOGLE_CLOUD_PROJECT'],
                         location=os.environ.get('SANDBOX_LOCATION','us-central1'))
for name in ['SANDBOX_A', 'SANDBOX_B']:
    c.sandboxes.delete(name=name)
"
```

## Resuming a session

If the **session store** persists (SQLite / Agent Platform Sessions) and the
sandbox is still `STATE_RUNNING`, a later process that resumes the same
session id reuses the same sandbox (Python variables and files survive).
`memory://` forgets sessions on restart, so a new session gets a new sandbox.

You can also pre-bind a sandbox when creating a session:

```python
await session_service.create_session(
    ...,
    state={"sandbox_name": existing_sandbox_resource_name},
)
```

Isolation then depends on who sets that key — seed two sessions with the same
name and they share a sandbox.

## What this does not show

- Shell sandboxes / `execute_bash` (see `sandbox_agent`)
- Pause / resume / snapshot lifecycle (platform defects; see
  `docs/sandbox-learnings.md`)
- Deploying the agent to Agent Engine
