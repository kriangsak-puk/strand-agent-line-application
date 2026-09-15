#!/usr/bin/env python3
"""Tear down the Lambda-deployed adapter.

Usage:
    uv run scripts/teardown_adapter.py         # delete the Lambda function + Function URL
    uv run scripts/teardown_adapter.py --all   # also delete the ECR repo and IAM role

Lambda + Function URL cost ~nothing when idle (pay-per-request), so this
is mostly useful to fully decommission the adapter, not to save money the
way scripts/teardown.py (AgentCore Runtime) does.
"""

import sys
from pathlib import Path

import boto3
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lambda_resources import BASIC_EXECUTION_POLICY_ARN, ECR_REPO, FUNCTION_NAME, ROLE_NAME, ROLE_POLICY_NAME

ROOT = Path(__file__).resolve().parent.parent


def delete_function(lam) -> None:
    try:
        lam.delete_function_url_config(FunctionName=FUNCTION_NAME)
        print("Deleted Function URL config.")
    except lam.exceptions.ResourceNotFoundException:
        pass

    try:
        lam.delete_function(FunctionName=FUNCTION_NAME)
        print(f"Deleted Lambda function {FUNCTION_NAME}.")
    except lam.exceptions.ResourceNotFoundException:
        print(f"Lambda function {FUNCTION_NAME} already gone.")


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
        iam.detach_role_policy(RoleName=ROLE_NAME, PolicyArn=BASIC_EXECUTION_POLICY_ARN)
    except iam.exceptions.NoSuchEntityException:
        pass
    try:
        iam.delete_role(RoleName=ROLE_NAME)
        print(f"Deleted IAM role {ROLE_NAME}.")
    except iam.exceptions.NoSuchEntityException:
        print(f"IAM role {ROLE_NAME} already gone.")


def main() -> None:
    full_cleanup = "--all" in sys.argv[1:]

    config = dotenv_values(ROOT / ".env")
    region = config.get("AWS_REGION")
    profile = config.get("AWS_PROFILE")
    if not region or not profile:
        sys.exit("Set AWS_REGION and AWS_PROFILE in .env before running teardown.")

    session = boto3.Session(profile_name=profile, region_name=region)
    delete_function(session.client("lambda"))

    if full_cleanup:
        delete_ecr_repo(session.client("ecr"))
        delete_role(session.client("iam"))
    else:
        print()
        print("ECR repo and IAM role left in place. Run with --all to remove those too.")


if __name__ == "__main__":
    main()
