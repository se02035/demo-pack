# Known limitations (agent contract)

Copy-adapt. Replace `ACME-` with the accepted issue prefix. **This file wins
over public docs.** Read it before any mutate. Quote the issue id when you
stop or change the plan.

Do not invent workarounds. Do not silently fail over to another environment.
Do not bake account ids, principals, or operation ids in as “the default.”

## How to apply a row

1. **Agent action** — do this *before* the API call (or instead of it).
2. **Tell the user** — say this in the same turn, in plain language.
3. If they insist on a refused call, explain again and still refuse (except
   where the row says “only if they explicitly allow”).

## What works where

Fill from probes. Omit this table if the product is single-environment and
kind-agnostic.

| Capability | Env A | Env B |
|---|---|---|
| (feature) | yes / no — (error) | |

## Decision table

| Id | When | Agent action | Tell the user |
|---|---|---|---|
| ACME-1 | They ask for a vendor CLI probes did not find | Use `acme-widgets` (or `python3 -m acme_widgets`). Do not invent the vendor CLI. | There is no vendor CLI for this API. I will use the acme-widgets CLI. |
| ACME-N | (trigger from probes) | (before the call) | (plain language, same turn) |

## Permissions the caller must already have

Do not probe policy unless they ask. Do not put emails or account ids in
flags by default.

| Who | Permission | On | If missing |
|---|---|---|---|
| API principal | (from probes) | (resource) | (error) |
