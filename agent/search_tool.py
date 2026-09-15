from ddgs import DDGS
from strands import tool


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo and return the top results.

    Use this when a question needs current or factual information you are
    not certain about. Requires no API key.

    Args:
        query: What to search for.
        max_results: How many results to return.
    """
    results = DDGS().text(query, max_results=max_results)
    if not results:
        return "No results found."
    return "\n".join(
        f"- {r.get('title')}: {r.get('href')}\n  {r.get('body', '')}"
        for r in results
    )
