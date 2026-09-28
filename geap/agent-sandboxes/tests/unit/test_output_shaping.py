"""Output truncation tests."""

from __future__ import annotations

from sandbox_agent.tools.output import shape_bash_result, truncate_text


def test_truncate_text_boundary():
  text, truncated = truncate_text("abcdef", 6)
  assert text == "abcdef"
  assert truncated is False
  text, truncated = truncate_text("abcdefg", 6)
  assert text == "abcdef"
  assert truncated is True


def test_shape_bash_result_sets_truncated_flag():
  result = shape_bash_result(
      sandbox_name="projects/p/locations/l/reasoningEngines/r/sandboxEnvironments/1",
      result={"stdout": "x" * 50, "stderr": "err", "returncode": 0, "duration_ms": 3},
      max_chars=10,
  )
  assert result["truncated"] is True
  assert len(result["stdout"]) == 10
  assert result["sandbox_name"].endswith("/1")
  assert result["returncode"] == 0
