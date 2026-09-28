"""Shared helpers for tool result shaping."""

from __future__ import annotations

from typing import Any


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
  if max_chars <= 0 or len(text) <= max_chars:
    return text, False
  return text[:max_chars], True


def shape_bash_result(
    *,
    sandbox_name: str,
    result: dict[str, Any],
    max_chars: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
  stdout, stdout_truncated = truncate_text(result.get("stdout") or "", max_chars)
  stderr, stderr_truncated = truncate_text(result.get("stderr") or "", max_chars)
  payload: dict[str, Any] = {
      "sandbox_name": sandbox_name,
      "stdout": stdout,
      "stderr": stderr,
      "returncode": int(result.get("returncode") or 0),
      "duration_ms": result.get("duration_ms"),
      "truncated": bool(stdout_truncated or stderr_truncated),
  }
  if extra:
    payload.update(extra)
  return payload


def error_payload(*, sandbox_name: str | None, error: str, code: str) -> dict[str, Any]:
  return {
      "ok": False,
      "error": error,
      "error_code": code,
      "sandbox_name": sandbox_name,
  }
