#!/usr/bin/env python3
"""Tear down the AgentCore deployment to stop AWS costs.

Usage:
    uv run scripts/teardown.py            # delete the AgentCore Runtime only
    uv run scripts/teardown.py --all       # also delete the ECR repo and IAM role

The AgentCore Runtime is the only piece that bills for active sessions;
the ECR repo and IAM role are essentially free to leave behind, so the
default just removes the runtime. --all removes everything deploy.py
creates, for a full account cleanup.
"""

import sys
from pathlib import Path

import boto3
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _aws_resources import ECR_REPO, ROLE_NAME, ROLE_POLICY_NAME, RUNTIME_NAME

ROOT = Path(__file__).resolve().parent.parent


def find_existing_runtime(control) -> dict | None:
    next_token = None
    while True:
        kwargs = {"nextToken": next_token} if next_token else {}
        resp = control.list_agent_runtimes(**kwargs)
        for rt in resp.get("agentRuntimes", []):
            if rt["agentRuntimeName"] == RUNTIME_NAME:
                return rt
        next_token = resp.get("nextToken")
        if not next_token:
            return None


def delete_runtime(control) -> None:
    existing = find_existing_runtime(control)
    if not existing:
        print(f"No AgentCore Runtime named {RUNTIME_NAME} found — nothing to delete.")
        return
    print(f"Deleting AgentCore Runtime {existing['agentRuntimeId']}...")
    control.delete_agent_runtime(agentRuntimeId=existing["agentRuntimeId"])
    print("Deleted.")


def delete_ecr_repo(ecr) -> None:
    try:
        ecr.delete_repository(repositoryName=ECR_REPO, force=True)
        print(f"Deleted ECR repo {ECR_REPO}.")
    except ecr.exceptions.RepositoryNotFoundException:
        print(f"ECR repo {ECR_REPO} already gone.")


def delete_role(iam) -> None:
    try:
        iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName=ROLE_POLICY_NAME)
    except iam.exceptions.NoSuchEntityException:
        pass
    try:
        iam.delete_role(RoleName=ROLE_NAME)
        print(f"Deleted IAM role {ROLE_NAME}.")
    except iam.exceptions.NoSuchEntityException:
        print(f"IAM role {ROLE_NAME} already gone.")


def clear_env_arn() -> None:
    """Drop the (now-invalid) runtime ARN and fall back to local mode,
    so the adapter doesn't keep trying to call a deleted runtime."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    lines = env_path.read_text().splitlines()
    lines = [line for line in lines if not line.startswith("AGENTCORE_AGENT_RUNTIME_ARN=")]
    for i, line in enumerate(lines):
        if line.startswith("AGENT_BACKEND="):
            lines[i] = "AGENT_BACKEND=local"
            break
    env_path.write_text("\n".join(lines) + "\n")
    print("Cleared AGENTCORE_AGENT_RUNTIME_ARN and reset AGENT_BACKEND=local in .env.")


def main() -> None:
    full_cleanup = "--all" in sys.argv[1:]

    config = dotenv_values(ROOT / ".env")
    region = config.get("AWS_REGION")
    profile = config.get("AWS_PROFILE")
    if not region or not profile:
        sys.exit("Set AWS_REGION and AWS_PROFILE in .env before running teardown.")

    session = boto3.Session(profile_name=profile, region_name=region)
    control = session.client("bedrock-agentcore-control")

    delete_runtime(control)
    clear_env_arn()

    if full_cleanup:
        delete_ecr_repo(session.client("ecr"))
        delete_role(session.client("iam"))
    else:
        print()
        print("ECR repo and IAM role left in place (cheap to keep, needed for the next deploy).")
        print("Run with --all to remove those too.")


if __name__ == "__main__":
    main()
