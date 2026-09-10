"""Unit tests for sandbox.py. Mocks agentplatform.Client; no live GCP."""

from __future__ import annotations

import argparse
import json
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import sandbox


def parse(*argv: str) -> argparse.Namespace:
    """Parse CLI args."""
    return sandbox.build_parser().parse_args(list(argv))


class FakeOp:
    """Minimal LRO double."""

    def __init__(
        self,
        name: str,
        *,
        done: bool | None = True,
        error: object | None = None,
        response: object | None = None,
    ) -> None:
        self.name = name
        self.done = done
        self.error = error
        self.response = response


def test_help_exits_zero_without_client(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        sandbox,
        "make_client",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("help must not construct Client")),
    )
    code = sandbox.main_with_args(["help"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    names = {item["name"] for item in payload["commands"]}
    assert "engines.create" in names
    assert "templates.create" in names
    assert "sandboxes.pause" in names
    assert "exec.code" in names
    assert "exec.bash" in names
    assert "cu.health" in names
    assert "cu.playwright" in names
    blob = json.dumps(payload)
    assert "crafty-progress" not in blob
    assert "149377925365" not in blob
    assert "@developer.gserviceaccount.com" not in blob


def test_help_sandboxes_lists_required_flags(capsys: pytest.CaptureFixture[str]) -> None:
    sandbox.main_with_args(["help", "sandboxes"])
    payload = json.loads(capsys.readouterr().out)
    create = next(item for item in payload["commands"] if item["name"] == "sandboxes.create")
    assert "--project" in create["required_flags"]
    assert "--location" in create["required_flags"]
    assert "--engine" in create["required_flags"]
    assert "--kind" in create["required_flags"]
    assert any(issue["id"].startswith("CRUD-") for issue in create["issues"])


def test_api_commands_require_project_and_location() -> None:
    args = sandbox.build_parser().parse_args(["engines", "list"])
    with pytest.raises(SystemExit):
        sandbox.require_project_location(args)


def test_no_default_project_location_or_service_account() -> None:
    parser = sandbox.build_parser()
    help_args = parser.parse_args(["help"])
    assert getattr(help_args, "project", None) in (None, "")
    assert getattr(help_args, "location", None) in (None, "")
    cu = parser.parse_args(["cu", "health", "sb"])
    assert cu.service_account is None


def test_refuse_mixed_location_in_resource_name() -> None:
    with pytest.raises(SystemExit) as ei:
        sandbox.engine_resource(
            project="p",
            location="europe-west4",
            engine="projects/p/locations/us-central1/reasoningEngines/abc",
        )
    assert "europe-west4" in str(ei.value)


def test_engine_id_builds_name_with_project_and_location() -> None:
    name = sandbox.engine_resource(project="my-proj", location="us-central1", engine="eng1")
    assert name == "projects/my-proj/locations/us-central1/reasoningEngines/eng1"


def test_accepts_project_number_in_resource_name() -> None:
    name = sandbox.engine_resource(
        project="my-proj",
        location="us-central1",
        engine="projects/149377925365/locations/us-central1/reasoningEngines/eng1",
    )
    assert name.endswith("/reasoningEngines/eng1")


def test_delete_requires_yes() -> None:
    args = parse("--project", "p", "--location", "us-central1", "engines", "delete", "eng1")
    with pytest.raises(SystemExit) as ei:
        sandbox.cmd_engines_delete(args, MagicMock())
    assert ei.value.code != 0


def test_wait_timeout_default_300() -> None:
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "sandboxes",
        "wait",
        "sb1",
        "--engine",
        "eng1",
    )
    assert args.timeout == 300
    assert args.until == "STATE_RUNNING"


def test_code_spec_is_empty_object() -> None:
    spec = sandbox.sandbox_create_spec("code")
    assert spec == {"code_execution_environment": {}}
    dumped = json.dumps(spec)
    assert "LANGUAGE_PYTHON" not in dumped


def test_shell_spec() -> None:
    assert sandbox.sandbox_create_spec("shell") == {"shell_environment": {}}


def test_computer_use_spec_is_none() -> None:
    assert sandbox.sandbox_create_spec("computer-use") is None


def test_computer_use_template_always_internet() -> None:
    cfg = sandbox.template_create_config(
        kind="computer-use",
        image=None,
        cpu=None,
        memory=None,
        port=None,
        internet_access=False,
    )
    assert cfg["wait_for_completion"] is False
    env = cfg["default_container_environment"]
    assert env["default_container_category"] == "DEFAULT_CONTAINER_CATEGORY_COMPUTER_USE"
    assert cfg["egress_control_config"]["internet_access"] is True
    assert "computer_use_environment" not in cfg


def test_byoc_template_body_and_refuse_docker_hub() -> None:
    cfg = sandbox.template_create_config(
        kind="byoc",
        image="us-docker.pkg.dev/p/r/img:tag",
        cpu="500m",
        memory="1Gi",
        port=8080,
        internet_access=False,
    )
    custom = cfg["custom_container_environment"]
    assert custom["custom_container_spec"]["image_uri"] == "us-docker.pkg.dev/p/r/img:tag"
    assert custom["ports"][0] == {"port": 8080}
    assert custom["resources"]["requests"]["cpu"] == "500m"
    with pytest.raises(SystemExit) as ei:
        sandbox.require_ar_image("docker.io/library/python:3.12-slim")
    assert "pkg.dev" in str(ei.value) or "Docker Hub" in str(ei.value)


def test_decode_execute_code_chunk_json() -> None:
    chunk = SimpleNamespace(data=b'{"exit_status_int":0,"msg_err":"","msg_out":"4\\n"}')
    payload = sandbox.decode_execute_code(SimpleNamespace(outputs=[chunk]))
    assert payload["msg_out"] == "4\n"
    assert payload["exit_status_int"] == 0


def test_map_cu_error_signjwt() -> None:
    err = sandbox.map_cu_error(RuntimeError("403 PERMISSION_DENIED iam.serviceAccounts.signJwt"))
    assert "serviceAccountTokenCreator" in str(err)


def test_infer_kind_code_vs_shell() -> None:
    code = SimpleNamespace(spec=SimpleNamespace(code_execution_environment={}, shell_environment=None))
    shell = SimpleNamespace(spec=SimpleNamespace(code_execution_environment=None, shell_environment={}))
    cu = SimpleNamespace(spec=None, connection_info=object())
    assert sandbox.infer_kind(code) == "code"
    assert sandbox.infer_kind(shell) == "shell"
    assert sandbox.infer_kind(cu) == "computer-use"


def test_pause_refuses_code_without_calling_api() -> None:
    client = MagicMock()
    env = SimpleNamespace(
        name="projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironments/s",
        spec=SimpleNamespace(code_execution_environment={}, shell_environment=None),
        state="STATE_RUNNING",
        display_name="c",
        expire_time=None,
        sandbox_environment_template=None,
        connection_info=None,
    )
    client.sandboxes.get.return_value = env
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "sandboxes",
        "pause",
        env.name,
    )
    with pytest.raises(SystemExit) as ei:
        sandbox.cmd_sandboxes_pause(args, client)
    assert "500" in str(ei.value) or "code" in str(ei.value).lower()
    client.sandboxes.pause.assert_not_called()


