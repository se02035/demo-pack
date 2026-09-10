# Discovery (grill for scope)

Same posture as agy **`/grill-me`**: invert the session. Interrogate the **goal**
until leftover ambiguity would not change the ship-bar, skill split, or
verification matrix. Then present a **scope brief** and wait.

This factory **implements** the interview (Cursor or agy). In agy the user may
also run `/grill-me`; still fill every dimension below that `/grill-me` left
blank.

**No probes, no generated files, no SDK install** during this phase.

Fill [templates/scope-brief.md](templates/scope-brief.md) and show it.

## How to grill

- **One question at a time** (or a short related pair). Not a wall.
- Ask the gap whose answer would **most change** the suite (systems, mutate vs
  read, split, auth).
- **Recommend an answer** from what they already said; agreeing should be easy.
  Infer freely. Do not invent secrets or environment ids.
- **Do not re-ask** facts already in the prompt, linked docs, or earlier answers.
- Stop when leftover questions would not change the matrix or split. Do not
  grill forever.
- User can object, skip, or say “you decide”; record that on the brief.

## Scope dimensions (skip any already known)

| Dimension | Why it matters |
|---|---|
| **Goal** | Who uses it, what job, when to invoke (feeds `description`) |
| **Ship-bar** | Actions that must work or become issue ids. Success example prompts |
| **Out of scope** | Adjacent work to refuse so the agent does not invent it |
| **Remote systems** | One API vs several; control plane vs data plane (drives split) |
| **Read vs mutate vs long-running** | What may bill or wait |
| **Auth / identity** | Mechanism names, not secrets |
| **Target environment(s)** | Account, region, cluster, workspace, or equivalent |
| **Constraints** | Must-use client, must-not vendor CLI, MCP vs HTTP, docs/OpenAPI/proto URLs |
| **Existing vs create** | Named production resources vs factory-prefixed smokes only |

## Scope brief (user confirms)

One short artifact:

- Goal (1–3 sentences)
- In scope / out of scope
- Ship-bar feature list
- Systems involved
- Auth + target env (or “still unknown — ask before probes”)
- Constraints
- Suggested split (preview only; official names are the spec sheet)

**Do not start live probes** until the scope brief is accepted, identity and
target env are stated (grill if missing), and the spec sheet is accepted.
