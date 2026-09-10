# Sample prompts

Give these to the user when onboarding. Replace `PROJECT_ID` / `LOCATION` /
`ENGINE` / `SANDBOX` / `TEMPLATE` / `IMAGE_URI`. Never paste a real project ID.
The host agent must still run the onboarding checklist in `SKILL.md` (ADC,
project, location) before any API call, and apply
[limitations.md](limitations.md).

If invocation is unclear, run `python3 scripts/sandbox.py help` first (no ADC).

## Onboarding

```
Show me how to invoke the sandbox CLI. Run scripts/sandbox.py help. Do not call GCP yet.
```

```
Onboard me to Agent Platform sandboxes in project PROJECT_ID, location us-central1, using Application Default Credentials.
```

```
Onboard me to Agent Platform sandboxes in project PROJECT_ID, location europe-west4, using Application Default Credentials. Tell me first if shell or Computer Use templates cannot provision.
```

```
Verify my ADC can list reasoning engines in project PROJECT_ID location LOCATION. Do not ask me to paste a token.
```

## Engines

```
Create a dedicated empty sandbox-host engine named agy-sandbox-host in project PROJECT_ID location LOCATION. Do not deploy an agent onto it.
```

```
Get engine ENGINE in project PROJECT_ID location LOCATION.
```

```
Delete engine ENGINE in project PROJECT_ID location LOCATION after its sandboxes and templates are gone. Use --yes.
```

## Templates

```
Create a prebuilt shell sandbox template on engine ENGINE in project PROJECT_ID location LOCATION.
```

```
Create a Computer Use template on engine ENGINE with internet egress enabled, then reuse it for sandboxes.
```

```
(Only if I have an image) Create a BYOC template from IMAGE_URI on engine ENGINE and grant the sandbox service agent Artifact Registry reader.
```

## Sandboxes

```
Create a dedicated empty sandbox-host engine, then a prebuilt shell sandbox with TTL 1h; list sandboxes; delete them when done.
```

```
Create a code-execution sandbox (Python, default machine) on engine ENGINE in project PROJECT_ID location LOCATION.
```

```
Create a Python code-execution sandbox in europe-west4. Do not create shell or Computer Use templates unless I explicitly accept that they may fail to provision.
```

```
Pause sandbox SANDBOX, then resume it. If it is a code-execution sandbox, refuse (CRUD-8).
```

```
Create a Computer Use sandbox from template TEMPLATE (internet egress on) on engine ENGINE. Do not send spec.computerUseEnvironment.
```

```
Wait until sandbox SANDBOX is STATE_RUNNING (timeout 300s).
```

## Exec

```
Run print(2+2) in code sandbox SANDBOX in project PROJECT_ID location LOCATION.
```

```
Run echo ok && pwd in shell sandbox SANDBOX. If it is a code sandbox, refuse.
```

## Computer Use

```
Check Computer Use health on SANDBOX using service account SERVICE_ACCOUNT_EMAIL. Do not default an SA.
```

```
Playwright connect_over_cdp on SANDBOX in us-central1 with SERVICE_ACCOUNT_EMAIL.
```

## Cleanup

```
Delete sandbox SANDBOX, then template TEMPLATE, then engine ENGINE in project PROJECT_ID location LOCATION. Confirm with --yes. Warn me they bill while they exist.
```
