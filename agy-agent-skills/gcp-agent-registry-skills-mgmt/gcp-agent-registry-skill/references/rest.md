# REST reference (v1alpha)

Base: `https://agentregistry.googleapis.com/v1alpha`

Headers on every call:

```
Authorization: Bearer ADC_TOKEN
x-goog-user-project: PROJECT_ID
```

`v1` has no skills resource. `v1beta1` does not exist.

Prefer `scripts/registry.py` over hand-rolled curl.

### Why not the official Python client

[`google-cloud-agentregistry`](https://pypi.org/project/google-cloud-agentregistry/)
(GAPIC) is **v1 only**: agents, MCP servers, bindings, endpoints, services. It has no
`Skill` types, no `search_skills`, and no `v1alpha` module. Skills exist only on
`agentregistry.googleapis.com/v1alpha` (REST `GET /v1/…/skills` is 404). Stay on this
script until the client library ships v1alpha skills.

## Resources

| Resource | ID format |
|---|---|
| Skill | `projects/{p}/locations/{l}/skills/{skill}` |
| Revision | `…/skills/{skill}/revisions/{revision}` |
| Operation | `…/locations/{l}/operations/{op}` |

Locations `global`, `us`, and `eu` are **separate catalogs**.

### First-party vs third-party

| Kind | Resource ID prefix |
|---|---|
| Google Cloud | `cloud.google.com-` |
| Gemini Enterprise | `discoveryengine.googleapis.com-` |
| Yours | `private-` (forced; you cannot pick a publisher) |

Creating `--skill-id registry-smoke-test` stores `private-registry-smoke-test`.

First-party `skillId` example: `urn:skill:cloud.google.com:container:gke-basics`.
Third-party: `urn:skill:projects-{NUMBER}:locations:{loc}:private-{id}`.

## List (browse — no query)

`GET …/skills?pageSize=100&filter=state=ACTIVE`

Working filters: `state=ACTIVE`, `state=STATE_DISABLED`, `targetState=…`,
`createTime>"RFC3339"`, AND combinations.

Broken: `publisher`, `frontmatter.license`, `frontmatter.metadata.*` (Issues 4, 18).
`orderBy` ignored (Issue 5). `pageSize` cap 100; `nextPageToken` works.

## Search

`GET …/skills:search?searchString=…&searchType=KEYWORD|SEMANTIC&filter=state=ACTIVE&pageSize=20`

### Keyword (`KEYWORD`)

Indexes skill-level `displayName`, `description`, `name`, `skillId`. Does **not** read
`SKILL.md` body. Frontmatter only if field-qualified (`frontmatter.description:term`)
— Issue 17.

Useful strings: `kubernetes`, `gke AND security`, `bigquery OR spanner`,
`displayName:gke*`, `name:cloud*`, `name:discoveryengine*`, `name:private*`,
`skillId:urn*`, `skillId="urn:skill:…" ` (quotes required for exact URN).

Targeting publishers: Use `name:cloud*` (Google Cloud) or `name:discoveryengine*`
(Gemini Enterprise). Do NOT use `name:cloud.google.com*` — dots in domain names
break prefix wildcard tokenization in the search engine (Issue 4).

`AND`/`OR` work. `NOT` does not (Issue 6).

### Semantic (`SEMANTIC`)

Indexes `SKILL.md` body. **Only `eu` returns results** (Issue 1). No relevance cutoff
— whole catalog ranked; use `pageSize` as top-N (Issue 15). First-party and
`private-*` share the same ranking. New ACTIVE skill: searchable in under a minute.
Switching `defaultRevision` re-ranks in about a second.

## Get / revisions / download

```
GET …/skills/{id}
GET …/skills/{id}/revisions     # response field: skillRevisions
GET …/skills/{id}/revisions/{rev}
GET …/skills/{id}/revisions/{rev}?alt=media   # HTTP 302 → /download/v1alpha/… ; follow it
```

Search always uses `defaultRevision`. If unset, `frontmatter` is null.

## Create / activate (three calls)

1. `POST …/skills?skillId=ID` with `targetState: TARGET_STATE_DRAFT` and
   `initialRevision.archiveUploadSource.archiveContent` (base64 ZIP, `SKILL.md` at root).
   Returns an LRO. After: `STATE_DRAFT`, no `defaultRevision`.
2. `PATCH …/skills/private-ID?updateMask=defaultRevision` with the revision name.
3. `PATCH …/skills/private-ID?updateMask=targetState` with `TARGET_STATE_ACTIVE`.

ZIP limits: 500 KB compressed, 10 MB uncompressed, 1 MB/file, depth ≤ 8, no `..` / symlinks.
Frontmatter YAML must include `name` and `description`.

`scripts/registry.py create` then `activate private-ID`.

## Patch / extra revisions

`PATCH` `updateMask` for `displayName`, `description`, `targetState`, `defaultRevision`.
Keyword search picks up displayName/description within seconds. PATCH does not rewrite
frontmatter.

`POST …/skills/{id}/revisions?skillRevisionId=v2` — does **not** change what is served
until `defaultRevision` is updated. `skillRevisionId` must match
`^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$`.

`activate` uses the **first** revision listed; after adding revisions, patch
`--default-revision` explicitly.

## Delete

Revision delete is an LRO. Skill delete fails while revisions exist (Issue 16).
`delete-skill` deletes every revision, polls, then deletes the container.

Do not delete the served revision unless you intend to break the skill (Issue 10).

## States vs search

| state | list | keyword | semantic | hidden by `state=ACTIVE` |
|---|---|---|---|---|
| ACTIVE | yes | yes | yes | no |
| DISABLED | yes | yes | yes | yes |
| DEPRECATED | yes | yes | yes | yes |
| DRAFT | yes | yes | yes | yes |
