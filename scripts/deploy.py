#!/usr/bin/env python3
"""Build, push, and deploy the agent to Amazon Bedrock AgentCore Runtime.

Usage: uv run scripts/deploy.py

Idempotent: creates the ECR repo / IAM role / AgentCore Runtime if they
don't exist yet, or pushes a new image and updates the runtime in place
if they do. Writes the resulting ARN into .env.
"""

import base64
import json
import subprocess
import sys
from pathlib import Path

import boto3
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _aws_resources import ECR_REPO, ROLE_NAME, ROLE_POLICY_NAME, RUNTIME_NAME, execution_policy, trust_policy

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def ensure_role(iam, account_id: str, region: str) -> str:
    role_arn = f"arn:aws:iam::{account_id}:role/{ROLE_NAME}"
    try:
        iam.get_role(RoleName=ROLE_NAME)
        print(f"IAM role {ROLE_NAME} already exists.")
    except iam.exceptions.NoSuchEntityException:
        print(f"Creating IAM role {ROLE_NAME}...")
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy(account_id, region)),
        )
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=ROLE_POLICY_NAME,
        PolicyDocument=json.dumps(execution_policy(account_id, region)),
    )
    return role_arn


def ensure_ecr_repo(ecr) -> None:
    try:
        ecr.describe_repositories(repositoryNames=[ECR_REPO])
        print(f"ECR repo {ECR_REPO} already exists.")
    except ecr.exceptions.RepositoryNotFoundException:
        print(f"Creating ECR repo {ECR_REPO}...")
        ecr.create_repository(repositoryName=ECR_REPO)


def build_and_push(ecr, account_id: str, region: str) -> str:
    registry = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
    image_uri = f"{registry}/{ECR_REPO}:latest"

    run(["docker", "build", "--platform", "linux/arm64", "-t", f"{ECR_REPO}:arm64", "."], cwd=ROOT)

    token = ecr.get_authorization_token()["authorizationData"][0]["authorizationToken"]
    user, password = base64.b64decode(token).decode().split(":", 1)
    print("+ docker login", registry)
    subprocess.run(
        ["docker", "login", "--username", user, "--password-stdin", registry],
        input=password.encode(),
        check=True,
    )

    run(["docker", "tag", f"{ECR_REPO}:arm64", image_uri])
    run(["docker", "push", image_uri])
    return image_uri


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


def deploy_runtime(control, image_uri: str, role_arn: str, env_vars: dict) -> str:
    artifact = {"containerConfiguration": {"containerUri": image_uri}}
    existing = find_existing_runtime(control)
    if existing:
        print(f"Updating existing AgentCore Runtime {existing['agentRuntimeId']}...")
        resp = control.update_agent_runtime(
            agentRuntimeId=existing["agentRuntimeId"],
            agentRuntimeArtifact=artifact,
            roleArn=role_arn,
            networkConfiguration={"networkMode": "PUBLIC"},
            environmentVariables=env_vars,
        )
        return resp["agentRuntimeArn"]

    print(f"Creating AgentCore Runtime {RUNTIME_NAME}...")
    resp = control.create_agent_runtime(
        agentRuntimeName=RUNTIME_NAME,
        agentRuntimeArtifact=artifact,
        networkConfiguration={"networkMode": "PUBLIC"},
        roleArn=role_arn,
        lifecycleConfiguration={"idleRuntimeSessionTimeout": 300, "maxLifetime": 1800},
        environmentVariables=env_vars,
    )
    return resp["agentRuntimeArn"]


def update_env_file(arn: str) -> None:
    env_path = ROOT / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    for i, line in enumerate(lines):
        if line.startswith("AGENTCORE_AGENT_RUNTIME_ARN="):
            lines[i] = f"AGENTCORE_AGENT_RUNTIME_ARN={arn}"
            break
    else:
        lines.append(f"AGENTCORE_AGENT_RUNTIME_ARN={arn}")
    env_path.write_text("\n".join(lines) + "\n")
    print(f"Updated .env: AGENTCORE_AGENT_RUNTIME_ARN={arn}")


def main() -> None:
    config = dotenv_values(ROOT / ".env")
    region = config.get("AWS_REGION")
    profile = config.get("AWS_PROFILE")
    if not region or not profile:
        sys.exit("Set AWS_REGION and AWS_PROFILE in .env before deploying.")

    session = boto3.Session(profile_name=profile, region_name=region)
    account_id = session.client("sts").get_caller_identity()["Account"]

    iam = session.client("iam")
    ecr = session.client("ecr")
    control = session.client("bedrock-agentcore-control")

    # Passed through to agent/core.py:_select_model() inside the container.
    candidate_env_vars = {
        "BEDROCK_MODEL_ID": config.get("BEDROCK_MODEL_ID"),
        "GEMINI_KEY": config.get("GEMINI_KEY"),
        "GEMINI_MODEL_ID": config.get("GEMINI_MODEL_ID"),
    }
    env_vars = {k: v for k, v in candidate_env_vars.items() if v}

    role_arn = ensure_role(iam, account_id, region)
    ensure_ecr_repo(ecr)
    image_uri = build_and_push(ecr, account_id, region)
    arn = deploy_runtime(control, image_uri, role_arn, env_vars)
    update_env_file(arn)

    print()
    print("Deployed:", arn)
    print('Set AGENT_BACKEND=agentcore in .env to route the LINE bot to this runtime.')


if __name__ == "__main__":
    main()
