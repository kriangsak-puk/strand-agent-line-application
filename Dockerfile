# AgentCore Runtime requires linux/arm64.
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-dev

COPY agent/ ./agent/
COPY agentcore_app.py ./

EXPOSE 8080

CMD ["uv", "run", "agentcore_app.py"]
