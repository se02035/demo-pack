#!/usr/bin/env python3
"""Create a bare Agent Platform runtime and print its resource name.

Usage:
  export GOOGLE_CLOUD_PROJECT=crafty-progress-421108
  export GOOGLE_CLOUD_LOCATION=us-central1   # model location; unused here
  export SANDBOX_LOCATION=us-central1
  python scripts/bootstrap_runtime.py
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "--project",
      default=os.environ.get("GOOGLE_CLOUD_PROJECT", "crafty-progress-421108"),
  )
  parser.add_argument(
      "--location",
      default=os.environ.get("SANDBOX_LOCATION", "us-central1"),
      help="Regional location for the runtime / sandboxes (not global).",
  )
  parser.add_argument(
      "--display-name",
      default="adk-sandbox-agent-runtime",
  )
  args = parser.parse_args()

  if args.location.lower() in {"global", "us", "eu"}:
    print(
        f"ERROR: location {args.location!r} is not valid for sandboxes. "
        "Use a region such as us-central1.",
        file=sys.stderr,
    )
    return 2

  import agentplatform

  client = agentplatform.Client(project=args.project, location=args.location)
  print(f"Creating Agent Platform runtime in {args.project}/{args.location} ...")
  runtime = client.runtimes.create(
      config={"display_name": args.display_name},
  )
  name = getattr(getattr(runtime, "api_resource", None), "name", None) or getattr(
      runtime, "name", None
  )
  if not name:
    print(f"ERROR: create returned unexpected object: {runtime!r}", file=sys.stderr)
    return 1

  print()
  print("Runtime created.")
  print(name)
  print()
  print("Paste this into agents/sandbox_agent/.env as:")
  print(f"SANDBOX_RUNTIME_NAME={name}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
