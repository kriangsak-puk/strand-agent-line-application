"""Standalone smoke test for the agent — no LINE or AgentCore involved.

Usage:
    uv run demo.py "What's the latest version of the AWS Strands Agents SDK?"
"""

import sys

from dotenv import load_dotenv

from agent.core import build_agent


def main() -> None:
    load_dotenv()
    prompt = " ".join(sys.argv[1:]) or "What's today's top news in AI?"
    agent = build_agent()
    agent(prompt)


if __name__ == "__main__":
    main()
