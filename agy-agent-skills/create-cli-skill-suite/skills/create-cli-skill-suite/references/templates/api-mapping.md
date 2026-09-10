# API mapping (CLI → SDK or HTTP)

Copy-adapt after probes. Pin the **live** client class and API version.
`help` must not construct the client.

```python
# Fill from probes. Example shape only — replace with the live client.
client = OfficialClient(
    # required env from user-stated flags
)
```

Prefer `acme-widgets` over curl. Do not document a vendor CLI probes did not
find. Do not use a deprecated/sample client probes disproved.

Known limits: [limitations.md](limitations.md).

## Resources

| Resource | Name format |
|---|---|
| (kind) | (API name; may differ in format from the user-stated id) |

Print the backend resource name the next call needs.

## CLI → SDK / HTTP

| CLI | Call | Notes |
|---|---|---|
| `widgets list` | (method) | |
| `widgets create` | (method) | `wait` false if an SDK waiter hung; poll until terminal |
| `widgets delete` | (method) | require `--yes` |

Never unbounded wait. Caps: 300s async, 300s ready, 300s resource wait
unless the user set others.

## Create shapes

Fill the live request body from probes, not from docs that probes disproved.

## Errors

Print `error` fields plus the **operation/resource name** probes returned.
Do not send the user to product logs if probes showed the error only on the
operation object.