def test_exec_bash_refuses_code() -> None:
    client = MagicMock()
    env = SimpleNamespace(
        name="projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironments/s",
        spec=SimpleNamespace(code_execution_environment={}, shell_environment=None),
        state="STATE_RUNNING",
        display_name="c",
        expire_time=None,
        sandbox_environment_template=None,
        connection_info=None,
    )
    client.sandboxes.get.return_value = env
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "exec",
        "bash",
        env.name,
        "--command",
        "pwd",
    )
    with pytest.raises(SystemExit):
        sandbox.cmd_exec_bash(args, client)
    client.sandboxes.execute_bash.assert_not_called()


def test_engines_create_uses_runtime_api_resource_name(capsys: pytest.CaptureFixture[str]) -> None:
    client = MagicMock()
    runtime = SimpleNamespace(
        api_resource=SimpleNamespace(
            name="projects/149377925365/locations/us-central1/reasoningEngines/1",
            display_name="host",
        )
    )
    client.runtimes.create.return_value = runtime
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "engines",
        "create",
        "--display-name",
        "host",
    )
    sandbox.cmd_engines_create(args, client)
    client.runtimes.create.assert_called_once()
    cfg = client.runtimes.create.call_args.kwargs["config"]
    assert cfg["display_name"] == "host"
    assert "agent" not in cfg
    out = json.loads(capsys.readouterr().out)
    assert out["name"].endswith("/reasoningEngines/1")


