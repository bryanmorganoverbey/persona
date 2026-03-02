"""
Tool definitions and backends for the goal agent.

Provides web_search (via Brave Search API) and web_fetch (via requests + html2text)
as Anthropic-format tool schemas, plus the execution dispatch logic.
"""

import os
import json
import requests
import html2text

BRAVE_SEARCH_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY", "")
WEB_FETCH_MAX_CHARS = 20_000
WEB_SEARCH_MAX_RESULTS = 5
WEB_FETCH_TIMEOUT = 15
WEB_SEARCH_TIMEOUT = 10

TOOL_DEFINITIONS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for current information. Returns a list of results "
            "with titles, URLs, and snippets. Use this for research tasks that "
            "require up-to-date data like pricing, availability, listings, or news."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch and read the content of a web page. Returns the page content "
            "as clean readable text. Use this to read full articles, listings, "
            "or pages found via web_search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
            },
            "required": ["url"],
        },
    },
]


def _search_brave(query: str) -> str:
    """Execute a web search using Brave Search API."""
    if not BRAVE_SEARCH_API_KEY:
        return json.dumps({
            "error": "BRAVE_SEARCH_API_KEY not configured. Cannot perform web search.",
        })

    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
            },
            params={"q": query, "count": WEB_SEARCH_MAX_RESULTS},
            timeout=WEB_SEARCH_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            })

        if not results:
            return json.dumps({"results": [], "note": "No results found."})

        return json.dumps({"results": results})

    except requests.RequestException as e:
        return json.dumps({"error": f"Search request failed: {e}"})


def _fetch_page(url: str) -> str:
    """Fetch a web page and convert to readable text."""
    try:
        resp = requests.get(
            url,
            timeout=WEB_FETCH_TIMEOUT,
            headers={"User-Agent": "GoalAgent/1.0 (research bot)"},
            allow_redirects=True,
        )
        resp.raise_for_status()

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0
        text = converter.handle(resp.text)

        if len(text) > WEB_FETCH_MAX_CHARS:
            text = text[:WEB_FETCH_MAX_CHARS] + "\n\n[Content truncated at 20,000 characters]"

        return text

    except requests.RequestException as e:
        return json.dumps({"error": f"Failed to fetch {url}: {e}"})


TOOL_HANDLERS = {
    "web_search": lambda inputs: _search_brave(inputs["query"]),
    "web_fetch": lambda inputs: _fetch_page(inputs["url"]),
}


def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch a tool call to the appropriate handler. Returns the result as a string."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    print(f"    Tool call: {name}({json.dumps(inputs, ensure_ascii=False)[:200]})")
    result = handler(inputs)
    print(f"    Tool result: {len(result)} chars")
    return result
