#!/usr/bin/env python3
"""GCP Agent Registry (v1alpha) skill helper. Stdlib only. ADC via gcloud."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = "https://agentregistry.googleapis.com/v1alpha"
SEMANTIC_LOCATIONS = frozenset({"eu"})
ISSUE_1 = (
    "Issue 1: semantic search returns HTTP 200 with an empty list in 'global' and "
    "'us'. It only returns ranked results in 'eu'. Keyword search works in all three. "
    "Workaround: use --location eu, or pass --force to call anyway."
)


def adc_token() -> str:
    try:
        out = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        sys.exit("gcloud not found. Install Google Cloud SDK and retry.")
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or str(e)).strip()
        sys.exit(
            "Could not mint an ADC token. Run:\n"
            "  gcloud auth application-default login\n"
            "  gcloud auth application-default set-quota-project PROJECT_ID\n"
            f"{msg}"
        )
    token = out.stdout.strip()
    if not token:
        sys.exit("ADC token empty. Re-run gcloud auth application-default login.")
    return token


def request(
    method: str,
    path: str,
    *,
    project: str,
    token: str,
    body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    follow: bool = False,
    raw: bool = False,
) -> tuple[int, Any]:
    url = f"{API}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": project,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener()
    if not follow:
        opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req) as resp:
            payload = resp.read()
            if raw:
                return resp.status, payload
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        payload = e.read()
        if raw:
            return e.code, payload
        try:
            return e.code, json.loads(payload) if payload else {"error": {"message": str(e)}}
        except json.JSONDecodeError:
            return e.code, {"error": {"message": payload[:400].decode(errors="replace")}}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def die_api(code: int, body: Any) -> None:
    if isinstance(body, dict) and "error" in body:
        err = body["error"]
        msg = err.get("message", json.dumps(err))[:500]
        sys.exit(f"HTTP {code}: {err.get('status', '')} {msg}".strip())
    sys.exit(f"HTTP {code}: {body!r}"[:500])


def poll(op_name: str, project: str, token: str, timeout: int = 120) -> dict[str, Any]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, body = request("GET", op_name, project=project, token=token)
        if code != 200:
            die_api(code, body)
        if body.get("done"):
            if body.get("error"):
                sys.exit(f"Operation failed: {json.dumps(body['error'])[:500]}")
            return body
        time.sleep(2)
    sys.exit(f"Timed out waiting for {op_name}")


def maybe_poll(code: int, body: Any, project: str, token: str) -> Any:
    if code >= 400:
        die_api(code, body)
    if isinstance(body, dict) and "operations/" in str(body.get("name", "")):
        return poll(body["name"], project, token)
    return body


def parent(args: argparse.Namespace) -> str:
    return f"projects/{args.project}/locations/{args.location}"


def emit(obj: Any) -> None:
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def cmd_list(args: argparse.Namespace, token: str) -> None:
    params = {"pageSize": str(args.page_size)}
    if not args.include_inactive:
        params["filter"] = "state=ACTIVE"
    if args.page_token:
        params["pageToken"] = args.page_token
    if args.order_by:
        print(
            "Issue 5: orderBy is accepted but ignored. Sorting client-side if needed.",
            file=sys.stderr,
        )
        params["orderBy"] = args.order_by
    code, body = request(
        "GET", f"{parent(args)}/skills", project=args.project, token=token, params=params
    )
    if code != 200:
        die_api(code, body)
    emit(body)


def cmd_search(args: argparse.Namespace, token: str) -> None:
    stype = args.type.upper()
    if stype == "SEMANTIC" and args.location not in SEMANTIC_LOCATIONS and not args.force:
        print(ISSUE_1, file=sys.stderr)
        sys.exit(2)
    if not args.query:
        print(
            "Issue 2: search without searchString fails or returns nothing. "
            "Use `list` to browse.",
            file=sys.stderr,
        )
        sys.exit(2)
    params = {
        "searchString": args.query,
        "searchType": stype,
        "pageSize": str(args.page_size),
    }
    if not args.include_inactive:
        params["filter"] = "state=ACTIVE"
    if args.filter:
        params["filter"] = args.filter
    if args.page_token:
        params["pageToken"] = args.page_token
    if "publisher" in (args.filter or ""):
        print(
            "Issue 4: filter on publisher never works (400 or silent zero). "
            "Use searchString=name:private*, name:cloud*, or name:discoveryengine* instead.",
            file=sys.stderr,
        )
    if "name:cloud.google.com" in args.query or "name:discoveryengine.googleapis.com" in args.query:
        print(
            "Warning (Issue 4): Dots in domain wildcards break search tokenization and return 0 results. "
            "Use 'name:cloud*' or 'name:discoveryengine*' instead.",
            file=sys.stderr,
        )
    if " NOT " in f" {args.query} " or args.query.upper().startswith("NOT "):
        print(
            "Issue 6: keyword NOT does not exclude. Filter client-side.",
            file=sys.stderr,
        )
    code, body = request(
        "GET",
        f"{parent(args)}/skills:search",
        project=args.project,
        token=token,
        params=params,
    )
    if code != 200:
        die_api(code, body)
    emit(body)


def cmd_get(args: argparse.Namespace, token: str) -> None:
    code, body = request(
        "GET",
        f"{parent(args)}/skills/{args.skill_id}",
        project=args.project,
        token=token,
    )
    if code != 200:
        die_api(code, body)
    emit(body)


def cmd_create(args: argparse.Namespace, token: str) -> None:
    zip_path = Path(args.payload)
    if not zip_path.is_file():
        sys.exit(f"Payload not found: {zip_path}")
    archive = base64.b64encode(zip_path.read_bytes()).decode()
    body = {
        "displayName": args.display_name,
        "description": args.description,
        "type": "SIMPLE",
        "targetState": "TARGET_STATE_DRAFT",
        "initialRevision": {"archiveUploadSource": {"archiveContent": archive}},
    }
    code, resp = request(
        "POST",
        f"{parent(args)}/skills",
        project=args.project,
        token=token,
        body=body,
        params={"skillId": args.skill_id},
    )
    result = maybe_poll(code, resp, args.project, token)
    emit(result.get("response", result) if isinstance(result, dict) else result)
    print(
        "Created as DRAFT with defaultRevision unset. Run `activate private-"
        f"{args.skill_id}` next (Issue 7).",
        file=sys.stderr,
    )


def cmd_activate(args: argparse.Namespace, token: str) -> None:
    skill = args.skill_id
    code, revs = request(
        "GET",
        f"{parent(args)}/skills/{skill}/revisions",
        project=args.project,
        token=token,
    )
    if code != 200:
        die_api(code, revs)
    items = revs.get("skillRevisions") or []
    if not items:
        sys.exit(f"No revisions on {skill}")
    rev = items[0]["name"]
    code, resp = request(
        "PATCH",
        f"{parent(args)}/skills/{skill}",
        project=args.project,
        token=token,
        body={"defaultRevision": rev},
        params={"updateMask": "defaultRevision"},
    )
    maybe_poll(code, resp, args.project, token)
    code, resp = request(
        "PATCH",
        f"{parent(args)}/skills/{skill}",
        project=args.project,
        token=token,
        body={"targetState": "TARGET_STATE_ACTIVE"},
        params={"updateMask": "targetState"},
    )
    maybe_poll(code, resp, args.project, token)
    cmd_get(argparse.Namespace(project=args.project, location=args.location, skill_id=skill), token)


def cmd_patch(args: argparse.Namespace, token: str) -> None:
    body: dict[str, Any] = {}
    masks: list[str] = []
    if args.display_name:
        body["displayName"] = args.display_name
        masks.append("displayName")
    if args.description:
        body["description"] = args.description
        masks.append("description")
    if args.target_state:
        body["targetState"] = args.target_state
        masks.append("targetState")
    if args.default_revision:
        body["defaultRevision"] = args.default_revision
        masks.append("defaultRevision")
    if not body:
        sys.exit("Nothing to patch. Pass --display-name, --description, --target-state, and/or --default-revision.")
    code, resp = request(
        "PATCH",
        f"{parent(args)}/skills/{args.skill_id}",
        project=args.project,
        token=token,
        body=body,
        params={"updateMask": ",".join(masks)},
    )
    result = maybe_poll(code, resp, args.project, token)
    emit(result.get("response", result) if isinstance(result, dict) else result)


def cmd_revisions(args: argparse.Namespace, token: str) -> None:
    code, body = request(
        "GET",
        f"{parent(args)}/skills/{args.skill_id}/revisions",
        project=args.project,
        token=token,
    )
    if code != 200:
        die_api(code, body)
    emit(body)


def cmd_add_revision(args: argparse.Namespace, token: str) -> None:
    zip_path = Path(args.payload)
    if not zip_path.is_file():
        sys.exit(f"Payload not found: {zip_path}")
    archive = base64.b64encode(zip_path.read_bytes()).decode()
    params = {}
    if args.revision_id:
        params["skillRevisionId"] = args.revision_id
    code, resp = request(
        "POST",
        f"{parent(args)}/skills/{args.skill_id}/revisions",
        project=args.project,
        token=token,
        body={"archiveUploadSource": {"archiveContent": archive}},
        params=params or None,
    )
    result = maybe_poll(code, resp, args.project, token)
    emit(result.get("response", result) if isinstance(result, dict) else result)
    print(
        "Revision added but not served until you PATCH defaultRevision (or run activate).",
        file=sys.stderr,
    )


def cmd_download(args: argparse.Namespace, token: str) -> None:
    path = f"{parent(args)}/skills/{args.skill_id}/revisions/{args.revision_id}"
    code, payload = request(
        "GET",
        path,
        project=args.project,
        token=token,
        params={"alt": "media"},
        follow=True,
        raw=True,
    )
    if code != 200:
        if isinstance(payload, (bytes, bytearray)):
            try:
                die_api(code, json.loads(payload))
            except json.JSONDecodeError:
                sys.exit(f"HTTP {code} downloading revision")
        die_api(code, payload)
    out = Path(args.out)
    out.write_bytes(payload)
    print(f"Wrote {len(payload)} bytes to {out}", file=sys.stderr)


def cmd_delete_revision(args: argparse.Namespace, token: str) -> None:
    path = f"{parent(args)}/skills/{args.skill_id}/revisions/{args.revision_id}"
    print(
        "Issue 10: deleting the served defaultRevision is allowed and can leave a "
        "broken but still-searchable skill. Repoint defaultRevision first if this "
        "is the served revision.",
        file=sys.stderr,
    )
    code, resp = request("DELETE", path, project=args.project, token=token)
    result = maybe_poll(code, resp, args.project, token)
    emit(result if isinstance(result, dict) else {"ok": True})


def cmd_delete_skill(args: argparse.Namespace, token: str) -> None:
    skill = args.skill_id
    code, revs = request(
        "GET",
        f"{parent(args)}/skills/{skill}/revisions",
        project=args.project,
        token=token,
    )
    if code != 200:
        die_api(code, revs)
    for rev in revs.get("skillRevisions") or []:
        print(f"Deleting revision {rev['name'].split('/')[-1]} …", file=sys.stderr)
        code, resp = request("DELETE", rev["name"], project=args.project, token=token)
        maybe_poll(code, resp, args.project, token)
    code, resp = request(
        "DELETE",
        f"{parent(args)}/skills/{skill}",
        project=args.project,
        token=token,
    )
    result = maybe_poll(code, resp, args.project, token)
    emit(result if isinstance(result, dict) else {"ok": True, "deleted": skill})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GCP Agent Registry v1alpha skill helper")
    p.add_argument("--project", required=True)
    p.add_argument("--location", required=True, help="eu | us | global (independent catalogs)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list")
    sp.add_argument("--page-size", type=int, default=20)
    sp.add_argument("--page-token")
    sp.add_argument("--order-by")
    sp.add_argument("--include-inactive", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("search")
    sp.add_argument("--type", required=True, choices=["keyword", "semantic", "KEYWORD", "SEMANTIC"])
    sp.add_argument("--query", required=True, help="searchString value")
    sp.add_argument("--page-size", type=int, default=20)
    sp.add_argument("--page-token")
    sp.add_argument("--filter", help="Override default filter=state=ACTIVE")
    sp.add_argument("--include-inactive", action="store_true")
    sp.add_argument("--force", action="store_true", help="Allow semantic search outside eu")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("get")
    sp.add_argument("skill_id")
    sp.set_defaults(func=cmd_get)

    sp = sub.add_parser("create")
    sp.add_argument("--skill-id", required=True)
    sp.add_argument("--display-name", required=True)
    sp.add_argument("--description", required=True)
    sp.add_argument("--payload", required=True, help="Path to ZIP with SKILL.md at root")
    sp.set_defaults(func=cmd_create)

    sp = sub.add_parser("activate")
    sp.add_argument("skill_id")
    sp.set_defaults(func=cmd_activate)

    sp = sub.add_parser("patch")
    sp.add_argument("skill_id")
    sp.add_argument("--display-name")
    sp.add_argument("--description")
    sp.add_argument("--target-state")
    sp.add_argument("--default-revision")
    sp.set_defaults(func=cmd_patch)

    sp = sub.add_parser("revisions")
    sp.add_argument("skill_id")
    sp.set_defaults(func=cmd_revisions)

    sp = sub.add_parser("add-revision")
    sp.add_argument("skill_id")
    sp.add_argument("--payload", required=True)
    sp.add_argument("--revision-id")
    sp.set_defaults(func=cmd_add_revision)

    sp = sub.add_parser("download")
    sp.add_argument("skill_id")
    sp.add_argument("revision_id")
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_download)

    sp = sub.add_parser("delete-revision")
    sp.add_argument("skill_id")
    sp.add_argument("revision_id")
    sp.set_defaults(func=cmd_delete_revision)

    sp = sub.add_parser("delete-skill")
    sp.add_argument("skill_id")
    sp.set_defaults(func=cmd_delete_skill)
    return p


def main() -> None:
    args = build_parser().parse_args()
    token = adc_token()
    args.func(args, token)


if __name__ == "__main__":
    main()
