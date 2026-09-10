#!/usr/bin/env python3
"""Agent Platform sandbox CLI. argparse facade over agentplatform.Client v1."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal, Sequence

from gcp_agent_sandbox import __version__

API_VERSION = "v1"
DEFAULT_TTL = "3600s"
DEFAULT_WAIT_TIMEOUT_S = 300
LRO_TIMEOUT_S = 300
ACTIVE_TIMEOUT_S = 300
POLL_S = 2.0
SIGNJWT_HINT = (
    "CRUD-10: generate_access_token failed (iam.serviceAccounts.signJwt). "
    "Grant roles/iam.serviceAccountTokenCreator on --service-account to the ADC "
    "principal (the SA resource, not project-wide). That SA also needs "
    "roles/aiplatform.user on the project. ADC OAuth is not a substitute "
    "(401 invalid iss). This skill will not grant IAM."
)

SandboxKind = Literal["code", "shell", "computer-use", "byoc"]
TemplateKind = Literal["shell", "computer-use", "byoc"]


@dataclass(frozen=True)
class IssueBlurb:
    """One known issue surfaced in `help` JSON.

    Attributes:
        id: Stable skill-prefixed issue id (for example ``CRUD-1``).
        workaround: One-line action the caller should take.
    """

    id: str
    workaround: str


@dataclass(frozen=True)
class CommandHelp:
    """Machine-readable help for one CLI command.

    Attributes:
        name: Dotted command name such as ``sandboxes.create``.
        summary: One-line description.
        when: When an agent should pick this command.
        required_flags: Flags that must be present.
        optional_flags: Flags that may be omitted.
        placeholders: Tokens used in the example (never real ids).
        example: Copy-paste invocation with placeholders.
        issues: Known mismatches that apply before running the command.
    """

    name: str
    summary: str
    when: str
    required_flags: tuple[str, ...]
    optional_flags: tuple[str, ...]
    placeholders: tuple[str, ...]
    example: str
    issues: tuple[IssueBlurb, ...]


@dataclass(frozen=True)
class UsageCatalog:
    """Discoverable usage catalog for agent harnesses.

    Attributes:
        commands: All commands implemented by this CLI.
    """

    commands: tuple[CommandHelp, ...]


CRUD_1 = IssueBlurb(
    id="CRUD-1",
    workaround="There is no gcloud sandbox or reasoning-engines CLI; use gcp-agent-sandbox.",
)
CRUD_2 = IssueBlurb(
    id="CRUD-2",
    workaround=(
        "Do not send spec.computer_use_environment (HTTP 400). Create a "
        "computer-use template with internet_access, then a sandbox from that "
        "template with no spec."
    ),
)
CRUD_3 = IssueBlurb(
    id="CRUD-3",
    workaround=(
        "API resource names may use the numeric project number. Pass --project "
        "as the user-stated ID; do not rewrite names returned by the API."
    ),
)
CRUD_6 = IssueBlurb(
    id="CRUD-6",
    workaround=(
        "In europe-west4 (and europe-west1), shell and Computer Use templates "
        "often never become ACTIVE: LRO ends ABORTED (code 10), resource FAILED. "
        "Python code sandboxes in the same region work. Tell the user; do not "
        "fail over to a US endpoint unless they explicitly agree. Print the "
        "operation name. See references/limitations.md."
    ),
)
CRUD_7 = IssueBlurb(
    id="CRUD-7",
    workaround=(
        "Pass --template for shell and computer-use sandboxes, or let this CLI "
        "create one with wait_for_completion=False and wait until ACTIVE. Do not "
        "use the SDK auto-template path."
    ),
)
CRUD_8 = IssueBlurb(
    id="CRUD-8",
    workaround=(
        "Do not pause or resume code-execution sandboxes (HTTP 500). "
        "Pause/resume is for shell and Computer Use only."
    ),
)
CRUD_9 = IssueBlurb(
    id="CRUD-9",
    workaround="Refuse execute_bash on code sandboxes. Use exec code, or a shell sandbox.",
)
CRUD_10 = IssueBlurb(
    id="CRUD-10",
    workaround=SIGNJWT_HINT,
)
CRUD_11 = IssueBlurb(
    id="CRUD-11",
    workaround="Refuse Docker Hub BYOC images. Use an Artifact Registry *.pkg.dev URI.",
)
CRUD_12 = IssueBlurb(
    id="CRUD-12",
    workaround=(
        "On template ABORTED/FAILED, print the operation resource name. "
        "Cloud Logging will not contain ABORTED; do not send the user there "
        "for a root cause."
    ),
)
CRUD_13 = IssueBlurb(
    id="CRUD-13",
    workaround=(
        "Code sandbox spec must be code_execution_environment {}. Do not send "
        "LANGUAGE_PYTHON."
    ),
)
CRUD_5 = IssueBlurb(
    id="CRUD-5",
    workaround="Code sandboxes have no connection_info. CDP is for Computer Use (and shell hostname) only.",
)


def usage_catalog() -> UsageCatalog:
    """Return the command catalog (CRUD + exec + computer-use).

    Returns:
        Catalog used by both ``help`` JSON and argparse descriptions.
    """

    common_req = ("--project", "--location")
    placeholders = (
        "PROJECT_ID",
        "LOCATION",
        "ENGINE",
        "SANDBOX",
        "TEMPLATE",
        "IMAGE_URI",
        "SERVICE_ACCOUNT_EMAIL",
        "CODE",
        "COMMAND",
    )
    issues_all = (CRUD_1, CRUD_3)
    issues_eu_tpl = (CRUD_6, CRUD_12)
    return UsageCatalog(
        commands=(
            CommandHelp(
                name="help",
                summary="Print this catalog as JSON (no GCP credentials or Client).",
                when="Invocation is unclear; run before any mutating command.",
                required_flags=(),
                optional_flags=("--command", "--format"),
                placeholders=(),
                example="gcp-agent-sandbox help",
                issues=(),
            ),
            CommandHelp(
                name="engines.create",
                summary="Create an empty Agent Platform instance (no agent deploy).",
                when="The user asked to create a dedicated sandbox-host engine.",
                required_flags=common_req + ("--display-name",),
                optional_flags=("--description",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "engines create --display-name NAME"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="engines.list",
                summary="List reasoning engines in a location.",
                when="The user named a location and wants to browse engines.",
                required_flags=common_req,
                optional_flags=(),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION engines list"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="engines.get",
                summary="Get one reasoning engine.",
                when="The user named an engine id or full resource name.",
                required_flags=common_req + ("NAME",),
                optional_flags=(),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION engines get ENGINE"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="engines.delete",
                summary="Delete an engine. Requires --yes. Uses force=True after --yes.",
                when="The user asked to tear down a sandbox-host engine.",
                required_flags=common_req + ("NAME", "--yes"),
                optional_flags=(),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "engines delete ENGINE --yes"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="templates.create",
                summary="Create a sandbox environment template (shell, computer-use, or BYOC).",
                when="The user wants a reusable template, especially computer-use with internet egress.",
                required_flags=common_req + ("--engine", "--kind", "--display-name"),
                optional_flags=("--image", "--cpu", "--memory", "--port", "--internet-access"),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "templates create --engine ENGINE --kind shell --display-name NAME"
                ),
                issues=issues_all + issues_eu_tpl + (CRUD_2, CRUD_7, CRUD_11),
            ),
            CommandHelp(
                name="templates.list",
                summary="List templates on an engine.",
                when="The user named an engine and wants existing templates.",
                required_flags=common_req + ("--engine",),
                optional_flags=(),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "templates list --engine ENGINE"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="templates.get",
                summary="Get one template.",
                when="The user named a template id or full resource name.",
                required_flags=common_req + ("NAME",),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "templates get TEMPLATE --engine ENGINE"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="templates.delete",
                summary="Delete a template. Requires --yes.",
                when="The user asked to delete a template after its sandboxes are gone.",
                required_flags=common_req + ("NAME", "--yes"),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "templates delete TEMPLATE --engine ENGINE --yes"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="sandboxes.create",
                summary="Create a sandbox (code, shell, computer-use, or BYOC).",
                when="The user asked to provision a sandbox. Warn that it bills while it exists.",
                required_flags=common_req + ("--engine", "--kind", "--display-name"),
                optional_flags=("--template", "--ttl"),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "sandboxes create --engine ENGINE --kind shell --display-name NAME --ttl 3600s"
                ),
                issues=issues_all + issues_eu_tpl + (CRUD_2, CRUD_7, CRUD_10, CRUD_11, CRUD_13),
            ),
            CommandHelp(
                name="sandboxes.list",
                summary="List sandboxes on an engine.",
                when="The user named an engine and wants current sandboxes.",
                required_flags=common_req + ("--engine",),
                optional_flags=(),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "sandboxes list --engine ENGINE"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="sandboxes.get",
                summary="Get one sandbox, including state and connection_info when present.",
                when="The user named a sandbox id or full resource name.",
                required_flags=common_req + ("NAME",),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "sandboxes get SANDBOX --engine ENGINE"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="sandboxes.pause",
                summary="Pause a running sandbox (keeps disk state). Refuse if kind is code.",
                when="The sandbox is idle and the user wants to cut compute cost. Refuse if kind is code (CRUD-8).",
                required_flags=common_req + ("NAME",),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "sandboxes pause SANDBOX --engine ENGINE"
                ),
                issues=issues_all + (CRUD_8,),
            ),
            CommandHelp(
                name="sandboxes.resume",
                summary="Resume a paused sandbox. Refuse if kind is code.",
                when="The user wants a paused sandbox running again. Refuse if kind is code (CRUD-8).",
                required_flags=common_req + ("NAME",),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "sandboxes resume SANDBOX --engine ENGINE"
                ),
                issues=issues_all + (CRUD_8,),
            ),
            CommandHelp(
                name="sandboxes.delete",
                summary="Delete a sandbox. Requires --yes.",
                when="The user is done with the sandbox.",
                required_flags=common_req + ("NAME", "--yes"),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "sandboxes delete SANDBOX --engine ENGINE --yes"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="sandboxes.wait",
                summary="Poll until a sandbox reaches a state (default STATE_RUNNING) or is gone.",
                when="Create/pause/resume returned before the desired state.",
                required_flags=common_req + ("NAME",),
                optional_flags=("--engine", "--until", "--timeout"),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "sandboxes wait SANDBOX --engine ENGINE --until STATE_RUNNING"
                ),
                issues=issues_all,
            ),
            CommandHelp(
                name="exec.code",
                summary="Run Python in a code-execution sandbox (decode Chunk JSON msg_out).",
                when="The user asked to execute Python in a RUNNING code sandbox.",
                required_flags=common_req + ("NAME", "--code"),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "exec code SANDBOX --engine ENGINE --code CODE"
                ),
                issues=issues_all + (CRUD_9, CRUD_13),
            ),
            CommandHelp(
                name="exec.bash",
                summary="Run bash in a shell sandbox (caller ADC, no JWT).",
                when="The user asked to run a shell command in a RUNNING shell sandbox.",
                required_flags=common_req + ("NAME", "--command"),
                optional_flags=("--engine", "--cwd"),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "exec bash SANDBOX --engine ENGINE --command COMMAND"
                ),
                issues=issues_all + issues_eu_tpl + (CRUD_9,),
            ),
            CommandHelp(
                name="cu.health",
                summary="GET / on a Computer Use sandbox (JWT required).",
                when="The user asked to check Computer Use browser health.",
                required_flags=common_req + ("NAME", "--service-account"),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "cu health SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL"
                ),
                issues=issues_all + issues_eu_tpl + (CRUD_5, CRUD_10),
            ),
            CommandHelp(
                name="cu.tabs",
                summary="GET /tabs on a Computer Use sandbox.",
                when="The user asked to list browser tabs.",
                required_flags=common_req + ("NAME", "--service-account"),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "cu tabs SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL"
                ),
                issues=issues_all + (CRUD_10,),
            ),
            CommandHelp(
                name="cu.cdp",
                summary="POST /cdp (default Page.navigate to example.com).",
                when="The user asked to drive the Computer Use browser via CDP HTTP.",
                required_flags=common_req + ("NAME", "--service-account"),
                optional_flags=("--engine", "--cdp-command", "--url"),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "cu cdp SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL"
                ),
                issues=issues_all + (CRUD_10,),
            ),
            CommandHelp(
                name="cu.ws",
                summary="Print CDP websocket URL (not the JWT / Sec-WebSocket-Protocol value).",
                when="The user or Playwright needs connect_over_cdp.",
                required_flags=common_req + ("NAME", "--service-account"),
                optional_flags=("--engine",),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "cu ws SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL"
                ),
                issues=issues_all + (CRUD_10,),
            ),
            CommandHelp(
                name="cu.playwright",
                summary="Playwright chromium.connect_over_cdp and print page title (optional extra).",
                when="The user asked to verify Computer Use with Playwright in US.",
                required_flags=common_req + ("NAME", "--service-account"),
                optional_flags=("--engine", "--url"),
                placeholders=placeholders,
                example=(
                    "gcp-agent-sandbox --project PROJECT_ID --location LOCATION "
                    "cu playwright SANDBOX --engine ENGINE --service-account SERVICE_ACCOUNT_EMAIL"
                ),
                issues=issues_all + issues_eu_tpl + (CRUD_10,),
            ),
        )
    )


def make_client(project: str, location: str) -> Any:
    """Construct ``agentplatform.Client`` on API v1.

    Args:
        project: User-stated GCP project id.
        location: Agent Platform region.

    Returns:
        An ``agentplatform.Client``.

    Raises:
        SystemExit: The SDK extra is not installed.
    """

    try:
        import agentplatform
    except ImportError as exc:
        raise SystemExit(
            "Install the gcp-agent-sandbox package "
            "(python3 -m pip install -e <path-to-gcp-agent-sandbox>)."
        ) from exc
    return agentplatform.Client(
        project=project,
        location=location,
        http_options={"api_version": API_VERSION},
    )


def emit(obj: object) -> None:
    """Write JSON to stdout.

    Args:
        obj: JSON-serializable value.
    """

    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def jsonable(obj: Any) -> Any:
    """Convert SDK models to JSON-safe dicts (not for execute_code Chunks).

    Args:
        obj: Runtime wrapper, pydantic model, or primitive.

    Returns:
        JSON-serializable value.
    """

    if obj is None:
        return None
    api_resource = getattr(obj, "api_resource", None)
    if api_resource is not None:
        return jsonable(api_resource)
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump(mode="json", exclude_none=True)
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(item) for item in obj]
    return obj


def require_project_location(args: argparse.Namespace) -> None:
    """Require ``--project`` and ``--location`` on API commands.

    Args:
        args: Parsed CLI namespace.

    Raises:
        SystemExit: Either flag is missing. There are no defaults.
    """

    if not getattr(args, "project", None) or not getattr(args, "location", None):
        raise SystemExit("--project and --location are required for API commands (no defaults).")


def require_yes(args: argparse.Namespace, resource: str) -> None:
    """Require ``--yes`` on deletes.

    Args:
        args: Parsed CLI namespace.
        resource: Resource name that would be deleted.

    Raises:
        SystemExit: ``--yes`` was omitted.
    """

    if not getattr(args, "yes", False):
        raise SystemExit(f"Refusing to delete {resource} without --yes.")


def require_service_account(args: argparse.Namespace) -> str:
    """Require ``--service-account`` for Computer Use data-plane commands.

    Args:
        args: Parsed CLI namespace.

    Returns:
        Service account email.

    Raises:
        SystemExit: Flag missing. There is no default.
    """

    sa = getattr(args, "service_account", None)
    if not sa:
        raise SystemExit("--service-account is required for Computer Use (no default).")
    return str(sa)


def location_from_name(name: str) -> str | None:
    """Extract the ``locations/{loc}`` segment from a resource name.

    Args:
        name: Full or partial resource name.

    Returns:
        Location id, or ``None`` if the segment is absent.
    """

    parts = name.strip("/").split("/")
    if "locations" in parts:
        idx = parts.index("locations")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def assert_same_location(name: str, location: str) -> None:
    """Reject a resource name whose location does not match ``--location``.

    Args:
        name: Resource name.
        location: CLI ``--location`` value.

    Raises:
        SystemExit: The name is regional and does not match.
    """

    found = location_from_name(name)
    if found is not None and found != location:
        raise SystemExit(
            f"Resource {name} is in location {found}, but --location is {location}. "
            "Sandboxes do not span continents; pass matching --location. "
            "Do not fail over EU traffic to a US endpoint."
        )


def engine_resource(*, project: str, location: str, engine: str) -> str:
    """Resolve an engine id or full name.

    Args:
        project: User-stated project id (used only when ``engine`` is an id).
        location: Expected location.
        engine: Engine id or full resource name.

    Returns:
        Full reasoningEngines resource name.

    Raises:
        SystemExit: The name's location does not match ``location``.
    """

    if "reasoningEngines/" in engine and engine.startswith("projects/"):
        assert_same_location(engine, location)
        return engine
    return f"projects/{project}/locations/{location}/reasoningEngines/{engine}"


def child_resource(
    *,
    project: str,
    location: str,
    collection: str,
    name: str,
    engine: str | None,
) -> str:
    """Resolve a sandbox or template id or full name.

    Args:
        project: User-stated project id.
        location: Expected location.
        collection: ``sandboxEnvironments`` or ``sandboxEnvironmentTemplates``.
        name: Id or full resource name.
        engine: Parent engine id or name when ``name`` is an id.

    Returns:
        Full resource name.

    Raises:
        SystemExit: Location mismatch, or ``--engine`` missing for a bare id.
    """

    if name.startswith("projects/") and "/locations/" in name:
        assert_same_location(name, location)
        return name
    if not engine:
        raise SystemExit(f"Pass a full resource name or --engine plus the {collection} ID.")
    parent = engine_resource(project=project, location=location, engine=engine)
    return f"{parent}/{collection}/{name}"


def require_ar_image(image: str) -> None:
    """Refuse Docker Hub / non-Artifact Registry URIs.

    Args:
        image: Container image URI.

    Raises:
        SystemExit: The URI is not Artifact Registry ``*.pkg.dev``.
    """

    lowered = image.lower()
    if "docker.io/" in lowered or lowered.startswith("docker.io"):
        raise SystemExit(CRUD_11.workaround)
    if ".pkg.dev/" not in image:
        raise SystemExit(CRUD_11.workaround)


def template_create_config(
    *,
    kind: TemplateKind,
    image: str | None,
    cpu: str | None,
    memory: str | None,
    port: int | None,
    internet_access: bool,
) -> dict[str, Any]:
    """Build SDK ``templates.create`` config (always ``wait_for_completion=False``).

    Args:
        kind: ``shell``, ``computer-use``, or ``byoc``.
        image: Artifact Registry URI (BYOC only).
        cpu: Optional CPU request (BYOC).
        memory: Optional memory request (BYOC).
        port: Optional container port (BYOC).
        internet_access: Extra egress for shell; Computer Use always enables it.

    Returns:
        Config dict for ``agentplatform`` templates.create.

    Raises:
        SystemExit: BYOC without ``--image``, or a non-AR image.
    """

    cfg: dict[str, Any] = {"wait_for_completion": False}
    if kind == "byoc":
        if not image:
            raise SystemExit("--kind byoc requires --image IMAGE_URI.")
        require_ar_image(image)
        custom: dict[str, Any] = {"custom_container_spec": {"image_uri": image}}
        if port is not None:
            custom["ports"] = [{"port": port}]
        requests: dict[str, str] = {}
        if cpu:
            requests["cpu"] = cpu
        if memory:
            requests["memory"] = memory
        if requests:
            custom["resources"] = {"requests": requests}
        cfg["custom_container_environment"] = custom
    elif kind == "computer-use":
        cfg["default_container_environment"] = {
            "default_container_category": "DEFAULT_CONTAINER_CATEGORY_COMPUTER_USE"
        }
        cfg["egress_control_config"] = {"internet_access": True}
    else:
        cfg["default_container_environment"] = {
            "default_container_category": "DEFAULT_CONTAINER_CATEGORY_SHELL_SANDBOX"
        }
        if internet_access:
            cfg["egress_control_config"] = {"internet_access": True}
    return cfg


def sandbox_create_spec(kind: SandboxKind) -> dict[str, Any] | None:
    """Build the sandbox ``spec`` for create (W1 / CRUD-2).

    Args:
        kind: Runtime kind.

    Returns:
        Spec dict, or ``None`` for computer-use and BYOC (template only).
    """

    if kind == "code":
        return {"code_execution_environment": {}}
    if kind == "shell":
        return {"shell_environment": {}}
    return None


def infer_kind(env: Any) -> str:
    """Classify a sandbox from its spec (CRUD-8 / CRUD-9).

    Args:
        env: ``SandboxEnvironment`` (or a test double).

    Returns:
        ``code``, ``shell``, or ``computer-use`` (template-backed / no code-or-shell spec).
    """

    spec = getattr(env, "spec", None)
    if spec is not None:
        if getattr(spec, "code_execution_environment", None) is not None:
            return "code"
        if getattr(spec, "shell_environment", None) is not None:
            return "shell"
        if getattr(spec, "computer_use_environment", None) is not None:
            return "computer-use"
    return "computer-use"


def format_lro_error(op: Any) -> str:
    """Format an LRO error including the operation name (CRUD-12).

    Args:
        op: SDK operation object.

    Returns:
        User-facing error string.
    """

    err = getattr(op, "error", None)
    code: object = None
    msg: object = None
    if isinstance(err, dict):
        code = err.get("code")
        msg = err.get("message")
    else:
        code = getattr(err, "code", None)
        msg = getattr(err, "message", err)
    name = str(getattr(op, "name", "") or "")
    return (
        f"Operation failed: code={code} message={msg} operation={name}. "
        "Cloud Logging will not contain ABORTED (CRUD-12). "
        "Do not fail over to another region."
    )


def await_operation(
    operation: Any,
    getter: Callable[[str], Any],
    *,
    timeout_s: int,
    poll_s: float = POLL_S,
) -> Any:
    """Poll an LRO until ``done is True`` or timeout (omitted ``done`` is in progress).

    Args:
        operation: Initial operation.
        getter: ``lambda name: client....get_operation(operation_name=name)``.
        timeout_s: Maximum seconds.
        poll_s: Sleep between polls.

    Returns:
        The last operation. Caller must inspect ``done`` / ``error``.

    Raises:
        SystemExit: ``done is True`` with an error.
    """

    t0 = time.monotonic()
    op = operation
    while True:
        if getattr(op, "done", None) is True:
            if getattr(op, "error", None):
                raise SystemExit(format_lro_error(op))
            return op
        if time.monotonic() - t0 >= timeout_s:
            return op
        name = getattr(op, "name", None)
        if not name:
            raise SystemExit("Operation has no name to poll.")
        time.sleep(poll_s)
        op = getter(str(name))


def wait_template_active(client: Any, name: str, timeout_s: int) -> Any:
    """Poll ``templates.get`` until ACTIVE, or stop on FAILED/DELETED.

    Args:
        client: ``agentplatform.Client``.
        name: Template resource name.
        timeout_s: Maximum seconds.

    Returns:
        The ACTIVE template.

    Raises:
        SystemExit: FAILED/DELETED or timeout.
    """

    t0 = time.monotonic()
    last: Any = None
    while time.monotonic() - t0 < timeout_s:
        last = client.sandboxes.templates.get(name=name)
        state = str(getattr(last, "state", "") or "")
        if "FAILED" in state or "DELETED" in state:
            raise SystemExit(
                f"Template {name} state={state}. Not ACTIVE (CRUD-6 / CRUD-14). "
                "Do not create a sandbox from it. Do not fail over to US."
            )
        if "ACTIVE" in state:
            return last
        time.sleep(POLL_S)
    raise SystemExit(
        f"Timed out waiting for template {name} to become ACTIVE; "
        f"last state={getattr(last, 'state', None)}"
    )


def wait_sandbox_state(
    client: Any,
    name: str,
    until: str,
    timeout_s: int,
) -> Any:
    """Poll ``sandboxes.get`` until ``until`` is in the state string.

    Args:
        client: ``agentplatform.Client``.
        name: Sandbox resource name.
        until: Substring such as ``RUNNING`` or ``PAUSED``.
        timeout_s: Maximum seconds.

    Returns:
        The matching sandbox.

    Raises:
        SystemExit: Timeout.
    """

    t0 = time.monotonic()
    last: Any = None
    while time.monotonic() - t0 < timeout_s:
        last = client.sandboxes.get(name=name)
        state = str(getattr(last, "state", "") or "")
        if until in state:
            return last
        time.sleep(POLL_S)
    raise SystemExit(
        f"Timed out waiting for {name} to reach {until}; last state={getattr(last, 'state', None)}"
    )


def lookup_template_by_display_name(client: Any, engine: str, display_name: str) -> str | None:
    """Find a template by display name after an LRO that omitted ``done``.

    Args:
        client: ``agentplatform.Client``.
        engine: Parent engine name.
        display_name: Template display name.

    Returns:
        Template resource name, or ``None``.
    """

    for tmpl in client.sandboxes.templates.list(name=engine):
        if getattr(tmpl, "display_name", None) == display_name:
            return str(getattr(tmpl, "name", "") or "")
    return None


def lookup_sandbox_by_display_name(client: Any, engine: str, display_name: str) -> str | None:
    """Find a sandbox by display name after an LRO that omitted ``done``.

    Args:
        client: ``agentplatform.Client``.
        engine: Parent engine name.
        display_name: Sandbox display name.

    Returns:
        Sandbox resource name, or ``None``.
    """

    for sb in client.sandboxes.list(name=engine):
        if getattr(sb, "display_name", None) == display_name:
            return str(getattr(sb, "name", "") or "")
    return None


def create_template_active(
    client: Any,
    *,
    engine: str,
    display_name: str,
    kind: TemplateKind,
    image: str | None,
    cpu: str | None,
    memory: str | None,
    port: int | None,
    internet_access: bool,
) -> Any:
    """Create a template and wait until ACTIVE (W3).

    Args:
        client: ``agentplatform.Client``.
        engine: Parent engine name.
        display_name: Template display name.
        kind: Template kind.
        image: BYOC image.
        cpu: BYOC CPU.
        memory: BYOC memory.
        port: BYOC port.
        internet_access: Shell egress flag.

    Returns:
        ACTIVE template object.

    Raises:
        SystemExit: LRO error, FAILED, or timeout.
    """

    cfg = template_create_config(
        kind=kind,
        image=image,
        cpu=cpu,
        memory=memory,
        port=port,
        internet_access=internet_access,
    )
    op = client.sandboxes.templates.create(
        name=engine,
        display_name=display_name,
        config=cfg,
    )
    op = await_operation(
        op,
        lambda n: client.sandboxes.templates.get_sandbox_environment_template_operation(
            operation_name=n
        ),
        timeout_s=LRO_TIMEOUT_S,
    )
    tmpl_name = getattr(getattr(op, "response", None), "name", None)
    if not tmpl_name:
        tmpl_name = lookup_template_by_display_name(client, engine, display_name)
    if not tmpl_name:
        raise SystemExit(
            f"Template {display_name!r} did not return a name (operation={getattr(op, 'name', None)}). "
            + CRUD_6.workaround
        )
    return wait_template_active(client, str(tmpl_name), ACTIVE_TIMEOUT_S)


def refuse_if_code(env: Any, action: str) -> None:
    """Refuse pause/resume/bash on code sandboxes without calling the mutating API.

    Args:
        env: Sandbox resource.
        action: ``pause``, ``resume``, or ``bash``.

    Raises:
        SystemExit: Kind is code.
    """

    if infer_kind(env) == "code":
        if action == "bash":
            raise SystemExit(CRUD_9.workaround)
        raise SystemExit(CRUD_8.workaround)


def decode_execute_code(response: Any) -> dict[str, Any]:
    """Decode ``execute_code`` Chunk JSON to ``msg_out`` (do not model_dump Chunks).

    Args:
        response: ``ExecuteSandboxEnvironmentResponse``.

    Returns:
        Dict with ``exit_status_int``, ``msg_out``, ``msg_err``.

    Raises:
        SystemExit: Missing or undecodable output.
    """

    outputs = list(getattr(response, "outputs", None) or [])
    if not outputs:
        raise SystemExit("execute_code returned no outputs.")
    data = getattr(outputs[0], "data", None)
    payload: Any
    if isinstance(data, bytes):
        payload = json.loads(data.decode("utf-8"))
    elif isinstance(data, str):
        payload = json.loads(data)
    elif isinstance(data, dict):
        payload = data
    else:
        raise SystemExit(f"execute_code output is not JSON bytes (type={type(data).__name__}).")
    if not isinstance(payload, dict):
        raise SystemExit("execute_code JSON was not an object.")
    return {
        "exit_status_int": payload.get("exit_status_int"),
        "msg_out": payload.get("msg_out", ""),
        "msg_err": payload.get("msg_err", ""),
    }


def map_cu_error(exc: BaseException) -> SystemExit:
    """Map JWT / IAM failures to CRUD-10.

    Args:
        exc: SDK or HTTP exception.

    Returns:
        SystemExit with the IAM hint or the original message.
    """

    text = str(exc)
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if (
        status == 403
        or "signJwt" in text
        or "signJwt" in repr(exc)
        or "PERMISSION_DENIED" in text
        or "iam.serviceAccounts.signJwt" in text
    ):
        return SystemExit(SIGNJWT_HINT)
    return SystemExit(f"{type(exc).__name__}: {exc}")


def sandbox_public_view(env: Any) -> dict[str, Any]:
    """Targeted sandbox JSON (no Chunk dumps).

    Args:
        env: Sandbox resource.

    Returns:
        Dict with name, state, kind, expire_time, and connection flags.
    """

    info = getattr(env, "connection_info", None)
    host = getattr(info, "load_balancer_hostname", None) if info is not None else None
    return {
        "name": getattr(env, "name", None),
        "display_name": getattr(env, "display_name", None),
        "state": str(getattr(env, "state", None)),
        "kind": infer_kind(env),
        "expire_time": str(getattr(env, "expire_time", None) or "") or None,
        "sandbox_environment_template": getattr(env, "sandbox_environment_template", None),
        "connection_info": {
            "has_hostname": bool(host),
            "hostname": host,
            "has_routing_token": bool(getattr(info, "routing_token", None) if info is not None else None),
        }
        if info is not None
        else None,
    }


def cmd_help(args: argparse.Namespace) -> None:
    """Print the usage catalog.

    Args:
        args: Parsed ``help`` namespace.
    """

    catalog = usage_catalog()
    topic = getattr(args, "topic", None) or getattr(args, "command_name", None)
    commands: Sequence[CommandHelp] = catalog.commands
    if topic and topic != "help":
        filtered = tuple(
            item
            for item in catalog.commands
            if item.name == topic or item.name.startswith(f"{topic}.")
        )
        if not filtered:
            raise SystemExit(
                f"Unknown help topic {topic!r}. Try: help, engines, templates, sandboxes, exec, cu."
            )
        commands = filtered
    payload = {
        "commands": [
            {
                **{k: v for k, v in asdict(item).items() if k != "issues"},
                "issues": [asdict(issue) for issue in item.issues],
            }
            for item in commands
        ]
    }
    fmt = getattr(args, "format", "json")
    if fmt == "text":
        for item in commands:
            sys.stdout.write(f"{item.name}\n  {item.summary}\n  {item.example}\n")
        return
    emit(payload)


def cmd_engines_create(args: argparse.Namespace, client: Any) -> None:
    """Create an empty reasoning engine.

    Args:
        args: Must include display_name.
        client: ``agentplatform.Client``.
    """

    cfg: dict[str, str] = {"display_name": args.display_name}
    if args.description:
        cfg["description"] = args.description
    runtime = client.runtimes.create(config=cfg)
    resource = runtime.api_resource
    emit(
        {
            "name": resource.name,
            "display_name": getattr(resource, "display_name", None),
        }
    )


def cmd_engines_list(args: argparse.Namespace, client: Any) -> None:
    """List reasoning engines.

    Args:
        args: Unused beyond client location.
        client: ``agentplatform.Client``.
    """

    items = []
    for runtime in client.runtimes.list():
        resource = runtime.api_resource
        items.append(
            {
                "name": getattr(resource, "name", None),
                "display_name": getattr(resource, "display_name", None),
            }
        )
    emit({"engines": items})


def cmd_engines_get(args: argparse.Namespace, client: Any) -> None:
    """Get one reasoning engine.

    Args:
        args: Must include name.
        client: ``agentplatform.Client``.
    """

    name = engine_resource(project=args.project, location=args.location, engine=args.name)
    runtime = client.runtimes.get(name=name)
    emit(jsonable(runtime))


def cmd_engines_delete(args: argparse.Namespace, client: Any) -> None:
    """Delete a reasoning engine with ``force=True`` after ``--yes``.

    Args:
        args: Must include name and yes.
        client: ``agentplatform.Client``.
    """

    name = engine_resource(project=args.project, location=args.location, engine=args.name)
    require_yes(args, name)
    op = client.runtimes.delete(name=name, force=True)
    emit({"name": getattr(op, "name", name), "done": getattr(op, "done", None)})


def cmd_templates_create(args: argparse.Namespace, client: Any) -> None:
    """Create a template and wait until ACTIVE.

    Args:
        args: Template create flags.
        client: ``agentplatform.Client``.
    """

    engine = engine_resource(project=args.project, location=args.location, engine=args.engine)
    kind: TemplateKind = args.kind
    tmpl = create_template_active(
        client,
        engine=engine,
        display_name=args.display_name,
        kind=kind,
        image=args.image,
        cpu=args.cpu,
        memory=args.memory,
        port=args.port,
        internet_access=bool(args.internet_access) or kind == "computer-use",
    )
    emit(jsonable(tmpl))


def cmd_templates_list(args: argparse.Namespace, client: Any) -> None:
    """List templates on an engine.

    Args:
        args: Must include engine.
        client: ``agentplatform.Client``.
    """

    engine = engine_resource(project=args.project, location=args.location, engine=args.engine)
    emit({"templates": [jsonable(item) for item in client.sandboxes.templates.list(name=engine)]})


def cmd_templates_get(args: argparse.Namespace, client: Any) -> None:
    """Get one template.

    Args:
        args: Template name and optional engine.
        client: ``agentplatform.Client``.
    """

    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironmentTemplates",
        name=args.name,
        engine=args.engine,
    )
    emit(jsonable(client.sandboxes.templates.get(name=name)))


def cmd_templates_delete(args: argparse.Namespace, client: Any) -> None:
    """Delete a template.

    Args:
        args: Template name, optional engine, and yes.
        client: ``agentplatform.Client``.
    """

    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironmentTemplates",
        name=args.name,
        engine=args.engine,
    )
    require_yes(args, name)
    op = client.sandboxes.templates.delete(name=name)
    emit({"name": getattr(op, "name", name), "done": getattr(op, "done", None)})


def _resolve_or_create_template(args: argparse.Namespace, client: Any, engine: str, kind: SandboxKind) -> str | None:
    if kind == "code":
        return None
    if args.template:
        name = child_resource(
            project=args.project,
            location=args.location,
            collection="sandboxEnvironmentTemplates",
            name=args.template,
            engine=args.engine,
        )
        wait_template_active(client, name, ACTIVE_TIMEOUT_S)
        return name
    if kind == "byoc":
        raise SystemExit("--kind byoc requires --template.")
    tpl_kind: TemplateKind = "computer-use" if kind == "computer-use" else "shell"
    tmpl = create_template_active(
        client,
        engine=engine,
        display_name=f"{args.display_name}-template",
        kind=tpl_kind,
        image=None,
        cpu=None,
        memory=None,
        port=None,
        internet_access=kind == "computer-use",
    )
    return str(tmpl.name)


def cmd_sandboxes_create(args: argparse.Namespace, client: Any) -> None:
    """Create a sandbox (W1 empty code spec; CU has no spec).

    Args:
        args: Sandbox create flags.
        client: ``agentplatform.Client``.
    """

    engine = engine_resource(project=args.project, location=args.location, engine=args.engine)
    kind: SandboxKind = args.kind
    template = _resolve_or_create_template(args, client, engine, kind)
    spec = sandbox_create_spec(kind)
    cfg: dict[str, Any] = {
        "display_name": args.display_name,
        "ttl": args.ttl,
        "wait_for_completion": False,
    }
    if template:
        cfg["sandbox_environment_template"] = template
    print(
        "Sandboxes bill while they exist. Prefer TTL, pause when idle, delete when done.",
        file=sys.stderr,
    )
    op = client.sandboxes.create(name=engine, spec=spec, config=cfg)
    op = await_operation(
        op,
        lambda n: client.sandboxes._get_sandbox_operation(operation_name=n),
        timeout_s=LRO_TIMEOUT_S,
    )
    sb_name = getattr(getattr(op, "response", None), "name", None)
    if not sb_name:
        sb_name = lookup_sandbox_by_display_name(client, engine, args.display_name)
    if not sb_name:
        raise SystemExit(
            f"Sandbox {args.display_name!r} did not return a name "
            f"(operation={getattr(op, 'name', None)})."
        )
    env = wait_sandbox_state(client, str(sb_name), "RUNNING", DEFAULT_WAIT_TIMEOUT_S)
    emit(sandbox_public_view(env))


def cmd_sandboxes_list(args: argparse.Namespace, client: Any) -> None:
    """List sandboxes on an engine.

    Args:
        args: Must include engine.
        client: ``agentplatform.Client``.
    """

    engine = engine_resource(project=args.project, location=args.location, engine=args.engine)
    emit({"sandboxes": [sandbox_public_view(item) for item in client.sandboxes.list(name=engine)]})


def cmd_sandboxes_get(args: argparse.Namespace, client: Any) -> None:
    """Get one sandbox.

    Args:
        args: Sandbox name and optional engine.
        client: ``agentplatform.Client``.
    """

    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironments",
        name=args.name,
        engine=args.engine,
    )
    emit(sandbox_public_view(client.sandboxes.get(name=name)))


def _pause_or_resume(args: argparse.Namespace, client: Any, action: str, until: str) -> None:
    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironments",
        name=args.name,
        engine=getattr(args, "engine", None),
    )
    env = client.sandboxes.get(name=name)
    refuse_if_code(env, action)
    cfg = {"wait_for_completion": False}
    if action == "pause":
        client.sandboxes.pause(name=name, config=cfg)
    else:
        client.sandboxes.resume(name=name, config=cfg)
    emit(sandbox_public_view(wait_sandbox_state(client, name, until, DEFAULT_WAIT_TIMEOUT_S)))


def cmd_sandboxes_pause(args: argparse.Namespace, client: Any) -> None:
    """Pause a sandbox (shell/CU only).

    Args:
        args: Sandbox name and optional engine.
        client: ``agentplatform.Client``.
    """

    _pause_or_resume(args, client, "pause", "PAUSED")


def cmd_sandboxes_resume(args: argparse.Namespace, client: Any) -> None:
    """Resume a sandbox (shell/CU only).

    Args:
        args: Sandbox name and optional engine.
        client: ``agentplatform.Client``.
    """

    _pause_or_resume(args, client, "resume", "RUNNING")


def cmd_sandboxes_delete(args: argparse.Namespace, client: Any) -> None:
    """Delete a sandbox.

    Args:
        args: Sandbox name, optional engine, and yes.
        client: ``agentplatform.Client``.
    """

    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironments",
        name=args.name,
        engine=args.engine,
    )
    require_yes(args, name)
    op = client.sandboxes.delete(name=name)
    emit({"name": getattr(op, "name", name), "done": getattr(op, "done", None)})


def cmd_sandboxes_wait(args: argparse.Namespace, client: Any) -> None:
    """Poll a sandbox until ``--until`` or gone.

    Args:
        args: Name, optional engine, until, and timeout.
        client: ``agentplatform.Client``.
    """

    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironments",
        name=args.name,
        engine=args.engine,
    )
    until = str(args.until)
    t0 = time.monotonic()
    last: Any = None
    while time.monotonic() - t0 < int(args.timeout):
        try:
            last = client.sandboxes.get(name=name)
        except Exception as exc:
            text = str(exc)
            if until == "gone" and ("404" in text or "NotFound" in type(exc).__name__):
                emit({"name": name, "state": "gone"})
                return
            raise SystemExit(f"{type(exc).__name__}: {exc}") from exc
        state = str(getattr(last, "state", "") or "")
        if until != "gone" and until.replace("STATE_", "") in state:
            emit(sandbox_public_view(last))
            return
        time.sleep(POLL_S)
    raise SystemExit(
        f"Timed out waiting for {name} to reach {until}; last state={getattr(last, 'state', None)}"
    )


def cmd_exec_code(args: argparse.Namespace, client: Any) -> None:
    """Run Python via ``execute_code``.

    Args:
        args: Sandbox name and ``--code``.
        client: ``agentplatform.Client``.
    """

    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironments",
        name=args.name,
        engine=args.engine,
    )
    env = client.sandboxes.get(name=name)
    if infer_kind(env) != "code":
        raise SystemExit("exec code is only for code-execution sandboxes.")
    try:
        response = client.sandboxes.execute_code(name=name, input_data={"code": args.code})
    except Exception as exc:
        text = str(exc)
        if "404" in text or "NotFound" in type(exc).__name__:
            client.sandboxes.get(name=name)
            response = client.sandboxes.execute_code(name=name, input_data={"code": args.code})
        else:
            raise SystemExit(f"{type(exc).__name__}: {exc}") from exc
    payload = decode_execute_code(response)
    emit(payload)
    status = payload.get("exit_status_int")
    if status not in (0, None, "0"):
        raise SystemExit(int(status) if isinstance(status, int) else 1)


def cmd_exec_bash(args: argparse.Namespace, client: Any) -> None:
    """Run bash via ``execute_bash``.

    Args:
        args: Sandbox name and ``--command``.
        client: ``agentplatform.Client``.
    """

    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironments",
        name=args.name,
        engine=args.engine,
    )
    env = client.sandboxes.get(name=name)
    refuse_if_code(env, "bash")
    if infer_kind(env) != "shell":
        raise SystemExit("exec bash is only for shell sandboxes (CRUD-9).")
    kwargs: dict[str, Any] = {"name": name, "command": args.command}
    if args.cwd:
        kwargs["cwd"] = args.cwd
    result = client.sandboxes.execute_bash(**kwargs)
    emit(result)
    if int(result.get("returncode", 0) or 0) != 0:
        raise SystemExit(int(result.get("returncode") or 1))


def _cu_env(args: argparse.Namespace, client: Any) -> Any:
    name = child_resource(
        project=args.project,
        location=args.location,
        collection="sandboxEnvironments",
        name=args.name,
        engine=args.engine,
    )
    env = client.sandboxes.get(name=name)
    if infer_kind(env) == "code":
        raise SystemExit(CRUD_5.workaround)
    if not getattr(env, "connection_info", None):
        raise SystemExit("Sandbox has no connection_info; Computer Use data plane cannot run.")
    return env


def _cu_token(client: Any, sa: str) -> str:
    try:
        return str(client.sandboxes.generate_access_token(sa))
    except Exception as exc:
        raise map_cu_error(exc) from exc


def cmd_cu_health(args: argparse.Namespace, client: Any) -> None:
    """GET / on the Computer Use proxy.

    Args:
        args: Sandbox + service account.
        client: ``agentplatform.Client``.
    """

    env = _cu_env(args, client)
    token = _cu_token(client, require_service_account(args))
    try:
        resp = client.sandboxes.send_command(
            http_method="GET",
            access_token=token,
            sandbox_environment=env,
            path="/",
        )
    except Exception as exc:
        raise map_cu_error(exc) from exc
    emit({"status_code": getattr(resp, "status_code", None), "body": getattr(resp, "body", None)})


def cmd_cu_tabs(args: argparse.Namespace, client: Any) -> None:
    """GET /tabs.

    Args:
        args: Sandbox + service account.
        client: ``agentplatform.Client``.
    """

    env = _cu_env(args, client)
    token = _cu_token(client, require_service_account(args))
    try:
        resp = client.sandboxes.send_command(
            http_method="GET",
            access_token=token,
            sandbox_environment=env,
            path="/tabs",
        )
    except Exception as exc:
        raise map_cu_error(exc) from exc
    emit({"status_code": getattr(resp, "status_code", None), "body": getattr(resp, "body", None)})


def cmd_cu_cdp(args: argparse.Namespace, client: Any) -> None:
    """POST /cdp.

    Args:
        args: Sandbox, service account, optional command/url.
        client: ``agentplatform.Client``.
    """

    env = _cu_env(args, client)
    token = _cu_token(client, require_service_account(args))
    command = args.cdp_command or "Page.navigate"
    url = args.url or "https://example.com"
    body = {"command": command, "params": {"url": url} if command == "Page.navigate" else {}}
    try:
        resp = client.sandboxes.send_command(
            http_method="POST",
            access_token=token,
            sandbox_environment=env,
            path="/cdp",
            request_dict=body,
        )
    except Exception as exc:
        raise map_cu_error(exc) from exc
    emit({"status_code": getattr(resp, "status_code", None), "body": getattr(resp, "body", None)})


def cmd_cu_ws(args: argparse.Namespace, client: Any) -> None:
    """Print CDP websocket URL without the JWT header value.

    Args:
        args: Sandbox + service account.
        client: ``agentplatform.Client``.
    """

    env = _cu_env(args, client)
    sa = require_service_account(args)
    try:
        ws_url, headers = client.sandboxes.generate_browser_ws_headers(
            sandbox_environment=env, service_account_email=sa
        )
    except Exception as exc:
        raise map_cu_error(exc) from exc
    emit({"url": ws_url, "header_keys": list(headers.keys())})


def cmd_cu_playwright(args: argparse.Namespace, client: Any) -> None:
    """Attach Playwright over CDP and print the page title.

    Args:
        args: Sandbox, service account, optional url.
        client: ``agentplatform.Client``.
    """

    env = _cu_env(args, client)
    sa = require_service_account(args)
    url = args.url or "https://example.com"
    try:
        ws_url, headers = client.sandboxes.generate_browser_ws_headers(
            sandbox_environment=env, service_account_email=sa
        )
    except Exception as exc:
        raise map_cu_error(exc) from exc
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is optional. pip install playwright && playwright install chromium. "
            f"CDP url is available via `cu ws` ({ws_url[:80]}…)."
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws_url, headers=headers, timeout=60_000)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        title = page.title()
        browser.close()
    emit({"playwright": True, "title": title, "url": url})


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser from the usage catalog.

    Returns:
        Argument parser. ``--project`` / ``--location`` are optional here so
        ``help`` can run without them; API commands still require both.
    """

    catalog = usage_catalog()
    descriptions = {item.name: item.summary for item in catalog.commands}
    parser = argparse.ArgumentParser(
        prog="gcp-agent-sandbox",
        description="Agent Platform sandbox helper (agentplatform.Client v1).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Print package version (no GCP credentials or Client).",
    )
    parser.add_argument("--project", help="GCP project ID the user stated (no default).")
    parser.add_argument("--location", help="Agent Platform region the user stated (no default).")
    sub = parser.add_subparsers(dest="group", required=True)

    hp = sub.add_parser("help", help=descriptions["help"])
    hp.add_argument("topic", nargs="?", help="engines | templates | sandboxes | exec | cu | dotted command")
    hp.add_argument("--command", dest="command_name", help="Same as topic.")
    hp.add_argument("--format", choices=("json", "text"), default="json")
    hp.set_defaults(func=cmd_help)

    engines = sub.add_parser("engines")
    eng_sub = engines.add_subparsers(dest="action", required=True)
    p = eng_sub.add_parser("create", help=descriptions["engines.create"])
    p.add_argument("--display-name", required=True)
    p.add_argument("--description")
    p.set_defaults(func=cmd_engines_create)
    p = eng_sub.add_parser("list", help=descriptions["engines.list"])
    p.set_defaults(func=cmd_engines_list)
    p = eng_sub.add_parser("get", help=descriptions["engines.get"])
    p.add_argument("name")
    p.set_defaults(func=cmd_engines_get)
    p = eng_sub.add_parser("delete", help=descriptions["engines.delete"])
    p.add_argument("name")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_engines_delete)

    templates = sub.add_parser("templates")
    tpl_sub = templates.add_subparsers(dest="action", required=True)
    p = tpl_sub.add_parser("create", help=descriptions["templates.create"])
    p.add_argument("--engine", required=True)
    p.add_argument("--kind", required=True, choices=("shell", "computer-use", "byoc"))
    p.add_argument("--display-name", required=True)
    p.add_argument("--image", help="Artifact Registry URI (BYOC).")
    p.add_argument("--cpu")
    p.add_argument("--memory")
    p.add_argument("--port", type=int)
    p.add_argument("--internet-access", action="store_true")
    p.set_defaults(func=cmd_templates_create)
    p = tpl_sub.add_parser("list", help=descriptions["templates.list"])
    p.add_argument("--engine", required=True)
    p.set_defaults(func=cmd_templates_list)
    p = tpl_sub.add_parser("get", help=descriptions["templates.get"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.set_defaults(func=cmd_templates_get)
    p = tpl_sub.add_parser("delete", help=descriptions["templates.delete"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_templates_delete)

    sandboxes = sub.add_parser("sandboxes")
    sb_sub = sandboxes.add_subparsers(dest="action", required=True)
    p = sb_sub.add_parser("create", help=descriptions["sandboxes.create"])
    p.add_argument("--engine", required=True)
    p.add_argument("--kind", required=True, choices=("code", "shell", "computer-use", "byoc"))
    p.add_argument("--display-name", required=True)
    p.add_argument("--template")
    p.add_argument("--ttl", default=DEFAULT_TTL)
    p.set_defaults(func=cmd_sandboxes_create)
    p = sb_sub.add_parser("list", help=descriptions["sandboxes.list"])
    p.add_argument("--engine", required=True)
    p.set_defaults(func=cmd_sandboxes_list)
    p = sb_sub.add_parser("get", help=descriptions["sandboxes.get"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.set_defaults(func=cmd_sandboxes_get)
    p = sb_sub.add_parser("pause", help=descriptions["sandboxes.pause"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.set_defaults(func=cmd_sandboxes_pause)
    p = sb_sub.add_parser("resume", help=descriptions["sandboxes.resume"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.set_defaults(func=cmd_sandboxes_resume)
    p = sb_sub.add_parser("delete", help=descriptions["sandboxes.delete"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_sandboxes_delete)
    p = sb_sub.add_parser("wait", help=descriptions["sandboxes.wait"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.add_argument(
        "--until",
        default="STATE_RUNNING",
        choices=("STATE_RUNNING", "STATE_PAUSED", "gone"),
    )
    p.add_argument("--timeout", type=int, default=DEFAULT_WAIT_TIMEOUT_S)
    p.set_defaults(func=cmd_sandboxes_wait)

    ex = sub.add_parser("exec")
    ex_sub = ex.add_subparsers(dest="action", required=True)
    p = ex_sub.add_parser("code", help=descriptions["exec.code"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.add_argument("--code", required=True)
    p.set_defaults(func=cmd_exec_code)
    p = ex_sub.add_parser("bash", help=descriptions["exec.bash"])
    p.add_argument("name")
    p.add_argument("--engine")
    p.add_argument("--command", required=True)
    p.add_argument("--cwd")
    p.set_defaults(func=cmd_exec_bash)

    cu = sub.add_parser("cu")
    cu_sub = cu.add_subparsers(dest="action", required=True)
    for action, help_key, func in (
        ("health", "cu.health", cmd_cu_health),
        ("tabs", "cu.tabs", cmd_cu_tabs),
        ("cdp", "cu.cdp", cmd_cu_cdp),
        ("ws", "cu.ws", cmd_cu_ws),
        ("playwright", "cu.playwright", cmd_cu_playwright),
    ):
        p = cu_sub.add_parser(action, help=descriptions[help_key])
        p.add_argument("name")
        p.add_argument("--engine")
        p.add_argument("--service-account")
        if action in ("cdp", "playwright"):
            p.add_argument("--url")
        if action == "cdp":
            p.add_argument("--cdp-command")
        p.set_defaults(func=func)
    return parser


def main_with_args(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector without the program name. ``None`` uses ``sys.argv``.

    Returns:
        Process exit code (0 on success).
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.group == "help":
        cmd_help(args)
        return 0
    require_project_location(args)
    client = make_client(str(args.project), str(args.location))
    func = getattr(args, "func")
    func(args, client)
    return 0


def main() -> None:
    """Entrypoint."""

    try:
        raise SystemExit(main_with_args())
    except BrokenPipeError:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
