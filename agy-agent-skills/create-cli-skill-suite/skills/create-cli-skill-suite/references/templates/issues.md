# Known issues (tell the user before acting)

Copy-adapt. When these conflict with public docs, **this file and
[limitations.md](limitations.md) win.**

**Agents:** follow [limitations.md](limitations.md) for **Agent action** and
**Tell the user**. Quote the id.

| Id | Trigger | Actual | Workaround |
|---|---|---|---|
| ACME-1 | Vendor CLI for this API | Probes did not find the subcommand | Use `acme-widgets`. |
| ACME-N | (from probes) | (live result) | (workaround or refuse) |

## User-facing blurbs

Use the **Tell the user** column in [limitations.md](limitations.md). Short
forms for the noisiest ids:

### ACME-1 — No vendor CLI

Probes did not find a vendor CLI for this API. I will use `acme-widgets`.
