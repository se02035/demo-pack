# Known issues (tell the user before acting)

Validated 2026-09-02 against `agentregistry.googleapis.com/v1alpha`. When these
conflict with https://docs.cloud.google.com/agent-registry/search-agents-and-tools,
**this file wins**. Quote the issue id, the actual behaviour, and the workaround.

| Id | Trigger | Actual | Workaround |
|---|---|---|---|
| 1 | Semantic search in `global` or `us` | HTTP 200, empty `skills` | Use `eu`. Keyword still works everywhere. |
| 2 | Search with no `searchString` | `INVALID_ARGUMENT` in `eu`; empty 200 in `global`/`us` | Use `list` to browse. |
| 3 | Omit `searchType` | Behaves like `SEMANTIC` (empty in `global`/`us`) | Always pass `KEYWORD` or `SEMANTIC`. |
| 4 | `filter=publisher=…` | 400 or silent zero results | Keyword `name:private*` / `name:cloud*` / `name:discoveryengine*`. |
| 5 | `orderBy` on `skills.list` | Silently ignored | Sort client-side. |
| 6 | Keyword `NOT` | Does not exclude (can rank the forbidden term first) | Filter client-side. |
| 7 | Create with `TARGET_STATE_ACTIVE` | 400; must be DRAFT or DISABLED | Create DRAFT → set `defaultRevision` → ACTIVE. |
| 8 | Documented curl `$(base64 …)` in single quotes | Never expands; `-w0` is GNU-only | Use `scripts/registry.py create`. |
| 9 | Expect disabled/deprecated/draft to be hidden | Still listed and ranked | Always `filter=state=ACTIVE`. |
| 10 | Delete the served revision | Allowed; skill becomes incoherent; index may still match | Repoint `defaultRevision` first. |
| 11 | Docs `--query` / `query` | REST param is `searchString` | Use the script `--query` (mapped) or `searchString`. |
| 12 | Use `gcloud alpha agent-registry skills` | Command group missing on SDK 575 | REST / this script. |
| 13 | Look up publisher `google` | Publishers are `cloud.google.com` and `discoveryengine.googleapis.com`. First-party URN e.g. `urn:skill:cloud.google.com:container:gke-basics`. Private URN embeds project number + location. | Use live `skillId` from `get`/`list`. |
| 14 | Parse errors as `google.rpc` only | Some errors leak `AiPlatformException` (Vertex AI Search) | Match on HTTP status + substring. |
| 15 | Treat semantic hit-count as relevance | Entire catalog is ranked (page cap 100) | Use `--page-size` as top-N; rank is the signal. |
| 16 | `DELETE` the skill while revisions exist | `FAILED_PRECONDITION` | Delete each revision, poll LRO, then delete skill (`delete-skill`). |
| 17 | Unqualified keyword on frontmatter text | Misses unless `frontmatter.description:term` (etc.) | Field-qualify, or put terms in skill `description`. |
| 18 | `frontmatter.metadata.*` search or list filter | Search: 200 empty. List filter: 400 unsupported | Use `displayName` / `description` / `name`. |

## User-facing blurbs

### Issue 1 — Semantic empty in `global` / `us`

Public docs treat semantic search as location-independent. In this API it only
returns ranked hits in **`eu`**. Same credentials and query in `global`/`us` return
an empty list. Keyword search is unaffected.

### Issue 2 — Empty search does not list everything

Docs: no criteria returns all skills. Actual: you must provide `searchString`
(`Must provide at least one of query or text_query` in `eu`). Use `list`.

### Issue 3 — Missing `searchType` is not keyword

Unspecified type ≈ semantic. Combined with Issue 1 this looks like “search is empty”.

### Issue 4 — Publisher filter & domain wildcards

- **Filter broken**: Bare `publisher=cloud.google.com` → 400. Quoted / full resource name → 200 with 0 hits.
- **Prefix matching**: Use `name:cloud*` (for `cloud.google.com-*`), `name:discoveryengine*` (for `discoveryengine.googleapis.com-*`), or `name:private*` (for third-party skills).
- **Wildcard Gotcha**: Do **not** use `name:cloud.google.com*` or `name:discoveryengine.googleapis.com*`. Search tokenization treats dots (`.`) as delimiters, breaking prefix wildcard matching and silently returning 0 hits. Always wildcard on the first token (e.g. `name:cloud*`).

### Issue 5 — `orderBy`

Accepted, identical ordering to the default. No error.

### Issue 6 — `NOT`

`gke NOT autoscaler` can return `gke-cluster-autoscaler` first. `AND` / `OR` work.

### Issue 7 — Create ACTIVE

`target_state is required and must be TARGET_STATE_DRAFT or TARGET_STATE_DISABLED`.
Until `defaultRevision` is set, `frontmatter` is null and content is not searchable.

### Issue 8 — Documented curl

`$(base64 -w0 …)` inside single quotes never expands; macOS `base64` has no `-w0`.

### Issue 9 — Lifecycle vs search

`STATE_DISABLED`, `STATE_DEPRECATED`, and `STATE_DRAFT` remain in `list` and both
search modes. Only `filter=state=ACTIVE` hides them.

### Issue 10 — Deleting the default revision

No guard. Skill can sit at `STATE_DRAFT` vs `targetState=ACTIVE` with no payload and
still rank in search.

### Issue 11 — Parameter name

REST: `searchString`. There is no `query` query-parameter.

### Issue 12 — gcloud

SDK 575.0.0 alpha has no `skills` group under `gcloud alpha agent-registry`.

### Issue 13 — Publishers and URNs

Not `google`. First-party URNs follow `urn:skill:publisher:namespace:id`. Third-party
URNs are `urn:skill:projects-NUMBER:locations:LOCATION:private-ID` and are not portable.
`publishers.list` omits the `private` publisher.

### Issue 14 — Error shape

Vertex AI Search exceptions appear as raw Java strings in some 400s.

### Issue 15 — No semantic cutoff

A query still returns the rest of the catalog at low rank. Always set page size.

### Issue 16 — Delete order

`cannot delete skill as it contains one or more revisions`. Revision delete is an LRO;
deleting the skill before `done: true` still fails.

### Issue 17 — Frontmatter not in all-fields keyword

After PATCHing skill `description` away from a term that remains in YAML frontmatter,
unqualified keyword misses; `frontmatter.description:term` still hits.

### Issue 18 — Custom frontmatter metadata

`frontmatter.metadata.category` exists on skills such as `gke-basics` but is not
searchable or list-filterable. `frontmatter.license` works as a **search** qualifier
only, not as a list filter.
