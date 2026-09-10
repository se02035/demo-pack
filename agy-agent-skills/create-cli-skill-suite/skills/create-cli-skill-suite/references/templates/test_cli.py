"""Unit tests for acme_widgets.cli. Mock the SDK client; no live network.

Copy-adapt: replace acme_widgets and assert no live account strings from
verification appear in help JSON.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import acme_widgets.cli as cli


def test_help_exits_zero_without_client(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """help must not construct the SDK client."""

    monkeypatch.setattr(
        cli,
        "make_client",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("help must not construct Client")
        ),
    )
    code = cli.main_with_args(["help"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    names = {item["name"] for item in payload["commands"]}
    assert "widgets.list" in names
    blob = json.dumps(payload)
    assert "acme-widgets" in blob
    # Replace with live ids from verification if any leaked into fixtures:
    assert "@example.com" not in blob


def test_version_skips_client(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--version must not construct the SDK client."""

    monkeypatch.setattr(
        cli,
        "make_client",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("version must not construct Client")
        ),
    )
    with pytest.raises(SystemExit) as ei:
        cli.main_with_args(["--version"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "1.0.0" in out


def test_help_lists_required_flags(capsys: pytest.CaptureFixture[str]) -> None:
    """help JSON lists required env flags and issue ids."""

    cli.main_with_args(["help"])
    payload = json.loads(capsys.readouterr().out)
    listing = next(item for item in payload["commands"] if item["name"] == "widgets.list")
    assert "--env" in listing["required_flags"]
    assert any(issue["id"].startswith("ACME-") for issue in listing["issues"])


def test_api_commands_require_env() -> None:
    """Parser has no hidden env default."""

    parser = cli.build_parser()
    help_args = parser.parse_args(["help"])
    assert getattr(help_args, "env", None) in (None, "")


def test_delete_without_yes_refuses(capsys: pytest.CaptureFixture[str]) -> None:
    """Deletes without --yes must not call the API."""

    code = cli.main_with_args(["--env", "ENV", "widgets", "delete", "NAME"])
    assert code != 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]
    assert payload["issue"] is None
