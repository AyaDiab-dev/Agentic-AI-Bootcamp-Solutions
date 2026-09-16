"""
Module 5 Lab — MCP SERVER

Expose two tools over MCP:
1. read_data(key)
2. web_search(query)

The server validates all inputs and keeps API secrets server-side.
Search runs in mock mode by default, with optional Tavily support.
"""

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("jhf-tools")


COUNTRIES = {
    "JO": {"country": "Jordan", "capital": "Amman"},
    "EG": {"country": "Egypt", "capital": "Cairo"},
    "TR": {"country": "Turkey", "capital": "Ankara"},
}


MOCK_HEADLINES = {
    "jordan": "Jordan expands Aqaba-Amman freight feasibility studies.",
    "amman": "Amman announces new infrastructure development plans.",
    "egypt": "Egypt announces a new regional development initiative.",
    "cairo": "Cairo launches new public infrastructure projects.",
    "turkey": "Turkey presents a new economic development programme.",
    "ankara": "Ankara announces new urban transport plans.",
}


# Mock mode requires no key and is the default for this lab.
# To use Tavily:
#   SEARCH_MODE=real
#   TAVILY_API_KEY=your-key
SEARCH_MODE = os.getenv("SEARCH_MODE", "mock").strip().lower()
SEARCH_TIMEOUT = 10.0


def error_result(message: str, code: str) -> dict[str, Any]:
    """Return errors in one consistent structure."""
    return {
        "ok": False,
        "error": message,
        "code": code,
    }


@mcp.tool()
def read_data(key: str) -> dict[str, Any]:
    """
    Look up a country using an ISO 3166-1 alpha-2 code.

    Args:
        key: A two-letter country code such as JO.
             The value is case-insensitive.

    Returns:
        The normalized code, country and capital on success.
        Invalid or unknown codes return a structured error.
    """
    if not isinstance(key, str) or not key.strip():
        return error_result(
            "Key must not be empty.",
            "invalid_argument",
        )

    normalized_key = key.strip().upper()

    if len(normalized_key) != 2 or not normalized_key.isalpha():
        return error_result(
            "Key must contain exactly two letters.",
            "invalid_argument",
        )

    country = COUNTRIES.get(normalized_key)

    if country is None:
        return error_result(
            f"Country code '{normalized_key}' was not found.",
            "not_found",
        )

    return {
        "ok": True,
        "key": normalized_key,
        "country": country["country"],
        "capital": country["capital"],
    }


@mcp.tool()
def web_search(query: str) -> dict[str, Any]:
    """
    Find one recent headline related to a search query.

    Args:
        query: A non-empty search query.

    Returns:
        One headline from the local mock or Tavily.
        Validation, configuration, timeout and HTTP failures
        are returned as structured errors.
    """
    if not isinstance(query, str) or not query.strip():
        return error_result(
            "Query must not be empty.",
            "invalid_argument",
        )

    clean_query = " ".join(query.split())

    if SEARCH_MODE == "mock":
        lowered_query = clean_query.lower()

        for keyword, headline in MOCK_HEADLINES.items():
            if keyword in lowered_query:
                return {
                    "ok": True,
                    "query": clean_query,
                    "headline": headline,
                    "source": "mock",
                }

        return {
            "ok": True,
            "query": clean_query,
            "headline": f"Mock headline about {clean_query}.",
            "source": "mock",
        }

    if SEARCH_MODE != "real":
        return error_result(
            "SEARCH_MODE must be either 'mock' or 'real'.",
            "configuration_error",
        )

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        return error_result(
            "TAVILY_API_KEY is missing on the server.",
            "search_unavailable",
        )

    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": clean_query,
                "topic": "news",
                "search_depth": "basic",
                "max_results": 1,
            },
            timeout=SEARCH_TIMEOUT,
        )

        response.raise_for_status()
        results = response.json().get("results", [])

    except httpx.TimeoutException:
        return error_result(
            f"Search timed out after {SEARCH_TIMEOUT} seconds.",
            "timeout",
        )

    except httpx.HTTPError as exc:
        return error_result(
            f"Search request failed: {exc}",
            "http_error",
        )

    except ValueError:
        return error_result(
            "Search API returned invalid JSON.",
            "invalid_response",
        )

    if not results:
        return error_result(
            f"No search results found for '{clean_query}'.",
            "no_results",
        )

    first_result = results[0]

    return {
        "ok": True,
        "query": clean_query,
        "headline": first_result.get("title", "Untitled result"),
        "url": first_result.get("url"),
        "source": "tavily",
    }


if __name__ == "__main__":
    # The client launches this server using the stdio transport.
    mcp.run()