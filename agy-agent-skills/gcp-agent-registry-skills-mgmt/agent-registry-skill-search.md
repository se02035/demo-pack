# How to search skills in GCP Agent Registry

A step-by-step REST guide for discovering **first-party** (Google-published) and
**third-party** (your own) skills.

Every call below was executed against a GCP project on 2026-09-02
using Application Default Credentials. Replace `PROJECT_ID` / `PROJECT_NUMBER`
with yours. Where the
[public docs](https://docs.cloud.google.com/agent-registry/search-agents-and-tools)
describe behaviour that does not happen, it is listed in [Issues](#issues) instead of
being repeated as if it worked.

---

## TL;DR

| You want to… | Call | Required params |
|---|---|---|
| Browse everything | `GET …/skills` | none |
| Match a name, ID, or description | `GET …/skills:search` | `searchString` + `searchType=KEYWORD` |
| Match intent / meaning (reads `SKILL.md`) | `GET …/skills:search` | `searchString` + `searchType=SEMANTIC` |
| List only your own skills | `GET …/skills:search` | `searchString=name:private*` + `searchType=KEYWORD` |
| Download a skill package | `GET …/revisions/{id}?alt=media` | follow the 302 (`curl -L`) |

Three rules that will save you an afternoon:

1. **Use `eu` for semantic search.** In `global` and `us` it returns `HTTP 200` with an
   empty list. Keyword search works in all three. See [Issue 1](#issue-1-semantic-search-returns-zero-results-in-global-and-us).
2. **Always set `searchType`.** Omitting it does **not** fall back to keyword search —
   it behaves like `SEMANTIC`. In `global`/`us` that looks like “search is empty”.
   See [Issue 3](#issue-3-omitting-searchtype-does-not-default-to-keyword).
3. **Always add `filter=state=ACTIVE`.** Disabled, deprecated, and draft skills remain
   fully searchable otherwise. See [Issue 9](#issue-9-disabled-and-deprecated-skills-remain-searchable).

---

## Step 0 — Prerequisites

### Auth

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project PROJECT_ID
```

```bash
export PROJECT_ID=YOUR_PROJECT_ID
export LOCATION=eu
export TOKEN=$(gcloud auth application-default print-access-token)
export API=https://agentregistry.googleapis.com/v1alpha
```

Every request needs both headers:

```bash
-H "Authorization: Bearer $TOKEN"
-H "x-goog-user-project: $PROJECT_ID"
```

IAM: `roles/agentregistry.viewer` to search, `roles/agentregistry.user` to register.

### API version

Only **`v1alpha`** exposes skills. Verified:

| Endpoint | Result |
|---|---|
| `GET /v1alpha/projects/…/skills` | `HTTP 200` |
| `GET /v1/projects/…/skills` | `HTTP 404` |
| `$discovery/rest?version=v1beta1` | `HTTP 404` (version does not exist) |

The documented gcloud command `gcloud alpha agent-registry skills search` does not exist
in Cloud SDK 575.0.0. Use REST. See [Issue 12](#issue-12-the-documented-gcloud-skills-command-does-not-exist).

The REST query parameter is **`searchString`**, not `query`. See [Issue 11](#issue-11-documented-parameter-name-is-query-the-api-uses-searchstring).

### Locations are independent registries

| Location | Skills (this project) | Keyword search | Semantic search |
|---|---|---|---|
| `global` | 98 | works | empty list |
| `us` | 98 | works | empty list |
| `eu` | 99+ (plus any private skills) | works | works |

This guide uses `LOCATION=eu`.

### First-party vs third-party

| Kind | Resource ID prefix | Example |
|---|---|---|
| First-party (Google Cloud) | `cloud.google.com-` | `cloud.google.com-gke-basics` |
| First-party (Gemini Enterprise) | `discoveryengine.googleapis.com-` | `discoveryengine.googleapis.com-report-writing` |
| Third-party (yours) | `private-` | `private-my-custom-skill` |

A skill you create as `my-custom-skill` is stored as `private-my-custom-skill`. Every
later call must use the prefixed ID.

Publishers actually present (not `google` as the docs show — [Issue 13](#issue-13-publisher-and-urn-formats-differ-from-the-docs)):

```bash
curl -s -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/publishers"
```

---

## Step 1 — Browse the catalog (`skills.list`)

This is the only discovery call that does **not** need a search string. Use it to confirm
the registry is populated and to get resource IDs.

```bash
curl -s -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills?pageSize=100"
```

Trimmed response:

```json
{
  "skills": [
    {
      "name": "projects/PROJECT_ID/locations/eu/skills/cloud.google.com-gke-basics",
      "displayName": "gke-basics",
      "description": "Manages core GKE cluster provisioning…",
      "state": "STATE_ACTIVE",
      "targetState": "TARGET_STATE_ACTIVE",
      "defaultRevision": "…/revisions/…",
      "frontmatter": { "name": "gke-basics", "description": "…" },
      "skillId": "urn:skill:…"
    }
  ]
}
```

Restrict to served skills and page:

```bash
curl -s -G -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  --data-urlencode 'filter=state=ACTIVE' \
  --data-urlencode 'pageSize=100' \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills"
```

Verified filters:

| Filter | Result |
|---|---|
| `state=ACTIVE` | works (99 of 99 first-party skills in `eu`) |
| `state=STATE_DISABLED` | works (both short and long enum forms) |
| `targetState=TARGET_STATE_ACTIVE` | works |
| `createTime>"2026-01-01T00:00:00Z"` | works |
| `createTime>"2026-09-01T00:00:00Z"` | works — empty here because the catalog predates that date |
| `state=ACTIVE AND createTime>"2026-01-01T00:00:00Z"` | works |
| `publisher=…` | **broken** — [Issue 4](#issue-4-filter-on-publisher-never-works) |
| `frontmatter.license="Apache-2.0"` | **rejected** — `field "frontmatter.license" is not supported` |
| `frontmatter.metadata.category=Containers` | **rejected** — [Issue 18](#issue-18-frontmattermetadata-is-neither-searchable-nor-filterable) |

`pageSize` caps at 100. `nextPageToken` returns disjoint pages. `orderBy` is accepted
but ignored — [Issue 5](#issue-5-orderby-is-silently-ignored).

---

## Step 2 — Keyword search (metadata only)

```
GET /v1alpha/projects/{project}/locations/{location}/skills:search
```

| Parameter | Required | Notes |
|---|---|---|
| `searchString` | yes | wire name; not `query` |
| `searchType` | effectively yes | set `KEYWORD` or `SEMANTIC` |
| `filter` | no | same syntax as `skills.list` |
| `pageSize` | no | default 20, cap 100 |
| `pageToken` | no | continuation |

### 2a. First-party example

```bash
curl -s -G -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  --data-urlencode 'searchString=kubernetes' \
  --data-urlencode 'searchType=KEYWORD' \
  --data-urlencode 'filter=state=ACTIVE' \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills:search"
```

Returns **6** skills in `global`, `us`, and `eu` (same result everywhere). Prefix match:

```bash
curl -s -G -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  --data-urlencode 'searchString=displayName:gke*' \
  --data-urlencode 'searchType=KEYWORD' \
  --data-urlencode 'filter=state=ACTIVE' \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills:search"
```

Returns **31** GKE skills.

### 2b. Third-party example

`filter=publisher=…` does not work. Filter on the resource-name prefix instead:

```bash
curl -s -G -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  --data-urlencode 'searchString=name:private*' \
  --data-urlencode 'searchType=KEYWORD' \
  --data-urlencode 'filter=state=ACTIVE' \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills:search"
```

Observed during testing in `eu` (throwaway `zz-search-test-*` skills have since been
removed): `private-my-custom-skill` plus two test packages. Use the same call against
your project to list whatever `private-*` skills you currently have.

Use `name:cloud*` for Google Cloud first-party skills (96 matches).

Exact `skillId` match requires quotes. First-party URNs follow the documented
`urn:skill:publisher:namespace:id` shape; third-party URNs embed project number and
location ([Issue 13](#issue-13-publisher-and-urn-formats-differ-from-the-docs)):

```bash
# first-party
--data-urlencode 'searchString=skillId="urn:skill:cloud.google.com:container:gke-basics"'
# third-party
--data-urlencode 'searchString=skillId="urn:skill:projects-PROJECT_NUMBER:locations:eu:private-my-custom-skill"'
--data-urlencode 'searchType=KEYWORD'
```

Unquoted `skillId=urn:skill:…` returns **zero** results.

### What keyword search indexes

Skill-level metadata only by default. It does **not** read the body of `SKILL.md`.
Frontmatter is searchable **only when you qualify the field** — an unqualified query
does not scan it. See [Issue 17](#issue-17-all-fields-keyword-search-does-not-include-frontmatter).

Proven with a custom skill whose distinctive words lived only in the `SKILL.md` body:
unqualified keyword search returned **zero** hits. After the sibling skill’s
`displayName`/`description` were patched away from those words, unqualified `quintapex`
also returned zero — while `frontmatter.description:quintapex` still returned the skill.

| Field | Unqualified (all-fields) | Field-qualified `field:term` | Prefix `*` |
|---|---|---|---|
| `displayName` | yes | yes | yes |
| `description` (skill resource) | yes | yes | no |
| `name` | yes | yes | yes |
| `skillId` | yes (prefix `skillId:urn*`) | yes, quotes required for exact | yes |
| `frontmatter.name` | **no** | yes | no |
| `frontmatter.description` | **no** | yes | no |
| `frontmatter.license` | **no** | yes | no |
| `frontmatter.metadata.*` | **no** | **no** (200, empty) | – |
| `SKILL.md` body | **no** | **no** — use semantic | – |

Verified expressions (`searchType=KEYWORD`, `eu`):

| `searchString` | Count | Notes |
|---|---|---|
| `kubernetes` | 6 | |
| `gke AND security` | 8 | `AND` works |
| `bigquery OR spanner` | 12 | `OR` works |
| `gke NOT autoscaler` | 2 | **broken** — top hit is `gke-cluster-autoscaler`. [Issue 6](#issue-6-the-not-operator-does-not-exclude) |
| `displayName:gke*` | 31 | |
| `name:cloud*` | 96 | first-party Google Cloud |
| `name:private*` | 3 during tests | third-party |
| `name:gke-basics` | 1 | |
| `description:kubernetes` | 6 | |
| `skillId:urn*` | 99 | all skills |
| `skillId="urn:skill:cloud.google.com:container:gke-basics"` | 1 | quotes required |
| `frontmatter.name:gke-basics` | 1 | field-qualified |
| `frontmatter.description:autoscaling` | 4 | field-qualified |
| `frontmatter.license:Apache` | 3+ | field-qualified |
| `frontmatter.metadata.category:Containers` | 0 | documented, does not match. [Issue 18](#issue-18-frontmattermetadata-is-neither-searchable-nor-filterable) |

---

## Step 3 — Semantic search (indexes `SKILL.md`)

> **Only returns results in `eu`.** Same query in `global` and `us` returns `HTTP 200`
> with `skills: []`. See [Issue 1](#issue-1-semantic-search-returns-zero-results-in-global-and-us).

```bash
curl -s -G -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  --data-urlencode 'searchString=find skills to handle database queries' \
  --data-urlencode 'searchType=SEMANTIC' \
  --data-urlencode 'filter=state=ACTIVE' \
  --data-urlencode 'pageSize=5' \
  "$API/projects/$PROJECT_ID/locations/eu/skills:search"
```

Observed top hits (first-party):

```
cloud.google.com-cloud-logging-query-generation
cloud.google.com-bigquery-basics
cloud.google.com-spanner-basics
cloud.google.com-bigquery-ai-ml
cloud.google.com-bigtable-basics
```

Further intent checks:

| Query | Top hits |
|---|---|
| `write a professional email` | `email-writing-style`, `report-writing` |
| `kubernetes cluster autoscaling` | `gke-cluster-autoscaler`, `gke-workload-scaling` |

### Rank, not count

Semantic search applies **no relevance cutoff**. It returns the whole catalog ranked
(capped by `pageSize`, max 100). Result count is meaningless; only **rank** matters.
Always set `pageSize` to the top-N you want. See [Issue 15](#issue-15-semantic-search-has-no-relevance-cutoff).

### First-party and third-party are both ranked

Where the index exists (`eu`), Google-published skills and `private-*` skills appear in
the same ranked list. A custom skill whose *metadata* said only “Internal utility skill.”
but whose *body* described invoice reconciliation ranked **#1** for paraphrases that
shared no literal keywords:

| Query | Type | Rank of body-only skill | Rank of metadata-control skill |
|---|---|---|---|
| `quintapex` / `invoice` / `ledger` | KEYWORD | not returned | 1 |
| `supplier payment records disagree with the finance books` | SEMANTIC | **1** | 2 |
| `help me close the books at the end of a financial quarter` | SEMANTIC | **1** | 2 |
| `find duplicate payments made to the same company` | SEMANTIC | **1** | 2 |
| `kubernetes autoscaling` | SEMANTIC | not in top 10 | not in top 10 |

Indexing of a newly activated skill was available in **under 60 seconds**. Switching
`defaultRevision` to a new payload re-ranked semantic results in **about one second**
(accounting queries dropped from rank 1 to 2; ballast-water queries rose from 2 to 1).
Adding a revision without changing `defaultRevision` does **not** change search.

---

## Step 4 — Inspect a skill (what actually got indexed)

```bash
# metadata
curl -s -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills/cloud.google.com-gke-basics"

# revisions (response field is skillRevisions, not revisions)
curl -s -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills/cloud.google.com-gke-basics/revisions"

# download ZIP (must follow the 302 — without -L you get JSON and no bytes)
curl -sL -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills/private-my-custom-skill/revisions/ver2?alt=media" \
  -o payload.zip
```

Without `-L`, curl receives `HTTP 302` with
`Location: https://agentregistry.googleapis.com/download/v1alpha/projects/…/revisions/ver2?alt=media`
and a tiny JSON body. With `-L`, the follow-up is `HTTP 200` `content-type: application/zip`
(5212 bytes, magic `PK\x03\x04` for `private-my-custom-skill` revision `ver2`).

Search always resolves `defaultRevision`. If that pointer is unset, `frontmatter` is
null and content search has nothing to index.

---

## Step 5 — Register a third-party skill (so you can search it)

Public docs show a one-shot create with `targetState: TARGET_STATE_ACTIVE`. That payload
is rejected. Registration is three calls. See [Issue 7](#issue-7-documented-create-payload-is-rejected)
and [Issue 8](#issue-8-the-documented-curl-example-cannot-work).

### 5a. Package

ZIP with `SKILL.md` at the root (YAML frontmatter must include `name` and `description`):

```
---
name: utility-alpha
description: Internal utility skill.
license: Apache-2.0
---

# Utility Alpha
…body text — this is what semantic search indexes…
```

```bash
cd my-skill && zip -r ../my-skill.zip SKILL.md
```

Limits: ZIP ≤ 500 KB, uncompressed ≤ 10 MB, file ≤ 1 MB, nesting ≤ 8, no symlinks / `..`.

### 5b. Create as DRAFT

Build the JSON from a script (do not put `$(base64 …)` inside single-quoted curl `-d`).
On macOS use `base64 -i file.zip`, not `base64 -w0`.

```python
import base64, json, subprocess, urllib.request

PROJECT, LOCATION = "PROJECT_ID", "eu"
API = "https://agentregistry.googleapis.com/v1alpha"
tok = subprocess.check_output(
    ["gcloud", "auth", "application-default", "print-access-token"], text=True
).strip()

body = {
    "displayName": "Utility Alpha",
    "description": "Internal utility skill.",
    "type": "SIMPLE",
    "targetState": "TARGET_STATE_DRAFT",   # ACTIVE is rejected at create
    "initialRevision": {
        "archiveUploadSource": {
            "archiveContent": base64.b64encode(open("my-skill.zip", "rb").read()).decode()
        }
    },
}
req = urllib.request.Request(
    f"{API}/projects/{PROJECT}/locations/{LOCATION}/skills?skillId=my-skill",
    data=json.dumps(body).encode(),
    headers={
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "x-goog-user-project": PROJECT,
    },
    method="POST",
)
print(json.loads(urllib.request.urlopen(req).read()))
```

Returns an LRO. Poll until `done: true`:

```bash
curl -s -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/operations/OPERATION_ID"
```

The resource ID becomes `private-my-skill`. After create: `state=STATE_DRAFT`,
`defaultRevision` unset, `frontmatter` null. The revision itself is already `ACTIVE`.

### 5c. Point `defaultRevision` and activate

```bash
# list revisions
curl -s -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills/private-my-skill/revisions"

# set default revision
curl -s -X PATCH \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  -H "Content-Type: application/json" \
  -d '{"defaultRevision":"projects/'"$PROJECT_ID"'/locations/'"$LOCATION"'/skills/private-my-skill/revisions/REVISION_ID"}' \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills/private-my-skill?updateMask=defaultRevision"

# activate
curl -s -X PATCH \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  -H "Content-Type: application/json" \
  -d '{"targetState":"TARGET_STATE_ACTIVE"}' \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills/private-my-skill?updateMask=targetState"
```

`frontmatter` populated on the skill resource is the signal that ingestion parsed
`SKILL.md`. After that, the skill is searchable (keyword on skill-level metadata,
semantic on body) within about a minute.

### 5d. Add a revision and switch what is served

```bash
# POST a new ZIP; skillRevisionId must match ^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$
POST $API/projects/$PROJECT_ID/locations/$LOCATION/skills/private-my-skill/revisions?skillRevisionId=v2-ballast
{ "archiveUploadSource": { "archiveContent": "<base64 zip>" } }
```

Returns an LRO. The new revision becomes `ACTIVE` but **search still uses the old
payload** until you PATCH `defaultRevision`. After pointing at `v2-ballast`, a semantic
query for the new topic ranked the skill **#1 within ~1s**, and the old topic dropped
to #2.

### 5e. Update searchable metadata

```bash
curl -s -X PATCH \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  -H "Content-Type: application/json" \
  -d '{"displayName":"Zymogenic Flange Auditor","description":"Zymogenic flange auditor for pressurized piping."}' \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills/private-zz-search-test-meta?updateMask=displayName,description"
```

Within a few seconds, unqualified keyword `zymogenic` / `flange` matched and the old
unqualified `quintapex` did **not**. Field-qualified `frontmatter.description:quintapex`
still matched — PATCH does not rewrite frontmatter.

### Lifecycle vs search

| `state` | In `skills.list` | Keyword | Semantic | Hidden by `filter=state=ACTIVE` |
|---|---|---|---|---|
| `STATE_ACTIVE` | yes | yes | yes | no |
| `STATE_DISABLED` | yes | **yes** | **yes** | yes |
| `STATE_DEPRECATED` | yes | **yes** | **yes** | yes |
| `STATE_DRAFT` | yes | **yes** | **yes** | yes |

Always pass `filter=state=ACTIVE` on list and search.

Do not delete the revision currently referenced by `defaultRevision` —
[Issue 10](#issue-10-the-default-revision-can-be-deleted-leaving-a-broken-skill).

Delete a skill (revisions first — see [Issue 16](#issue-16-a-skill-cannot-be-deleted-until-all-revisions-are-gone)):

```bash
# 1. list revisions, DELETE each, poll the LRO until done
# 2. then:
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
  "$API/projects/$PROJECT_ID/locations/$LOCATION/skills/private-my-skill"
```

---

## Issues

Behaviour that contradicts the public documentation, or is otherwise surprising.
Reproduced 2026-09-02. Use your own `PROJECT_ID`.

### Issue 1 — Semantic search returns zero results in `global` and `us`

**Severity: high.** This is the original reported symptom.

Docs treat semantic search as location-independent. It only returns results in `eu`.

```bash
for L in global us eu; do
  echo -n "$L: "
  curl -s -G -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
    --data-urlencode 'searchString=find skills to handle database queries' \
    --data-urlencode 'searchType=SEMANTIC' \
    "$API/projects/$PROJECT_ID/locations/$L/skills:search" \
    | python3 -c 'import sys,json; print(len(json.load(sys.stdin).get("skills",[])))'
done
```

```
global: 0
us: 0
eu: 99+
```

Keyword control (`searchString=kubernetes&searchType=KEYWORD`) returns 6 in all three
locations, so this is not auth, IAM, or catalog visibility. A bogus `searchType` returns
`400 INVALID_ARGUMENT ... Invalid value at 'search_type'`, so `SEMANTIC` is parsed and
the empty list is real.

`eu` was also the only location that already had a `private-*` skill. It is plausible
the per-location semantic index is provisioned lazily; that was **not** confirmed (would
require registering a skill in `global`).

**Workaround:** use `eu` for semantic search.

### Issue 2 — “No search criteria returns all skills” is false

Docs: *“If no search criteria is specified then all accessible Skills will be returned.”*

Actual, in `eu`:

```
INVALID_ARGUMENT: Must provide at least one of query or text_query
```

In `global`/`us` the same request returns `HTTP 200` with an empty list (no error).
A `filter` alone does not satisfy the requirement.

**Workaround:** use `skills.list` to browse.

### Issue 3 — Omitting `searchType` does not default to keyword

With a valid `searchString` and no `searchType`:

| Location | Result |
|---|---|
| `eu` | same ranking as `searchType=SEMANTIC` (full corpus, page-capped) |
| `global` / `us` | `HTTP 200`, 0 results (because semantic itself is empty there) |

So unspecified type ≈ semantic, **not** keyword. Combined with Issue 1 this looks
exactly like “search returns nothing” if you copy a gcloud example and only pass the
query string.

```bash
# eu: 100 results, ranked like SEMANTIC — not the 6 keyword hits
--data-urlencode 'searchString=kubernetes'

# eu: 6 results
--data-urlencode 'searchString=kubernetes' --data-urlencode 'searchType=KEYWORD'
```

**Workaround:** always set `searchType=KEYWORD` or `searchType=SEMANTIC`.

### Issue 4 — `filter` on `publisher` never works

Documented as filterable. Observed:

| Filter | Result |
|---|---|
| `publisher=cloud.google.com` | `400` — `unsupported rhs expression type` |
| `publisher="cloud.google.com"` | `200`, 0 results |
| full resource name, quoted | `200`, 0 results |

Combined with a `searchString` that alone returns dozens of hits, the quoted form
silently zeroes the count.

**Workaround:** `searchString=name:private*` or `name:cloud*` with `searchType=KEYWORD`.

### Issue 5 — `orderBy` is silently ignored

`skills.list` accepts `orderBy` (`createTime`, `createTime desc`, `displayName`, `name`)
and returns byte-identical ordering. No error.

**Workaround:** sort client-side.

### Issue 6 — The `NOT` operator does not exclude

`AND` and `OR` work. `NOT` does not:

```bash
--data-urlencode 'searchString=gke NOT autoscaler' --data-urlencode 'searchType=KEYWORD'
```

Returns 2 results; the **first** is `cloud.google.com-gke-cluster-autoscaler`.

**Workaround:** filter client-side.

### Issue 7 — Documented create payload is rejected

Published REST example uses `"targetState": "TARGET_STATE_ACTIVE"`. Actual:

```
INVALID_ARGUMENT: target_state is required and must be TARGET_STATE_DRAFT or TARGET_STATE_DISABLED
```

You must create as `DRAFT`, `PATCH` `defaultRevision`, then `PATCH`
`targetState=TARGET_STATE_ACTIVE`. Until `defaultRevision` is set, `frontmatter` is
null and content is not searchable.

### Issue 8 — The documented curl example cannot work

```bash
-d '{ … "archiveContent": "$(base64 -w0 local_skill.zip)" … }'
```

1. `$(...)` is inside **single quotes**, so the shell never expands it.
2. `-w0` is GNU-only; macOS BSD `base64` needs `base64 -i file.zip`.

**Workaround:** build the body in a script.

### Issue 9 — Disabled and deprecated skills remain searchable

`STATE_DISABLED` / `STATE_DRAFT` are documented as “not served”, yet they remain in
`skills.list` and rank in both keyword and semantic search.

**Workaround:** always pass `filter=state=ACTIVE` (verified on both list and search).

### Issue 10 — The default revision can be deleted, leaving a broken skill

`revisions.delete` accepts the served revision with no error. The skill is left
`state=STATE_DRAFT` vs `targetState=TARGET_STATE_ACTIVE`, with `defaultRevision` absent
and `frontmatter` null.

It can **remain searchable**: the index may still serve deleted payload content.

**Workaround:** repoint `defaultRevision` before deleting a revision.

### Issue 11 — Documented parameter name is `query`; the API uses `searchString`

Docs use `--query` / `query`. The REST query parameter on `skills:search` is
`searchString`. There is no `query` parameter.

### Issue 12 — The documented gcloud `skills` command does not exist

Docs present `gcloud alpha agent-registry skills search` as the primary interface.
Cloud SDK **575.0.0** (alpha `2026.06.26`) has `agents`, `bindings`, `endpoints`,
`mcp-servers`, `operations`, `services` — no `skills` group.

**Workaround:** REST, or update the SDK and re-verify.

### Issue 13 — Publisher and URN formats differ from the docs

| | Documented | Actual |
|---|---|---|
| Publisher | `google` | `cloud.google.com`, `discoveryengine.googleapis.com` |
| First-party URN | `urn:skill:google-workspace:create-docs` | `urn:skill:cloud.google.com:container:gke-basics` (same shape, different publisher) |
| Third-party URN | (not shown) | `urn:skill:projects-PROJECT_NUMBER:locations:eu:private-my-custom-skill` |

First-party URNs match the documented `urn:skill:publisher:namespace:id` shape (publisher
is `cloud.google.com`, not `google`). Third-party URNs embed project number and location,
so they are not portable across projects or locations. `publishers.list` returns only
`FIRST_PARTY` publishers; the `private` publisher that owns third-party skills is not
listed.

### Issue 14 — Internal Java exceptions leak into API errors

```
com.google.cloud.ai.platform.common.errors.AiPlatformException: code=INVALID_ARGUMENT,
message=Must provide at least one of query or text_query, cause=null
```

Search is backed by Vertex AI Search. Error strings are awkward to parse compared with
the `google.rpc.BadRequest` details the same API returns elsewhere.

### Issue 15 — Semantic search has no relevance cutoff

Every semantic query returns the entire catalog ranked (up to `pageSize`). Checking
“did search return anything?” is always yes in `eu`.

**Workaround:** set `pageSize` to the top-N you want; treat **rank** as the signal.

### Issue 16 — A skill cannot be deleted until all revisions are gone

`DELETE …/skills/{id}` fails while any revision exists:

```
FAILED_PRECONDITION: cannot delete skill as it contains one or more revisions
```

`revisions.delete` returns an LRO. Deleting the skill immediately after the 200 still
fails — you must poll until `done: true`, then delete the container.

This is the opposite surprise of [Issue 10](#issue-10-the-default-revision-can-be-deleted-leaving-a-broken-skill):
the served revision *can* be deleted, but the empty skill *cannot* be deleted until
that revision LRO finishes.

**Workaround:** delete every revision, wait for each LRO, then delete the skill.

### Issue 17 — All-fields keyword search does not include frontmatter

Docs mark `frontmatter.name` and `frontmatter.description` as included in all-fields
(unqualified) keyword search.

Actual: after PATCHing a skill’s `displayName`/`description` so they no longer contained
`quintapex`, while `frontmatter.description` still did:

```
searchString=quintapex                         -> 0 results
searchString=frontmatter.description:quintapex -> 1 result (the same skill)
```

Unqualified keyword search indexes skill-level `displayName`, `description`, `name`, and
`skillId` only. Frontmatter requires an explicit `frontmatter.*:` qualifier.

**Workaround:** search `frontmatter.description:TERM` (and/or `frontmatter.name:TERM`) in
addition to the unqualified string.

### Issue 18 — `frontmatter.metadata.*` is neither searchable nor filterable

`cloud.google.com-gke-basics` exposes `frontmatter.metadata.category = Containers`.
Docs list `frontmatter.metadata.` as searchable (`:`) and filterable (`=`).

| Call | Result |
|---|---|
| `searchString=frontmatter.metadata.category:Containers` `searchType=KEYWORD` | `HTTP 200`, 0 results |
| `skills.list` `filter=frontmatter.metadata.category=Containers` | `400` `field "frontmatter.metadata.category" is not supported` |
| `skills.list` `filter=frontmatter.license="Apache-2.0"` | `400` `field "frontmatter.license" is not supported` |

`frontmatter.license` *does* work as a keyword `searchString` qualifier; it does **not**
work as a list `filter`.

**Workaround:** do not rely on custom frontmatter metadata for discovery. Use
`displayName` / `description` / `name` / field-qualified `frontmatter.name` and
`frontmatter.description`.

---

## Appendix — doc flag → REST parameter

| Documented (gcloud / docs) | REST | Notes |
|---|---|---|
| `--query` | `searchString` | GET query param |
| `--search-type=semantic` | `searchType=SEMANTIC` | uppercase; `semantic` also accepted |
| `--project` | path `projects/{id}` | |
| `--location` | path `locations/{loc}` | |
| `--payload` | `initialRevision.archiveUploadSource.archiveContent` | base64 ZIP |
| `--gcs-source-uri` | `initialRevision.gcsSource.uri` | grant `storage.objects.get` to the Agent Registry service agent |
| `--display-name` | `displayName` | |
| `--description` | `description` | |

Agents and MCP servers use **POST** `:search` with a JSON body, not this GET:

- `projects.locations.agents:search`
- `projects.locations.mcpServers:search`
