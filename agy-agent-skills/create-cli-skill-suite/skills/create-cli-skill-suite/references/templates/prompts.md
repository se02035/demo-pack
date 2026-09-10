# Sample prompts

The host agent must still run onboarding in `SKILL.md` (CLI, auth, target
env) before any API call, and apply [limitations.md](limitations.md).

If invocation is unclear, run `acme-widgets help` first (no API client).

- Show me how to invoke the CLI (`acme-widgets help`); do not call the API yet.
- Onboard me to Acme Widgets in environment ENV, using the documented auth.
  Do not ask me to paste a token.
- List widgets, then delete NAME with `--yes` when I confirm.
