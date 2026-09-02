---
name: gcp-agent-registry
description: >-
  Search, list, create, update, download, and delete skills in GCP Agent
  Registry (v1alpha). Covers keyword and semantic skills:search, first-party
  (cloud.google.com, discoveryengine.googleapis.com) and third-party (private-*)
  skills, ADC auth, revisions, and known API/doc mismatches. Use when the user
  mentions Agent Registry, skills:search, SKILL.md upload, semantic or keyword
  skill search, or CRUD on registry skills.
license: Apache-2.0
compatibility: >-
  Requires Python 3.10+, Google Cloud SDK (gcloud) with Application Default
  Credentials, and network access to agentregistry.googleapis.com. Use
  scripts/registry.py (v1alpha REST). The official google-cloud-agentregistry
  Python client is v1-only and has no Skills API.
metadata:
  version: "1.0"
  source: ../agent-registry-skill-search.md
---

# GCP Agent Registry

Operate GCP Agent Registry **skills** over REST (`v1alpha` only). Prefer the bundled
script over inventing curl. Public Google docs conflict with the live API — when they
do, follow this skill and tell the user, using [references/issues.md](references/issues.md).

Do not register this harness skill into Agent Registry unless the user asks. Do not
delete `private-my-custom-skill` or other skills the user did not name.

## Onboarding (required before any API call)

Collect from the user. **Do not guess** project, location, or credentials.

1. `PROJECT_ID` — GCP project that hosts the registry.
2. `LOCATION` — `eu`, `us`, or `global`. These are **independent catalogs**.
3. Auth — **Application Default Credentials** only:
   ```bash
   gcloud auth application-default login
   gcloud auth application-default set-quota-project PROJECT_ID
   ```
   Do not ask for service-account JSON keys or for the user to paste access tokens
   into chat.

Verify:

```bash
gcloud auth application-default print-access-token >/dev/null
python3 scripts/registry.py --project PROJECT_ID --location LOCATION list --page-size 1
```

If the user wants **semantic** search and `LOCATION` is not `eu`, **stop**. Surface
Issue 1 from [references/issues.md](references/issues.md) before calling the API.

IAM: viewer to search; `roles/agentregistry.user` to create/update/delete.

## Hard rules

- API host: `https://agentregistry.googleapis.com/v1alpha`. `v1` has no skills.
- Search wire param is `searchString` (not `query`). Always send `searchType=KEYWORD`
  or `searchType=SEMANTIC`.
- Default `filter=state=ACTIVE` on list and search unless the user wants retired skills.
- Third-party IDs are prefixed: creating `foo` yields `private-foo`. Use the prefixed
  ID on every later call.
- First-party prefixes: `cloud.google.com-`, `discoveryengine.googleapis.com-`.
- Filter publishers via searchString using `name:private*` (third-party), `name:cloud*`
  (Google Cloud), or `name:discoveryengine*` (Gemini Enterprise) — publisher filter is
  broken (Issue 4). Never use `name:cloud.google.com*` as dots break wildcard tokenization.
- Keyword search does **not** read `SKILL.md` body. Unqualified keyword also skips
  frontmatter (Issue 17). Semantic search indexes the body, in `eu` only.
- Create as `TARGET_STATE_DRAFT`, then set `defaultRevision`, then `TARGET_STATE_ACTIVE`
  (Issue 7). Never send `TARGET_STATE_ACTIVE` on create.
- Delete every revision (poll LROs) before deleting the skill container (Issue 16).

## Issue gate

Before executing an action, match it in [references/issues.md](references/issues.md).
If it is a known mismatch, **tell the user first** (doc claim vs actual vs workaround),
then proceed only with the workaround or after they confirm.

| User asks to… | Issue |
|---|---|
| Semantic search in `global` or `us` | 1 |
| Search with no `searchString` / “return all” | 2 |
| Search without `searchType` | 3 |
| Filter by publisher | 4 |
| `orderBy` on list | 5 |
| Keyword `NOT` exclusion | 6 |
| Create already ACTIVE | 7 |
| Inline `$(base64 …)` in single-quoted curl | 8 |
| Hide disabled skills without a filter | 9 |
| Delete the served revision | 10 |
| Use `--query` or `query=` | 11 |
| Use `gcloud alpha agent-registry skills` | 12 |
| Look up publisher `google` | 13 |
| Treat semantic hit-count as relevance | 15 |
| `DELETE` the skill while revisions exist | 16 |
| Unqualified keyword on frontmatter text | 17 |
| Filter/search `frontmatter.metadata.*` | 18 |

Full REST shapes: [references/rest.md](references/rest.md).

## Script

All paths relative to this skill root. `--project` and `--location` are required
(no hidden default).

```bash
python3 scripts/registry.py --project PROJECT_ID --location LOCATION COMMAND
```

| Command | Purpose |
|---|---|
| `list` | Browse (`skills.list`) |
| `search --type keyword\|semantic --query "…"` | `skills:search` |
| `get SKILL_ID` | `skills.get` |
| `create --skill-id ID --display-name N --description D --payload ZIP` | DRAFT + zip |
| `activate SKILL_ID` | set `defaultRevision` + ACTIVE |
| `patch SKILL_ID --display-name … --description … --target-state … --default-revision …` | metadata / state |
| `revisions SKILL_ID` | list revisions |
| `add-revision SKILL_ID --payload ZIP [--revision-id ID]` | new immutable snapshot |
| `download SKILL_ID REVISION_ID --out FILE` | `alt=media` (follows 302) |
| `delete-revision SKILL_ID REVISION_ID` | delete one revision (LRO) |
| `delete-skill SKILL_ID` | delete all revisions, then container |

`search --type semantic` on a non-`eu` location exits unless `--force`.
`search` sends `filter=state=ACTIVE` unless `--include-inactive`.

## Demo

Bundled throwaway payload: [assets/sample-demo-skill/SKILL.md](assets/sample-demo-skill/SKILL.md)
(heliograph / noon-gun vocabulary; bland display metadata). Register, prove keyword vs
semantic, then **delete it**. Do not touch other private skills.

```bash
cd assets/sample-demo-skill && zip -r ../../sample-demo-skill.zip SKILL.md && cd ../..
python3 scripts/registry.py --project PROJECT_ID --location eu create \
  --skill-id registry-smoke-test \
  --display-name "Registry Smoke Test" \
  --description "Internal utility skill." \
  --payload sample-demo-skill.zip
python3 scripts/registry.py --project PROJECT_ID --location eu activate private-registry-smoke-test
python3 scripts/registry.py --project PROJECT_ID --location eu search \
  --type keyword --query heliograph
python3 scripts/registry.py --project PROJECT_ID --location eu search \
  --type semantic --query "how do I signal noon with a mirror on a ship" --page-size 5
python3 scripts/registry.py --project PROJECT_ID --location eu delete-skill private-registry-smoke-test
```

## Sample prompts

Show these to new users. Full list: [references/prompts.md](references/prompts.md).

- Onboard me to Agent Registry in project `PROJECT_ID`, location `eu`, using ADC.
- Keyword-search first-party GKE skills.
- Semantic-search skills for writing a professional email. (Warn if location ≠ `eu`.)
- List only my third-party skills.
- Register the bundled smoke-test skill, then prove body-only semantic match.
- Download the ZIP for skill `SKILL_ID` revision `REVISION_ID`.
