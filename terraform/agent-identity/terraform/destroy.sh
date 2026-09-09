#!/usr/bin/env bash
# Tear down every Terraform-managed demo asset in this state.
# Usage:
#   ./destroy.sh                         # flags from terraform.tfvars / defaults
#   ./destroy.sh -var=enable_agent_runtime_code=true -var=enable_cloud_run=true \
#     -var=enable_principalset_agents=true -var=enable_principalset_mutate=true
#     (if those flags are not in terraform.tfvars — same flags as last apply)
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .terraform ]]; then
  terraform init
fi

exec terraform destroy "$@"
