#!/usr/bin/env python3
"""List or delete sandboxes whose display_name starts with a prefix.

Usage:
  python scripts/reap_sandboxes.py --list
  python scripts/reap_sandboxes.py --delete --older-than-hours 1
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone


def _parse_create_time(value: object) -> datetime | None:
  if value is None:
    return None
  if isinstance(value, datetime):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
  text = str(value).strip()
  if not text:
    return None
  try:
    if text.endswith("Z"):
      text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
  except ValueError:
    return None


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "--project",
      default=os.environ.get("GOOGLE_CLOUD_PROJECT", "crafty-progress-421108"),
  )
  parser.add_argument(
      "--location",
      default=os.environ.get("SANDBOX_LOCATION", "us-central1"),
  )
  parser.add_argument(
      "--runtime-name",
      default=os.environ.get("SANDBOX_RUNTIME_NAME"),
      required=False,
  )
  parser.add_argument(
      "--prefix",
      default=os.environ.get("SANDBOX_DISPLAY_NAME_PREFIX", "adk-demo"),
  )
  parser.add_argument("--list", action="store_true", help="List matching sandboxes.")
  parser.add_argument("--delete", action="store_true", help="Delete matching sandboxes.")
  parser.add_argument(
      "--older-than-hours",
      type=float,
      default=0.0,
      help="Only act on sandboxes older than this many hours (0 = all).",
  )
  args = parser.parse_args()

  if not args.runtime_name:
    print("ERROR: set --runtime-name or SANDBOX_RUNTIME_NAME", file=sys.stderr)
    return 2
  if not args.list and not args.delete:
    print("ERROR: pass --list and/or --delete", file=sys.stderr)
    return 2

  import agentplatform

  client = agentplatform.Client(project=args.project, location=args.location)
  sandboxes = list(client.sandboxes.list(name=args.runtime_name))
  now = datetime.now(timezone.utc)
  matched = []
  for sandbox in sandboxes:
    display = getattr(sandbox, "display_name", "") or ""
    if not display.startswith(args.prefix):
      continue
    created = _parse_create_time(getattr(sandbox, "create_time", None))
    age_hours = (now - created).total_seconds() / 3600.0 if created else None
    if args.older_than_hours > 0 and (age_hours is None or age_hours < args.older_than_hours):
      continue
    matched.append((sandbox, display, age_hours))

  if args.list or not args.delete:
    for sandbox, display, age_hours in matched:
      age = f"{age_hours:.2f}h" if age_hours is not None else "unknown-age"
      print(f"{sandbox.name}\t{display}\t{getattr(sandbox, 'state', None)}\t{age}")
    print(f"{len(matched)} matching sandbox(es).")

  if args.delete:
    for sandbox, display, _age in matched:
      print(f"Deleting {sandbox.name} ({display}) ...")
      client.sandboxes.delete(name=sandbox.name)
    print(f"Deleted {len(matched)} sandbox(es).")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
