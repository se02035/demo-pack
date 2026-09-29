#!/usr/bin/env python3
"""Create (or reuse) a pinned shell sandbox template and print its name.

Every bare sandboxes.create auto-provisions a throwaway template (~78s) and
never deletes it. Pinning one reusable template removes that cost and the leak.

Usage:
  export GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT
  export SANDBOX_LOCATION=us-central1
  export SANDBOX_RUNTIME_NAME=projects/.../reasoningEngines/...
  python scripts/bootstrap_template.py
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "--project",
      default=os.environ.get("GOOGLE_CLOUD_PROJECT", "YOUR_GCP_PROJECT"),
  )
  parser.add_argument(
      "--location",
      default=os.environ.get("SANDBOX_LOCATION", "us-central1"),
  )
  parser.add_argument(
      "--runtime-name",
      default=os.environ.get("SANDBOX_RUNTIME_NAME"),
  )
  parser.add_argument(
      "--display-name",
      default=os.environ.get("SANDBOX_DISPLAY_NAME_PREFIX", "adk-demo") + "-shell-template",
  )
  args = parser.parse_args()
  if not args.runtime_name or args.runtime_name.endswith("/RUNTIME_ID"):
    print("ERROR: set SANDBOX_RUNTIME_NAME to a real runtime", file=sys.stderr)
    return 2

  # Prefer the project's wrapper so retries/error mapping stay consistent.
  sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agents"))
  from sandbox_agent.sandbox.client import SandboxClient

  client = SandboxClient(project=args.project, location=args.location)

  existing = None
  for tpl in client.list_templates(runtime_name=args.runtime_name):
    if tpl.get("display_name") != args.display_name or not tpl.get("name"):
      continue
    try:
      client.get_template(name=tpl["name"])
    except Exception:
      continue
    existing = tpl
    break

  if existing:
    name = existing["name"]
    print(f"Reusing existing template {args.display_name!r}.")
  else:
    print(f"Creating shell template {args.display_name!r} ...")
    created = client.create_template(
        runtime_name=args.runtime_name,
        display_name=args.display_name,
        wait_for_completion=True,
    )
    name = created.get("name")
    if not name:
      print(f"ERROR: create returned unexpected object: {created!r}", file=sys.stderr)
      return 1
    print("Template created.")

  print()
  print(name)
  print()
  print("Paste this into agents/sandbox_agent/.env as:")
  print(f"SANDBOX_TEMPLATE_NAME={name}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
