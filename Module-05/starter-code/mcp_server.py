"""
Module 5 Lab — MCP SERVER
Expose two tools over MCP: read_data(key) and web_search(query).
"""

import os
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
}

USE_MOCK = os.environ.get("SEARCH_API_KEY") is None


@mcp.tool()
def read_data(key: str) -> dict:
    """
    Look up a country by ISO 3166-1 alpha-2 code.

    Args:
        key: Two-letter ISO country code, e.g. JO for Jordan.
             Case-insensitive.

    Returns:
        A dictionary with country and capital on success,
        or a structured error dictionary on failure.
    """

    if not key or not key.strip():
        return {
            "error": "Key must not be empty.",
            "code": "invalid_argument"
        }

    normalized = key.strip().upper()

    if len(normalized) != 2 or not normalized.isalpha():
        return {
            "error": "Key must be a two-letter ISO country code.",
            "code": "invalid_argument"
        }

    if normalized not in COUNTRIES:
        return {
            "error": f"Country code '{normalized}' not found.",
            "code": "not_found"
        }

    return COUNTRIES[normalized]


@mcp.tool()
def web_search(query: str) -> dict:
    """
    Search for one recent headline related to the query.

    Args:
        query: A non-empty search query.

    Returns:
        A dictionary containing one headline on success,
        or a structured error dictionary on failure.
    """

    if not query or not query.strip():
        return {
            "error": "Query must not be empty.",
            "code": "invalid_argument"
        }

    if USE_MOCK:
        normalized_query = query.strip().lower()

        for keyword, headline in MOCK_HEADLINES.items():
            if keyword in normalized_query:
                return {
                    "query": query,
                    "headline": headline,
                    "source": "mock"
                }

        return {
            "query": query,
            "headline": f"Mock headline about {query}.",
            "source": "mock"
        }

    return {
        "error": "Real search API is not configured.",
        "code": "search_unavailable"
    }


@mcp.resource("countries://all")
def countries_all() -> str:
    """
    Return the complete country table supported by this server.
    """
    return str(COUNTRIES)


if __name__ == "__main__":
    mcp.run()