def test_lro_done_true_with_error_prints_operation_name() -> None:
    op = FakeOp(
        "projects/p/locations/europe-west4/operations/99",
        done=True,
        error=SimpleNamespace(code=10, message="ABORTED"),
    )
    with pytest.raises(SystemExit) as ei:
        sandbox.await_operation(op, lambda _n: op, timeout_s=1, poll_s=0)
    assert "ABORTED" in str(ei.value)
    assert "operations/99" in str(ei.value)


def test_await_operation_treats_missing_done_as_in_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    first = FakeOp("op1", done=None, response=None)
    second = FakeOp(
        "op1",
        done=True,
        response=SimpleNamespace(name="projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironmentTemplates/t"),
    )
    calls = {"n": 0}

    def getter(_name: str) -> FakeOp:
        calls["n"] += 1
        return second

    monkeypatch.setattr(time, "sleep", lambda _s: None)
    result = sandbox.await_operation(first, getter, timeout_s=30, poll_s=0)
    assert result.done is True
    assert calls["n"] == 1


def test_sandboxes_create_code_sends_empty_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    env = SimpleNamespace(
        name="projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironments/s",
        spec=SimpleNamespace(code_execution_environment={}, shell_environment=None),
        state="STATE_RUNNING",
        display_name="code",
        expire_time=None,
        sandbox_environment_template=None,
        connection_info=None,
    )
    op = FakeOp(
        "projects/p/locations/us-central1/operations/1",
        done=True,
        response=SimpleNamespace(name=env.name),
    )
    client.sandboxes.create.return_value = op
    client.sandboxes.get.return_value = env
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "sandboxes",
        "create",
        "--engine",
        "e",
        "--kind",
        "code",
        "--display-name",
        "code",
    )
    sandbox.cmd_sandboxes_create(args, client)
    spec = client.sandboxes.create.call_args.kwargs["spec"]
    cfg = client.sandboxes.create.call_args.kwargs["config"]
    assert spec == {"code_execution_environment": {}}
    assert cfg["wait_for_completion"] is False
    assert "computer_use_environment" not in (spec or {})


def test_sandboxes_create_computer_use_omits_spec_and_requires_active_template() -> None:
    client = MagicMock()
    tmpl = SimpleNamespace(
        name="projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironmentTemplates/t",
        state="ACTIVE",
        display_name="cu-tpl",
    )
    env = SimpleNamespace(
        name="projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironments/s",
        spec=None,
        state="STATE_RUNNING",
        display_name="cu",
        expire_time=None,
        sandbox_environment_template=tmpl.name,
        connection_info=SimpleNamespace(load_balancer_hostname="x.sandbox.vertexai.goog", routing_token="tok"),
    )
    client.sandboxes.templates.get.return_value = tmpl
    client.sandboxes.create.return_value = FakeOp(
        "op",
        done=True,
        response=SimpleNamespace(name=env.name),
    )
    client.sandboxes.get.return_value = env
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "sandboxes",
        "create",
        "--engine",
        "e",
        "--kind",
        "computer-use",
        "--display-name",
        "cu",
        "--template",
        "t",
    )
    sandbox.cmd_sandboxes_create(args, client)
    spec = client.sandboxes.create.call_args.kwargs["spec"]
    cfg = client.sandboxes.create.call_args.kwargs["config"]
    assert spec is None
    assert cfg["sandbox_environment_template"].endswith("/sandboxEnvironmentTemplates/t")
    assert "computer_use_environment" not in cfg


