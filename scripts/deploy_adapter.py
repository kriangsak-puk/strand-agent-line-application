#!/usr/bin/env python3
"""Build, push, and deploy the LINE adapter to AWS Lambda + Function URL.

Usage: uv run scripts/deploy_adapter.py

Idempotent: creates the ECR repo / IAM role / Lambda function / Function
URL if they don't exist yet, or pushes a new image and updates them in
place if they do. Prints the Function URL to register as the LINE
webhook (append /callback).

The deployed function always runs with AGENT_BACKEND=agentcore (calling
the AgentCore Runtime deployed by scripts/deploy.py) — a Lambda can't use
"local" mode's per-user in-memory Agent map across invocations anyway,
since each invocation may run in a fresh execution environment.
"""

import base64
import subprocess
import sys
import time
from pathlib import Path

import boto3
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lambda_resources import (
    BASIC_EXECUTION_POLICY_ARN,
    ECR_REPO,
    FUNCTION_NAME,
    LAMBDA_TRUST_POLICY,
    ROLE_NAME,
    ROLE_POLICY_NAME,
    invoke_agentcore_policy,
)

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def ensure_role(iam, account_id: str, region: str, runtime_arn: str) -> str:
    import json

    role_arn = f"arn:aws:iam::{account_id}:role/{ROLE_NAME}"
    runtime_name = runtime_arn.split("/")[-1].rsplit("-", 1)[0]
    try:
        iam.get_role(RoleName=ROLE_NAME)
        print(f"IAM role {ROLE_NAME} already exists.")
    except iam.exceptions.NoSuchEntityException:
        print(f"Creating IAM role {ROLE_NAME}...")
        iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=json.dumps(LAMBDA_TRUST_POLICY))

    iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=BASIC_EXECUTION_POLICY_ARN)
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=ROLE_POLICY_NAME,
        PolicyDocument=json.dumps(invoke_agentcore_policy(runtime_name, region, account_id)),
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

    run(
        ["uv", "export", "--no-dev", "--frozen", "--no-hashes", "-o", "requirements.txt"],
        cwd=ROOT,
    )
    run(
        [
            "docker",
            "build",
            "--platform",
            "linux/arm64",
            # Lambda's container image support rejects the OCI image index
            # (with attestation/SBOM manifests) that Docker's default
            # builder attaches otherwise — it needs a plain single-image
            # manifest.
            "--provenance=false",
            "--sbom=false",
            "-f",
            "Dockerfile.lambda",
            "-t",
            f"{ECR_REPO}:arm64",
            ".",
        ],
        cwd=ROOT,
    )

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


def wait_until_active(lam) -> None:
    for _ in range(60):
        resp = lam.get_function(FunctionName=FUNCTION_NAME)
        config = resp["Configuration"]
        if config["State"] == "Active" and config["LastUpdateStatus"] == "Successful":
            return
        time.sleep(2)
    print("Warning: function did not settle to Active/Successful in time; continuing anyway.")


def deploy_function(lam, image_uri: str, role_arn: str, env_vars: dict) -> None:
    try:
        lam.get_function(FunctionName=FUNCTION_NAME)
        exists = True
    except lam.exceptions.ResourceNotFoundException:
        exists = False

    if exists:
        print(f"Updating existing Lambda function {FUNCTION_NAME}...")
        lam.update_function_code(FunctionName=FUNCTION_NAME, ImageUri=image_uri)
        wait_until_active(lam)
        lam.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Role=role_arn,
            Timeout=60,
            MemorySize=512,
            Environment={"Variables": env_vars},
        )
        wait_until_active(lam)
        return

    print(f"Creating Lambda function {FUNCTION_NAME}...")
    last_error = None
    for attempt in range(6):
        try:
            lam.create_function(
                FunctionName=FUNCTION_NAME,
                PackageType="Image",
                Code={"ImageUri": image_uri},
                Role=role_arn,
                Timeout=60,
                MemorySize=512,
                Architectures=["arm64"],
                Environment={"Variables": env_vars},
            )
            break
        except lam.exceptions.InvalidParameterValueException as e:
            # A freshly created IAM role can take a few seconds to
            # propagate before Lambda can assume it.
            last_error = e
            print(f"  role not ready yet, retrying ({attempt + 1}/6)...")
            time.sleep(5)
    else:
        raise last_error
    wait_until_active(lam)


def ensure_function_url(lam) -> str:
    try:
        resp = lam.get_function_url_config(FunctionName=FUNCTION_NAME)
        print("Function URL already configured.")
    except lam.exceptions.ResourceNotFoundException:
        print("Creating Function URL...")
        resp = lam.create_function_url_config(FunctionName=FUNCTION_NAME, AuthType="NONE")

    try:
        lam.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="AllowPublicFunctionUrl",
            Action="lambda:InvokeFunctionUrl",
            Principal="*",
            FunctionUrlAuthType="NONE",
        )
    except lam.exceptions.ResourceConflictException:
        pass  # permission already granted

    # Function URLs created since ~October 2025 also need a plain
    # lambda:InvokeFunction grant (no FunctionUrlAuthType condition — that
    # param is only valid alongside InvokeFunctionUrl) or public callers
    # get a 403 despite AuthType=NONE and the permission above.
    try:
        lam.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="AllowPublicInvoke",
            Action="lambda:InvokeFunction",
            Principal="*",
        )
    except lam.exceptions.ResourceConflictException:
        pass  # permission already granted

    return resp["FunctionUrl"]


def main() -> None:
    config = dotenv_values(ROOT / ".env")
    region = config.get("AWS_REGION")
    profile = config.get("AWS_PROFILE")
    runtime_arn = config.get("AGENTCORE_AGENT_RUNTIME_ARN")
    line_secret = config.get("LINE_CHANNEL_SECRET")
    line_token = config.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not all([region, profile, runtime_arn, line_secret, line_token]):
        sys.exit(
            "Set AWS_REGION, AWS_PROFILE, AGENTCORE_AGENT_RUNTIME_ARN, LINE_CHANNEL_SECRET, "
            "and LINE_CHANNEL_ACCESS_TOKEN in .env before deploying the adapter."
        )

    session = boto3.Session(profile_name=profile, region_name=region)
    account_id = session.client("sts").get_caller_identity()["Account"]

    iam = session.client("iam")
    ecr = session.client("ecr")
    lam = session.client("lambda")

    role_arn = ensure_role(iam, account_id, region, runtime_arn)
    ensure_ecr_repo(ecr)
    image_uri = build_and_push(ecr, account_id, region)

    env_vars = {
        "LINE_CHANNEL_SECRET": line_secret,
        "LINE_CHANNEL_ACCESS_TOKEN": line_token,
        "AGENT_BACKEND": "agentcore",
        "AGENTCORE_AGENT_RUNTIME_ARN": runtime_arn,
    }
    deploy_function(lam, image_uri, role_arn, env_vars)
    url = ensure_function_url(lam)

    print()
    print("Deployed. LINE webhook URL:")
    print(f"  {url.rstrip('/')}/callback")


if __name__ == "__main__":
    main()
