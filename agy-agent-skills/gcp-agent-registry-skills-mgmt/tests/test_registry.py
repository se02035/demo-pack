"""Unit tests for registry.py. Mocks ADC and HTTP; no live GCP."""

from __future__ import annotations

import base64
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import registry


def parse(*argv: str) -> SimpleNamespace:
    return registry.build_parser().parse_args(["--project", "p", "--location", "eu", *argv])


def test_cli_requires_project_and_location():
    with pytest.raises(SystemExit):
        registry.build_parser().parse_args(["list"])


def test_search_requires_type_and_query():
    with pytest.raises(SystemExit):
        parse("search")
    with pytest.raises(SystemExit):
        parse("search", "--type", "keyword")


def test_semantic_global_exits_issue_1(capsys):
    args = registry.build_parser().parse_args(
        ["--project", "p", "--location", "global", "search", "--type", "semantic", "--query", "x"]
    )
    with pytest.raises(SystemExit) as ei:
        registry.cmd_search(args, "tok")
    assert ei.value.code == 2
    assert "Issue 1" in capsys.readouterr().err


def test_semantic_us_blocked():
    args = registry.build_parser().parse_args(
        ["--project", "p", "--location", "us", "search", "--type", "semantic", "--query", "x"]
    )
    with pytest.raises(SystemExit) as ei:
        registry.cmd_search(args, "tok")
    assert ei.value.code == 2


def test_semantic_force_proceeds(monkeypatch):
    args = registry.build_parser().parse_args(
        [
            "--project",
            "p",
            "--location",
            "global",
            "search",
            "--type",
            "semantic",
            "--query",
            "x",
            "--force",
        ]
    )
    mock = MagicMock(return_value=(200, {"skills": []}))
    monkeypatch.setattr(registry, "request", mock)
    registry.cmd_search(args, "tok")
    assert mock.call_args.kwargs["params"]["searchType"] == "SEMANTIC"


def test_semantic_eu_sends_search_type(monkeypatch):
    args = parse("search", "--type", "semantic", "--query", "email")
    mock = MagicMock(return_value=(200, {"skills": []}))
    monkeypatch.setattr(registry, "request", mock)
    registry.cmd_search(args, "tok")
    params = mock.call_args.kwargs["params"]
    assert params["searchString"] == "email"
    assert params["searchType"] == "SEMANTIC"
    assert params["filter"] == "state=ACTIVE"
    assert mock.call_args.args[1].endswith("skills:search")


def test_keyword_search_default_filter(monkeypatch):
    args = parse("search", "--type", "keyword", "--query", "kubernetes")
    mock = MagicMock(return_value=(200, {"skills": [{"name": "a"}]}))
    monkeypatch.setattr(registry, "request", mock)
    registry.cmd_search(args, "tok")
    params = mock.call_args.kwargs["params"]
    assert params["searchString"] == "kubernetes"
    assert params["searchType"] == "KEYWORD"
    assert params["filter"] == "state=ACTIVE"


def test_keyword_include_inactive_omits_state_filter(monkeypatch):
    args = parse("search", "--type", "keyword", "--query", "k8s", "--include-inactive")
    mock = MagicMock(return_value=(200, {"skills": []}))
    monkeypatch.setattr(registry, "request", mock)
    registry.cmd_search(args, "tok")
    assert "filter" not in mock.call_args.kwargs["params"]


def test_issue_4_publisher_filter_warns(monkeypatch, capsys):
    args = parse(
        "search",
        "--type",
        "keyword",
        "--query",
        "gke",
        "--filter",
        'publisher="cloud.google.com"',
    )
    monkeypatch.setattr(registry, "request", MagicMock(return_value=(200, {"skills": []})))
    registry.cmd_search(args, "tok")
    err = capsys.readouterr().err
    assert "Issue 4" in err
    assert "name:cloud*" in err
    assert "name:discoveryengine*" in err


