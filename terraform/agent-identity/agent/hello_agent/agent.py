"""Hello-world ADK agent used to prove Agent Identity IAM.

Tools call Secret Manager and GCS using Application Default Credentials.
On Agent Runtime / Cloud Run with identity_type=AGENT_IDENTITY those calls
authenticate as the minted SPIFFE principal, not a service account.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.cloud import secretmanager, storage
from vertexai.agent_engines import AdkApp

# Override with DEMO_MODEL without rebuilding the agent source when Agent
# Runtime injects it.
_MODEL = os.environ.get("DEMO_MODEL", "gemini-2.5-flash")


def _access_secret(env_name: str) -> dict:
    resource = os.environ.get(env_name)
    if not resource:
        return {
            "status": "error",
            "error": f"{env_name} is not set",
        }
    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(name=resource)
        payload = response.payload.data.decode("utf-8")
        return {"status": "ok", "secret_payload": payload}
    except Exception as exc:  # noqa: BLE001 — return the IAM/API error to the model
        return {"status": "error", "error": str(exc)}


def read_demo_secret() -> dict:
    """Read the per-principal demo secret (DEMO_SECRET_RESOURCE).

    Terraform grants roles/secretmanager.secretAccessor on this secret to the
    first Agent Runtime principal and the predicted first Cloud Run principal
    only. A later agent is expected to get PERMISSION_DENIED.
    """
    return _access_secret("DEMO_SECRET_RESOURCE")


def read_set_proof_secret() -> dict:
    """Read the principalSet inherit-demo secret (DEMO_SET_SECRET_RESOURCE).

    Bound only to the project Agent Runtime and Cloud Run principalSets, not to
    individual principal:// members.
    """
    return _access_secret("DEMO_SET_SECRET_RESOURCE")


def read_broadcast_secret() -> dict:
    """Read the principalSet mutate-demo secret (DEMO_SET_BROADCAST_RESOURCE).

    Created in a later apply and bound only to principalSets so existing and
    new agents pick up the grant without new per-principal IAM.
    """
    return _access_secret("DEMO_SET_BROADCAST_RESOURCE")


def read_demo_gcs_object() -> dict:
    """Read the demo GCS object bound to the first agents' identities.

    Terraform grants roles/storage.objectViewer on the demo bucket to those
    individual principals only. New agents are expected to get PERMISSION_DENIED.
    """
    bucket_name = os.environ.get("DEMO_BUCKET_NAME")
    object_name = os.environ.get("DEMO_OBJECT_NAME", "hello.txt")
    if not bucket_name:
        return {
            "status": "error",
            "error": "DEMO_BUCKET_NAME is not set",
        }
    try:
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(object_name)
        return {
            "status": "ok",
            "bucket": bucket_name,
            "object": object_name,
            "contents": blob.download_as_text(),
        }
    except Exception as exc:  # noqa: BLE001 — return the IAM/API error to the model
        return {"status": "error", "error": str(exc)}


root_agent = Agent(
    name="hello_agent_identity",
    model=_MODEL,
    instruction=(
        "You are a hello-world agent whose job is to prove GCP Agent Identity. "
        "When asked to read the demo secret, call read_demo_secret and quote "
        "the payload. When asked to read the set-proof secret, call "
        "read_set_proof_secret and quote the payload. When asked to read the "
        "broadcast secret, call read_broadcast_secret and quote the payload. "
        "When asked to read the demo GCS object, call read_demo_gcs_object "
        "and quote the contents. If a tool returns status=error, report the "
        "error verbatim (that is the negative IAM test). You may also answer "
        "general questions using Gemini. Prefer tools over guessing when the "
        "user asks about a secret or bucket."
    ),
    tools=[
        read_demo_secret,
        read_set_proof_secret,
        read_broadcast_secret,
        read_demo_gcs_object,
    ],
)

# Agent Runtime source_code_spec must point at AdkApp (query/stream_query),
# not the raw LlmAgent. Cloud Run's FastAPI loader still uses root_agent.
adk_app = AdkApp(agent=root_agent)
