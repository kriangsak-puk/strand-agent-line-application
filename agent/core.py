import os

from strands import Agent

from agent.search_tool import web_search

SYSTEM_PROMPT = (
    "You are a helpful assistant reachable over LINE chat. "
    "Always call the web_search tool before answering any question about "
    "current events, scores, prices, dates, or any other fact that could "
    "have changed recently or that you are not 100% certain of — never "
    "answer from memory alone for these. "
    "The tool's results are short, unstructured snippets scraped from "
    "search result pages: they can jumble multiple items together (e.g. "
    "several match results in one line with no clear labels), so only "
    "state a specific detail (a score, a date, a competition name, etc.) "
    "if it is unambiguously attached to the thing being asked about in "
    "the snippet. Never invent or infer a detail that isn't clearly "
    "there — if the results are ambiguous or don't clearly answer the "
    "question, say so plainly and ask the user to narrow it down (e.g. "
    "which specific match/date/team) rather than guessing. "
    "Keep answers concise, since they are displayed as chat messages."
)


# Cheapest current-generation Claude model on Bedrock. Cross-region
# ("global.") inference profile, same pattern as the Sonnet default.
# Override with the BEDROCK_MODEL_ID env var without touching code.
DEFAULT_BEDROCK_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"

# Cheapest current Gemini tier. Override with GEMINI_MODEL_ID.
DEFAULT_GEMINI_MODEL_ID = "gemini-3.5-flash-lite"


def _select_model():
    """Bedrock by default (model id from BEDROCK_MODEL_ID, or the cheap
    default above); Gemini if GEMINI_KEY is set instead (model id from
    GEMINI_MODEL_ID, or its own cheap default).

    The Gemini path is kept as a fallback in case Bedrock access is ever
    unavailable again (it was, briefly, during account verification —
    see PLAN.md §12), not as the primary path.
    """
    gemini_key = os.environ.get("GEMINI_KEY") or os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        from strands.models.gemini import GeminiModel

        model_id = os.environ.get("GEMINI_MODEL_ID", DEFAULT_GEMINI_MODEL_ID)
        return GeminiModel(client_args={"api_key": gemini_key}, model_id=model_id)

    from strands.models import BedrockModel

    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
    return BedrockModel(model_id=model_id)


def build_agent() -> Agent:
    """Construct a fresh Strands agent with the web-search tool attached.

    This is the single source of truth for agent configuration, imported
    by both the local adapter (agent/respond.py) and the AgentCore
    entrypoint (agentcore_app.py) so the two backends never drift apart.
    """
    return Agent(system_prompt=SYSTEM_PROMPT, tools=[web_search], model=_select_model())