def test_issue_4_domain_wildcard_dots_warns(monkeypatch, capsys):
    args = parse("search", "--type", "keyword", "--query", "bigquery AND name:cloud.google.com*")
    monkeypatch.setattr(registry, "request", MagicMock(return_value=(200, {"skills": []})))
    registry.cmd_search(args, "tok")
    err = capsys.readouterr().err
    assert "Warning (Issue 4)" in err
    assert "name:cloud*" in err


def test_issue_4_discoveryengine_domain_wildcard_dots_warns(monkeypatch, capsys):
    args = parse("search", "--type", "keyword", "--query", "agent AND name:discoveryengine.googleapis.com*")
    monkeypatch.setattr(registry, "request", MagicMock(return_value=(200, {"skills": []})))
    registry.cmd_search(args, "tok")
    err = capsys.readouterr().err
    assert "Warning (Issue 4)" in err
    assert "name:discoveryengine*" in err


def test_issue_6_not_operator_warns(monkeypatch, capsys):
    args = parse("search", "--type", "keyword", "--query", "gke NOT autoscaler")
    monkeypatch.setattr(registry, "request", MagicMock(return_value=(200, {"skills": []})))
    registry.cmd_search(args, "tok")
    assert "Issue 6" in capsys.readouterr().err


def test_create_draft_and_base64_payload(monkeypatch, tmp_path):
    zip_path = tmp_path / "skill.zip"
    raw = b"PK\x03\x04fake-zip"
    zip_path.write_bytes(raw)
    args = parse(
        "create",
        "--skill-id",
        "registry-smoke-test",
        "--display-name",
        "Registry Smoke Test",
        "--description",
        "Internal utility skill.",
        "--payload",
        str(zip_path),
    )
    mock = MagicMock(return_value=(200, {"name": "projects/p/locations/eu/skills/private-x"}))
    monkeypatch.setattr(registry, "request", mock)
    registry.cmd_create(args, "tok")
    body = mock.call_args.kwargs["body"]
    assert body["targetState"] == "TARGET_STATE_DRAFT"
    assert body["targetState"] != "TARGET_STATE_ACTIVE"
    assert body["initialRevision"]["archiveUploadSource"]["archiveContent"] == base64.b64encode(raw).decode()
    assert mock.call_args.kwargs["params"]["skillId"] == "registry-smoke-test"
    assert mock.call_args.args[0] == "POST"


def test_activate_patches_revision_then_active(monkeypatch):
    args = parse("activate", "private-foo")
    rev = "projects/p/locations/eu/skills/private-foo/revisions/rev-1"
    calls: list[tuple] = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("body"), kwargs.get("params")))
        if path.endswith("/revisions"):
            return 200, {"skillRevisions": [{"name": rev}]}
        if method == "PATCH":
            return 200, {}
        if path.endswith("/skills/private-foo"):
            return 200, {"name": path, "state": "STATE_ACTIVE"}
        return 200, {}

    monkeypatch.setattr(registry, "request", fake_request)
    registry.cmd_activate(args, "tok")
    patches = [c for c in calls if c[0] == "PATCH"]
    assert patches[0][2] == {"defaultRevision": rev}
    assert patches[0][3] == {"updateMask": "defaultRevision"}
    assert patches[1][2] == {"targetState": "TARGET_STATE_ACTIVE"}
    assert patches[1][3] == {"updateMask": "targetState"}


def test_delete_skill_deletes_revisions_then_container(monkeypatch):
    args = parse("delete-skill", "private-foo")
    rev_name = "projects/p/locations/eu/skills/private-foo/revisions/rev-1"
    calls: list[tuple[str, str]] = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        if method == "GET" and path.endswith("/revisions"):
            return 200, {"skillRevisions": [{"name": rev_name}]}
        if method == "DELETE":
            return 200, {}
        return 200, {}

    monkeypatch.setattr(registry, "request", fake_request)
    registry.cmd_delete_skill(args, "tok")
    assert ("DELETE", rev_name) in calls
    assert ("DELETE", "projects/p/locations/eu/skills/private-foo") in calls
    assert calls.index(("DELETE", rev_name)) < calls.index(
        ("DELETE", "projects/p/locations/eu/skills/private-foo")
    )


