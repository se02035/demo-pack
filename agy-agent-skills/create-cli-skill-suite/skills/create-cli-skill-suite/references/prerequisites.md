# Prerequisite gate (generated skills)

Every generated skill must know **what must be true before each user
interaction**, and must **ask and stop** if anything required is missing.
Mandatory before **long-running** work: async create/deploy, wait-until-ready,
anything using the 300s wait caps, anything that **bills while it exists**.

**Do not guess. Do not read ambient vendor-CLI config.**

Copy the Onboarding and Per-action sections from
[templates/SKILL.md](templates/SKILL.md) and fill them from the verification
matrix `requires:` column.

## What to collect (adapt to the product)

- **Identity / auth** — mechanism probes proved. Confirm it exists; never print
  tokens; never ask for key files.
- **Target environment** — account, project, org, region, cluster, namespace,
  workspace, or equivalent. User-stated. **Required CLI flags. No argparse
  defaults** that pick an env.
- **Per-action extras** — extra principal, image/URI, resource to reuse,
  confirm flag on delete, TTL, or anything `requires:` listed for that command.

## Agent behavior

1. **Onboarding** in `SKILL.md` — CLI installed, harness vs API auth if both
   exist, target env.
2. **Per-action table** — intent → required fields → cheap preflight
   (`help`/`--version` with no credentials; auth-presence check that does not
   print secrets) → only then the slow call.
3. If anything required is missing: **ask once**, show a sample prompt, **do
   not invoke the CLI or API** until the user answers.
4. Reuse resource names already in this conversation. Do not create a new host
   resource per turn without asking.
5. Cheap checks first. Never start a wait/create/deploy to discover that
   environment or identity was missing.

CLI required flags are a **backstop**. The skill’s primary duty is still ask
and stop.

Runtime flow: onboarding → per-action requires → cheap preflight → issue gate
→ long or mutating call.
