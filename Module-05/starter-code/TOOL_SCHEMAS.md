# Module 5 — MCP Tool Schemas

This document describes the tools exposed by `mcp_server.py` and
called by the LangGraph agent through MCP.

## Tool Schemas

| Tool | Arguments | Successful output | Error cases |
|---|---|---|---|
| `read_data` | `key: str` — a two-letter ISO country code; case-insensitive | `ok`, normalized `key`, `country`, and `capital` | Empty key, invalid format, or unknown country code |
| `web_search` | `query: str` — a non-empty search query | `ok`, normalized `query`, one `headline`, and `source` | Empty query, invalid search mode, missing API key, timeout, HTTP error, invalid response, or no results |

## `read_data` Example

Input:

```json
{
  "key": "JO"
}
```

Successful output:

```json
{
  "ok": true,
  "key": "JO",
  "country": "Jordan",
  "capital": "Amman"
}
```

Unknown-code output:

```json
{
  "ok": false,
  "error": "Country code 'ZZ' was not found.",
  "code": "not_found"
}
```

## `web_search` Example

Input:

```json
{
  "query": "Jordan news"
}
```

Mock-mode output:

```json
{
  "ok": true,
  "query": "Jordan news",
  "headline": "Jordan expands Aqaba-Amman freight feasibility studies.",
  "source": "mock"
}
```

## Search Modes

The server uses `mock` mode by default, as permitted by the lab
worksheet. Mock mode requires no external API key or network request.

Optional real search can be enabled server-side using:

```text
SEARCH_MODE=real
TAVILY_API_KEY=your-key
```

The API key remains inside the MCP server and is never exposed to the
LangGraph agent.

The real search path uses a 10-second timeout and maps configuration,
timeout, HTTP, invalid-response, and no-result failures to structured
error results.

## Client–Server Boundary

The client discovers tools using `session.list_tools()` and calls them
using `session.call_tool()`.

The client does not import `read_data` or `web_search` from the server.

The client also:

- limits the ReAct loop to six action attempts;
- blocks duplicate tool calls in Python;
- treats tool results as untrusted data;
- handles MCP failures without crashing the graph;
- checks that `read_data("ZZ")` returns a clean error.