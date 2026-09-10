# Process (gated)

The implementing agent **stops** at each gate. No product files and no live
probes until the scope brief, spec sheet, identity, and target environment are
accepted or stated.

## Gates

1. **Seed** — purpose, docs, constraints already in the prompt. Do not re-ask.
   No secrets. Do not read ambient vendor-CLI config.
1a. **Grill** — [discovery.md](discovery.md). Scope brief. User confirms.
1b. **Spec sheet** — [spec.md](spec.md). Names, descriptions, split. User confirms.
2. **Verification plan** — matrix (columns in [verification.md](verification.md)).
   Show it, then probe. Explicit accept is **not** required for this step.
3. **Live probes** — SDK-first. Complete the matrix (complete ≠ all green).
   Issue ids on failures. Evidence gitignored.
4. **Implementation plan** — proven calls → CLI; failures → known issues.
   Re-propose split if probes revealed another system. **User accepts. Stop.**
5. **TDD + package** — [tdd.md](tdd.md), [packaging.md](packaging.md).
6. **Skills + README** — npx-safe folders. [known-issues.md](known-issues.md),
   [prerequisites.md](prerequisites.md). Fail closed if CLI missing.
7. **CLI smoke** — packaged CLI, confirm-flag delete, cleanup prefix.

If the user wants MCP-only or prompt-only: **stop**. This factory produces
Python CLI + Agent Skills suites only.

## Wrong-tool check (first)

If there is no remote API to wrap (only an MCP server, only a prompt, only
local files), tell the user this skill is the wrong tool and stop.