def test_template_create_waits_until_active(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    tmpl_name = "projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironmentTemplates/t"
    op = FakeOp("op-tpl", done=True, response=SimpleNamespace(name=tmpl_name))
    client.sandboxes.templates.create.return_value = op
    client.sandboxes.templates.get.side_effect = [
        SimpleNamespace(name=tmpl_name, state="PROVISIONING", display_name="shell"),
        SimpleNamespace(name=tmpl_name, state="ACTIVE", display_name="shell"),
    ]
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "templates",
        "create",
        "--engine",
        "e",
        "--kind",
        "shell",
        "--display-name",
        "shell",
    )
    sandbox.cmd_templates_create(args, client)
    cfg = client.sandboxes.templates.create.call_args.kwargs["config"]
    assert cfg["wait_for_completion"] is False
    assert client.sandboxes.templates.get.call_count == 2


def test_template_create_refuses_sandbox_while_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    tmpl_name = "projects/p/locations/europe-west4/reasoningEngines/e/sandboxEnvironmentTemplates/t"
    client.sandboxes.templates.create.return_value = FakeOp(
        "projects/p/locations/europe-west4/operations/1",
        done=True,
        response=SimpleNamespace(name=tmpl_name),
    )
    client.sandboxes.templates.get.return_value = SimpleNamespace(
        name=tmpl_name, state="FAILED", display_name="shell"
    )
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    args = parse(
        "--project",
        "p",
        "--location",
        "europe-west4",
        "templates",
        "create",
        "--engine",
        "e",
        "--kind",
        "shell",
        "--display-name",
        "shell",
    )
    with pytest.raises(SystemExit) as ei:
        sandbox.cmd_templates_create(args, client)
    assert "FAILED" in str(ei.value)


def test_exec_code_prints_msg_out(capsys: pytest.CaptureFixture[str]) -> None:
    client = MagicMock()
    env = SimpleNamespace(
        name="projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironments/s",
        spec=SimpleNamespace(code_execution_environment={}, shell_environment=None),
        state="STATE_RUNNING",
        display_name="c",
        expire_time=None,
        sandbox_environment_template=None,
        connection_info=None,
    )
    client.sandboxes.get.return_value = env
    client.sandboxes.execute_code.return_value = SimpleNamespace(
        outputs=[SimpleNamespace(data=b'{"exit_status_int":0,"msg_err":"","msg_out":"4\\n"}')]
    )
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "exec",
        "code",
        env.name,
        "--code",
        "print(2+2)",
    )
    sandbox.cmd_exec_code(args, client)
    kwargs = client.sandboxes.execute_code.call_args.kwargs
    assert kwargs["input_data"] == {"code": "print(2+2)"}
    out = json.loads(capsys.readouterr().out)
    assert out["msg_out"] == "4\n"


def test_cu_health_maps_403(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    env = SimpleNamespace(
        name="projects/p/locations/us-central1/reasoningEngines/e/sandboxEnvironments/s",
        spec=None,
        state="STATE_RUNNING",
        display_name="cu",
        expire_time=None,
        sandbox_environment_template="t",
        connection_info=SimpleNamespace(load_balancer_hostname="h", routing_token="r"),
    )
    client.sandboxes.get.return_value = env
    client.sandboxes.generate_access_token.side_effect = RuntimeError("403 signJwt PERMISSION_DENIED")
    args = parse(
        "--project",
        "p",
        "--location",
        "us-central1",
        "cu",
        "health",
        env.name,
        "--service-account",
        "sa@example.iam.gserviceaccount.com",
    )
    with pytest.raises(SystemExit) as ei:
        sandbox.cmd_cu_health(args, client)
    assert "serviceAccountTokenCreator" in str(ei.value)
    client.sandboxes.send_command.assert_not_called()


def test_main_api_constructs_v1_client(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_client(project: str, location: str) -> MagicMock:
        seen["project"] = project
        seen["location"] = location
        client = MagicMock()
        client.runtimes.list.return_value = []
        return client

    monkeypatch.setattr(sandbox, "make_client", fake_client)
    code = sandbox.main_with_args(
        ["--project", "p", "--location", "europe-west4", "engines", "list"]
    )
    assert code == 0
    assert seen == {"project": "p", "location": "europe-west4"}
