import json
import os

import boto3
from strands import Agent

from agent.core import build_agent

# Local mode's "session" is just an in-memory per-user Agent map — the
# Agent object's own message list is the conversation memory. Lost on
# process restart; that's fine for development (see PLAN.md §6).
_agents: dict[str, Agent] = {}


def respond_local(user_id: str, text: str) -> str:
    agent = _agents.setdefault(user_id, build_agent())
    result = agent(text)
    return str(result)


def _session_id(user_id: str) -> str:
    # invoke_agent_runtime requires a runtimeSessionId of 33+ characters.
    # LINE user ids are already exactly 33 chars ("U" + 32 hex), but pad
    # deterministically as a safety net in case that ever isn't true.
    return f"line-{user_id}".ljust(33, "0")


def respond_agentcore(user_id: str, text: str) -> str:
    """AgentCore mode's "session" is the runtimeSessionId below — each
    session gets its own dedicated microVM on AgentCore's side, whose
    conversation memory (if any) lives entirely in that container, not
    here (see PLAN.md §6).
    """
    client = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION"))
    response = client.invoke_agent_runtime(
        agentRuntimeArn=os.environ["AGENTCORE_AGENT_RUNTIME_ARN"],
        runtimeSessionId=_session_id(user_id),
        payload=json.dumps({"prompt": text}),
        qualifier="DEFAULT",
    )
    body = response["response"].read()
    return json.loads(body)["result"]
