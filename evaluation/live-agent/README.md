# Live workflow demo

A local voice demo of a short care-team phone call, built with the Agent Development Kit (ADK). You talk to it in the ADK web UI. The same conversation can be scored later with the included live evaluation set.

Copy `live_workflow/.env.example` to `live_workflow/.env` and fill in `GOOGLE_API_KEY` and `LIVE_MODEL` locally. That file stays uncommitted. Enterprise mode is off, so ADK uses the key in `GOOGLE_API_KEY`.

## What it does

The caller is treated as a patient named John Doe. The call has three stages, always in this order:

1. **Greet and confirm the name.** The agent introduces itself as Sam and checks that it is speaking with John Doe before sharing anything else.
2. **Verify the date of birth.** It asks for the date, reads it back, then checks it. The matching record is July 12th, 1985 (`1985-07-12`). That check is mocked in code, not looked up from a real system.
3. **Share the visit and wrap up.** After identity is verified, it tells the caller about an appointment on Tuesday, June 16th at 3 PM with Dr. Example, answers a short follow-up, and ends with "Goodbye."

Lines that walk the happy path:

- "Hi, yes, this is John Doe"
- "My date of birth is July 12th, 1985"
- "No, no other questions. Thanks!"

## How it works

One ADK `Workflow` is the root agent. It keeps a single live voice session for the whole call. You hear one conversation. Control moves from stage to stage inside that session.

Each stage is an ADK `Agent` with `mode='task'`. A task agent runs its own turn loop until it decides the stage is finished. The next stage does not start before that. The greeter and the date-of-birth agent each return a small typed result (`GreeterOutput`, `DobOutput`) that the workflow passes forward. The last stage has no typed output. It just closes the call.

The date-of-birth agent calls the `validate_date_of_birth` tool only after it has read the date back and the caller has confirmed it. The tool compares the date, in `YYYY-MM-DD` form, with `1985-07-12` and stores whether it matched.

`adk web` serves a local dev UI. Pick `live_workflow` and start a Live session to talk to the workflow.

Evaluation replays the same path without a person on the microphone. `live_workflow.evalset.json` describes one case, `verified_patient_scenario`: an audio user simulator plays John Doe from a conversation plan. `test_config.json` scores the result with rubrics for identity-before-details, the validation tool call, stage order, the appointment details, and a goodbye.

## Core components

| Piece | Role |
| --- | --- |
| `Workflow` and `START` | Graph that runs the three stages in order on one live session |
| `greeter_agent` | Task agent that confirms the caller's name |
| `dob_verifier_agent` | Task agent that captures and checks the date of birth |
| `goals_agent` | Task agent that delivers the appointment and ends the call |
| `validate_date_of_birth` | Mock tool used only after the date is read back |
| `LIVE_MODEL` in `.env` | Live model id used by all three agents |
| `GOOGLE_API_KEY` in `.env` | AI Studio key. Enterprise mode is off, so this is the Gemini API, not Agent Platform |
| `adk web` | Local UI for a Live session |
| `live_workflow.evalset.json` | Audio user-simulator case for the verified-patient call |
| `test_config.json` | Rubric thresholds for that eval |

## Run

From this directory:

```bash
uv sync
uv run adk web
```

Open the URL printed in the terminal (usually `http://127.0.0.1:8000`), select `live_workflow`, and start a Live session.

To score the call with the audio simulator:

```bash
uv run adk eval \
  live_workflow \
  live_workflow/live_workflow.evalset.json \
  --config_file_path live_workflow/test_config.json
```

That eval calls the Live API and a text-to-speech model. It can take several minutes.
