# Module 5 Bridge Project — Release Smoke Test

## Student

Aya Diab

## Scenario

**Scenario A — Release Smoke Test**

I chose the QA scenario because it demonstrates a practical use of MCP: connecting an existing LangGraph agent to a browser automation server without writing or importing browser tools.

The agent uses the external `@playwright/mcp` server and discovers its available tools dynamically at runtime.

## Task

The agent runs a release smoke test against:

https://github.com/AyaDiab-dev/Agentic-AI-Bootcamp-Solutions/tree/main/Module-05/starter-code

It verifies:

1. The exact page title.
2. The visible repository folder heading or breadcrumb.
3. Whether the browser logged any console errors.
4. Whether the `mcp_agent_output.txt` link exists.

The final answer may report `PASS` only when all four checks have direct supporting observations.

## Result

**PASS**

The successful run verified:

* Page title: `Agentic-AI-Bootcamp-Solutions/Module-05/starter-code at main · AyaDiab-dev/Agentic-AI-Bootcamp-Solutions · GitHub`
* Repository folder path: `Module-05/starter-code`
* Console errors: `0`
* `mcp_agent_output.txt`: link found

The complete successful tool-call transcript is available in `RUN_TRANSCRIPT.txt`.

## What Could Not Be Verified

Nothing remained unverified in the final run.

Earlier attempts could not navigate because the Playwright Chromium build required by the MCP server was not installed. After installing the matching browser build, navigation succeeded.

## Reflection

The most surprising behavior was that prompt instructions alone did not reliably control the loop. In early runs, the model repeated successful browser calls, stopped before completing every check, and once reported `PASS` while admitting that one requirement was not checked. I first refined the loop-discipline instructions, but the model could still ignore them. I therefore added two server-agnostic safeguards in Python: one blocks identical repeated tool calls, and another blocks a contradictory final answer that contains both `PASS` and an admission such as “not checked” or “not verified.” In the final run, these guards worked as intended: the duplicate call was blocked, the premature answer was rejected, the missing link check was performed, and only then did the agent return a supported `PASS`. This reinforced the lesson that prompts request behavior, while code must enforce rules that cannot safely be ignored.