def test_delete_skill_polls_revision_lro(monkeypatch):
    args = parse("delete-skill", "private-foo")
    rev_name = "projects/p/locations/eu/skills/private-foo/revisions/rev-1"
    op = "projects/p/locations/eu/operations/op-1"
    seq = {
        "revs": (200, {"skillRevisions": [{"name": rev_name}]}),
        "del_rev": (200, {"name": op}),
        "poll": (200, {"done": True, "name": op}),
        "del_skill": (200, {}),
    }

    def fake_request(method, path, **kwargs):
        if method == "GET" and path.endswith("/revisions"):
            return seq["revs"]
        if method == "DELETE" and path == rev_name:
            return seq["del_rev"]
        if method == "GET" and path == op:
            return seq["poll"]
        if method == "DELETE" and path.endswith("/skills/private-foo"):
            return seq["del_skill"]
        raise AssertionError((method, path))

    monkeypatch.setattr(registry, "request", fake_request)
    monkeypatch.setattr(registry.time, "sleep", lambda *_: None)
    registry.cmd_delete_skill(args, "tok")


def test_adc_token_missing_gcloud(monkeypatch):
    monkeypatch.setattr(
        registry.subprocess,
        "run",
        MagicMock(side_effect=FileNotFoundError()),
    )
    with pytest.raises(SystemExit) as ei:
        registry.adc_token()
    assert "gcloud not found" in str(ei.value)


def test_adc_token_refresh_failed(monkeypatch):
    err = subprocess.CalledProcessError(1, "gcloud", stderr="Reauthentication failed")
    monkeypatch.setattr(registry.subprocess, "run", MagicMock(side_effect=err))
    with pytest.raises(SystemExit) as ei:
        registry.adc_token()
    assert "application-default login" in str(ei.value)


def test_adc_token_empty(monkeypatch):
    monkeypatch.setattr(
        registry.subprocess,
        "run",
        MagicMock(return_value=SimpleNamespace(stdout="  \n")),
    )
    with pytest.raises(SystemExit) as ei:
        registry.adc_token()
    assert "ADC token empty" in str(ei.value)


def test_api_error_system_exit():
    with pytest.raises(SystemExit) as ei:
        registry.die_api(400, {"error": {"status": "INVALID_ARGUMENT", "message": "bad"}})
    assert "HTTP 400" in str(ei.value)
    assert "INVALID_ARGUMENT" in str(ei.value)
    assert "bad" in str(ei.value)


def test_search_http_error(monkeypatch):
    args = parse("search", "--type", "keyword", "--query", "x")
    monkeypatch.setattr(
        registry,
        "request",
        MagicMock(return_value=(400, {"error": {"status": "INVALID_ARGUMENT", "message": "nope"}})),
    )
    with pytest.raises(SystemExit) as ei:
        registry.cmd_search(args, "tok")
    assert "nope" in str(ei.value)


def test_list_default_active_filter(monkeypatch):
    args = parse("list")
    mock = MagicMock(return_value=(200, {"skills": []}))
    monkeypatch.setattr(registry, "request", mock)
    registry.cmd_list(args, "tok")
    assert mock.call_args.kwargs["params"]["filter"] == "state=ACTIVE"


def test_list_order_by_warns_issue_5(monkeypatch, capsys):
    args = parse("list", "--order-by", "createTime")
    monkeypatch.setattr(registry, "request", MagicMock(return_value=(200, {"skills": []})))
    registry.cmd_list(args, "tok")
    assert "Issue 5" in capsys.readouterr().err
