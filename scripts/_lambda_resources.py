"""Shared resource definitions for scripts/deploy_adapter.py and teardown_adapter.py."""

ECR_REPO = "strand-agent-line-adapter"
FUNCTION_NAME = "strand-agent-line-adapter"
ROLE_NAME = "strand-agent-line-adapter-lambda-role"
ROLE_POLICY_NAME = "invoke-agentcore-runtime"
BASIC_EXECUTION_POLICY_ARN = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

LAMBDA_TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}


def invoke_agentcore_policy(runtime_name: str, region: str, account_id: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvokeAgentRuntime",
                "Effect": "Allow",
                "Action": "bedrock-agentcore:InvokeAgentRuntime",
                "Resource": f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/{runtime_name}-*",
            }
        ],
    }
