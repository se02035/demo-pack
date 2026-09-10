# Auth in generated skills

How **generated** skills document credentials. Runtime ask-and-stop lives in
[prerequisites.md](prerequisites.md).

## Harness vs API

Agy (or any harness) sign-in authenticates the **agent session**. It is **not**
the product API credential. If both exist, say so in onboarding. `help` working
does not mean the API will accept calls.

## What to document

- The **mechanism** probes proved (env-based SDK credentials, OAuth, API-key
  **environment variable name**, extra principal, or product equivalent).
- How to confirm it **without printing secrets** (presence check, not dump).
- Caller-must-have permissions (from probes or vendor docs that probes did not
  disprove). Do not grant or change policy unless that is the API under skill.
  Do not probe policy unless the user asks.

## Never

- Paste tokens, key files, or secret values in chat, SKILL.md, prompts, or
  `help` examples.
- Log credential headers.
- Bake account, principal, or operation ids into argparse defaults.
- Default an extra principal required for some commands — **ask**.
- Treat ambient vendor-CLI config (default account, last-used region, current
  kube context) as the user stating values.

## Control plane vs data plane

If probes show control-plane credentials fail on a data plane that expects a
different identity, that is an issue id **and** a required extra on that
command. Ask before the long call.
