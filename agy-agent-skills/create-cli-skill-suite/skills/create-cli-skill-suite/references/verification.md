# Verification (SDK-first probes)

Complete the matrix **before** the implementation plan. **Complete ≠ every row
green.** Each ship-bar row must **run**. Success becomes a CLI command.
Failure or blocked auth becomes an issue id (refuse / out of scope), not a
silent omission.

No packaged CLI and no generated skills in this phase.

## Matrix columns

| skill name | ship-bar feature | candidate SDK/HTTP call | requires: | probe file | result (ok / fail / blocked) | issue id |

Show this table as the verification plan, then probe. Explicit accept is not
required for this step (it is required for scope, spec, and the later
implementation plan).

## SDK vs REST

| Rule | Meaning |
|---|---|
| Official Python SDK is the default | Search vendor docs, PyPI, generated OpenAPI/gRPC stubs. Install the same extra/version the CLI will depend on |
| No official Python SDK | Still ship a Python argparse CLI wrapping HTTP/gRPC from probes. Do not switch language |
| Do not skip an existing Python SDK | REST/curl is a fallback or control experiment only |
| Vendor CLI is not assumed | Do not document subcommands probes did not find |

## Probe rules

- Throwaway `_probe_*.py`, gitignored. Call the SDK (not the future argparse
  facade).
- Print a short JSON object to stdout: `ok`/`fail`, resource ids if any, error
  excerpt. Do not print secrets.
- Default wait caps unless the user set others: **300s** async / ready /
  resource wait. Do not use an SDK convenience waiter that hung in probes;
  poll with an explicit cap.
- Prove **auth** as its own rows (credential present, wrong identity, missing
  extra principal).
- Cheap preflight first; do not start a row’s long wait until `requires:` is
  complete.
- Create/list success ≠ ready when there is a state machine. Poll get until
  terminal. Listing while provisioning is not ready.
- Multi-environment products: include the environments the user cares about,
  or document “single environment only”. Capability × environment table when
  probes differ. No silent failover.
- Missing completion flag = in progress if probes showed that. On terminal
  error print the operation/error object; do not invent “check the logs”; do
  not retry the same kind/environment in a loop. Stop that kind; continue
  independent rows.
- Pin the client class + API version probes used. Ban sample/deprecated
  clients probes disproved.
- Decode the live body the next command needs. Do not trust SDK pretty-print
  when it encodes or omits fields.
- Cleanup leftover resources (`agy-<slug>-` unless the spec sheet named
  another). Do not attach smokes to unnamed production resources.
- Parallelize independent probes.

## Outputs

- Human-only `*-api-evidence.md` at suite root (**gitignored**; may contain
  account ids). Not copied by npx.
- Complete issue log (every failed, mismatched, or auth-blocked row gets an
  id). See [known-issues.md](known-issues.md).
