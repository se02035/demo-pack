# Learnings (product-agnostic)

Generic rules for every suite this factory produces. Do not require opening
another skill. Do not name a vendor API, region, client class, or issue id from
a suite already in this repo.

## Process

- Grill for scope, then infer-and-confirm the spec sheet, before probes.
- Live-verify with throwaway SDK probes **before** the shipped CLI.
- Gitignore `_probe_*` / `_smoke_*` / `*-api-evidence.md`.
- User accepts the **post-verification** implementation plan before packaging.
- Re-smoke the packaged CLI. Cleanup leftover resources with a stable prefix.
- Cap waits (default 300s). Missing completion flag = in progress if probes
  showed that. Terminal failure: stop that kind; print the error/operation
  object; do not extend the wait hoping.
- Parallelize independent probes.

## Docs vs live

- Live API wins. Agent contract = limitations + issue ids. Evidence is not a
  skill and is gitignored.
- Samples and docs can use the wrong client, API version, or request body.
  Pin the live client + version; ban what probes disproved.
- Print the API resource name the backend understands, not a wrapper display
  name. Returned ids may differ in format from what the user typed; do not
  rewrite them into a different resource.
- SDK dumps can hide/encode payloads; decode the live bytes/JSON.
- Product logs/audit may omit the real error; surface the object probes
  returned instead of “check the vendor logs.”
- HTTP 200 / create accepted / list visible ≠ ready when there is a state
  machine. Poll get until terminal. Do not use an SDK auto-wait if it hung.
- On terminal failure: stop **that kind**; continue other matrix rows; do not
  retry the same kind/environment in a loop.

## Auth / access / safety

- Harness login is **not** the product API credential. Call out both when both
  exist. See [auth.md](auth.md).
- Prefer env-based / official-SDK auth; never pasted tokens or key files; never
  log credential headers. Confirm auth without printing the token.
- Never bake account, principal, or operation ids into SKILL.md, prompts,
  argparse defaults, or `help` examples.
- Extra principals required for some commands still have **no default** — ask.
- Prerequisite gate: [prerequisites.md](prerequisites.md).
- Do not grant or change access policy (unless that is the API) and do not
  probe policy unless asked. Document caller-must-have permissions.
- Control-plane credentials may not work on a data plane that expects a
  different identity. Treat that as an issue **and** a required extra.
- No silent environment/endpoint failover. User-stated target env.
- Explicit confirm flag on deletes. Warn if resources bill while they exist.
  Do not attach smokes to unnamed existing production resources.

## Packaging / Antigravity / npx

See [packaging.md](packaging.md).

- Unique CLI name; `python3 -m pkg` fallback. Missing CLI → **fail closed**;
  print pip install; do not invent curl or a vendor CLI probes did not find.
- `help` / `--version` must not construct the SDK client.
- No shims. npx copies **only** the skill directory.
- Duplicate limitations/issues into each skill.
- Agy loads `<launch-cwd>/.agents/skills/`. Restart `agy` after npx. Pip into
  the same `python3` the harness uses.
- JSON stdout; warnings on stderr. CLI `--version` matches `metadata.version`.
- Progressive disclosure: lean `SKILL.md`; API mapping in `references/`.

## Client-side refuses

- Kind/precondition checks citing issue ids, not only HTTP error text.
- Insist ≠ override, except rows that say “only if they explicitly agree.”
