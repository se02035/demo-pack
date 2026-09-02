# Sample prompts

Give these to the user when onboarding. Replace `PROJECT_ID` / `LOCATION` / skill IDs.
The host agent must still run the onboarding checklist in `SKILL.md` (ADC, project,
location) before any API call, and apply the issue gate in `references/issues.md`.

## Onboarding

```
Onboard me to GCP Agent Registry in project PROJECT_ID, location eu, using Application Default Credentials.
```

```
Verify my ADC can list skills in project PROJECT_ID location eu. Do not ask me to paste a token.
```

## Keyword search (first-party)

```
Keyword-search first-party GKE skills in my registry. Use searchType=KEYWORD and filter=state=ACTIVE.
```

```
Find skills whose displayName starts with gke.
```

```
Look up the first-party skill with skillId "urn:skill:cloud.google.com:container:gke-basics".
```

## Semantic search

```
Semantic-search skills for writing a professional email.
```

If location is not `eu`, warn with Issue 1 **before** calling.

```
Find skills to handle database queries using semantic search in eu, top 5 only.
```

## Third-party vs first-party

```
List only my third-party skills (name:private*).
```

```
List Google Cloud first-party skills (name:cloud*).
```

## Demo (bundled smoke-test skill)

```
Register the bundled sample-demo-skill from this skill's assets, activate it, then prove that keyword search for "heliograph" misses it while semantic search for "how do I signal noon with a mirror on a ship" ranks it first. Delete it afterwards. Do not delete any other private skill.
```

## Lifecycle / issues (agent must explain the issue first)

```
Create a skill already in TARGET_STATE_ACTIVE.   → Issue 7; refuse and use DRAFT then activate.
```

```
Search with no query string so I get everything.   → Issue 2; use list instead.
```

```
Filter skills by publisher google / cloud.google.com.   → Issue 4; use name prefixes.
```

```
Disable skill SKILL_ID and show it still appears in search unless filter=state=ACTIVE.   → Issue 9.
```

```
Delete skill SKILL_ID.   → Issue 16; delete revisions first (the script does this).
```

```
Semantic search in location global.   → Issue 1; stop unless the user switches to eu or confirms --force.
```

## Inspect / download

```
Show metadata and revisions for skill SKILL_ID.
```

```
Download the ZIP for skill SKILL_ID revision REVISION_ID to ./payload.zip.
```

## Metadata patch

```
Rename private-registry-smoke-test display name and description, then keyword-search the new words.
```
