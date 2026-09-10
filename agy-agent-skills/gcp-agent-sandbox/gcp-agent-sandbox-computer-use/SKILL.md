---
name: gcp-agent-sandbox-computer-use
description: >-
  Drive Gemini Enterprise Agent Platform Computer Use sandboxes: JWT access
  token, GET / and /tabs, POST /cdp, CDP websocket headers, optional Playwright
  chromium.connect_over_cdp. Proven in us-central1. europe-west4 CU templates
  currently FAIL/ABORT. Use when the user mentions Computer Use, CDP, Playwright
  connect_over_cdp, or sandbox browser automation. Requires --service-account
  (no default).
license: Apache-2.0
compatibility: >-
  Python 3.10+, pip install -r ../requirements.txt
  (google-cloud-aiplatform[agent_engines]>=2.1.0), gcloud ADC. Playwright is
  optional (`pip install playwright && playwright install chromium`). Caller
  needs Token Creator on --service-account. There is no gcloud sandbox CLI.
metadata:
  version: "1.0"
---

# GCP Agent Platform Computer Use

Talk to a **RUNNING Computer Use** sandbox. Create it with
**gcp-agent-sandbox-crud** (template `COMPUTER_USE` + `internet_access`, sandbox
**no spec**). Read
[../gcp-agent-sandbox-crud/references/limitations.md](../gcp-agent-sandbox-crud/references/limitations.md)
first (CRUD-2, CRUD-6, CRUD-10, CRUD-15).

## Hard rules

- `--project`, `--location`, and **`--service-account`** required. Never default
  an SA email.
- ADC OAuth as the CU bearer is **401** invalid `iss`. JWT only (CRUD-10).
- On 403 `signJwt`, print the Token Creator prerequisite. Do not grant IAM.
- Do not send `computer_use_environment` on create (CRUD-2).
- `europe-west4` CU templates do not become ACTIVE (CRUD-6). Do not fail over
  to US unless the user agrees.
- No VNC path (CRUD-15). Playwright `connect_over_cdp` is the proven US method.
- Do not print the `Sec-WebSocket-Protocol` value (it contains a JWT). `cu ws`
  prints the URL and header **keys** only.

```bash
python3 scripts/sandbox.py help cu
python3 scripts/sandbox.py --project PROJECT_ID --location LOCATION \
  cu health SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL
python3 scripts/sandbox.py --project PROJECT_ID --location LOCATION \
  cu tabs SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL
python3 scripts/sandbox.py --project PROJECT_ID --location LOCATION \
  cu cdp SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL
python3 scripts/sandbox.py --project PROJECT_ID --location LOCATION \
  cu ws SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL
python3 scripts/sandbox.py --project PROJECT_ID --location LOCATION \
  cu playwright SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL
```

Playwright (US, after `cu ws` or `cu playwright`): `chromium.connect_over_cdp`
with the websocket URL and headers from `generate_browser_ws_headers` (includes
`Sec-WebSocket-Protocol`). Live check: page title **Example Domain**.

## IAM (caller must already have)

| Who | Role | On |
|---|---|---|
| ADC principal | `roles/aiplatform.user` | project |
| ADC principal | `roles/iam.serviceAccountTokenCreator` | **the** `--service-account` |
| `--service-account` | `roles/aiplatform.user` | project |

## Sample prompts

- Check Computer Use health on SANDBOX in us-central1 using SA SERVICE_ACCOUNT_EMAIL.
- Navigate to example.com via CDP, then Playwright connect_over_cdp.
- Do not try Computer Use templates in europe-west4 unless I accept they may fail.
