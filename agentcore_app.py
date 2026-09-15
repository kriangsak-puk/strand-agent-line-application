from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agent.core import build_agent

app = BedrockAgentCoreApp()
agent = build_agent()


@app.entrypoint
def invoke(payload: dict) -> dict:
    prompt = payload.get("prompt", "")
    result = agent(prompt)
    return {"result": str(result)}


if __name__ == "__main__":
    app.run()
