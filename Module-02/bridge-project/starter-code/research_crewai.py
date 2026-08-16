"""
Module 2 Bridge Project - CrewAI STARTER (hierarchical)

Same job as the LangGraph version. Build that one FIRST, then come back here.

WHAT IS DIFFERENT
    In LangGraph you drew the branch yourself, in one line you could point
    at. A hierarchical crew has no such line. Instead you hire a MANAGER and
    let it decide who works, in what order, and when the job is done.

    You are trading a decision you can READ for a decision you DELEGATE.

    Run both versions on the nonsense claim afterwards and watch carefully.
    In LangGraph, refusing is a code path - report_gap physically cannot
    produce an answer. Here, refusing is an instruction in a backstory. You
    are asking the manager nicely.

    Whether it listens is the most interesting result in this project, and
    it goes in your README either way.

Run:
    python research_crewai_starter.py "Anthropic was founded by ex-OpenAI staff"
    python research_crewai_starter.py "the flurbotron 9000 was released in 2019"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# CrewAI asks about execution traces on the first run in a new folder and
# blocks for 20 seconds waiting for an answer. This stops that.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from crewai import Agent, Crew, LLM, Process, Task  # noqa: E402
from crewai.tools import tool  # noqa: E402
from dotenv import find_dotenv, load_dotenv  # noqa: E402

try:
    from crewai.events.listeners.tracing.utils import mark_first_execution_done

    mark_first_execution_done()
except Exception:
    pass


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from search_tools import web_search  # noqa: E402


load_dotenv()
load_dotenv(find_dotenv(usecwd=True))

api_key = os.environ.get("OPENROUTER_API_KEY")

if not api_key:
    raise RuntimeError(
        "OPENROUTER_API_KEY not found.\n"
        "Create a file named .env in the project folder containing:\n"
        "    OPENROUTER_API_KEY=sk-or-...\n"
        "then run this script again."
    )


# ---------------------------------------------------------------------------
# TODO 1 - MODEL CLIENT
# ---------------------------------------------------------------------------

llm = LLM(
    model="openrouter/openai/gpt-4o-mini",
    temperature=0,
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1",
)


# ---------------------------------------------------------------------------
# THE TOOL
# ---------------------------------------------------------------------------
# In LangGraph the tool was a plain function call inside a node - YOU decided
# when it ran.
#
# Here the tool is given to the Researcher agent, and the agent/manager
# decides when it should be used.


# TODO 2 - wrap web_search as a CrewAI tool.
@tool("Web Search")
def search_web(query: str) -> str:
    """Search the web for evidence about the given query.

    Returns search findings together with source URLs.

    The tool may also return exactly:
    NO_RESULTS
    if the search ran successfully but found nothing,

    or:
    SEARCH_UNAVAILABLE
    if the search could not run.
    """
    return web_search(query)


def build_crew() -> Crew:

    # -----------------------------------------------------------------------
    # TODO 3 - RESEARCHER
    # -----------------------------------------------------------------------
    researcher = Agent(
        role="Evidence Researcher",
        goal=(
            "Find reliable web evidence that can verify or reject the "
            "question without inventing information."
        ),
        backstory=(
            "You are a careful evidence researcher. "
            "Always use the Web Search tool when researching the question. "
            "Report exactly what the search returned and preserve all source URLs. "
            "If the tool returns NO_RESULTS, say clearly that the search ran "
            "but found nothing. "
            "If it returns SEARCH_UNAVAILABLE, say clearly that the search "
            "could not run. "
            "Never replace missing evidence with your own memory or assumptions."
        ),
        tools=[search_web],
        llm=llm,
        verbose=True,
        max_iter=4,
    )


    # -----------------------------------------------------------------------
    # TODO 4 - WRITER
    # -----------------------------------------------------------------------
    writer = Agent(
        role="Evidence Writer",
        goal=(
            "Produce a short evidence-based final response and refuse to "
            "answer when the available evidence is insufficient."
        ),
        backstory=(
            "You are a cautious fact-checking writer. "
            "You only make claims that are supported by the research evidence. "
            "You would rather say that something could not be verified than "
            "write a convincing statement that might be wrong. "
            "Never invent missing facts or sources."
        ),
        llm=llm,
        verbose=True,
        max_iter=4,
    )


    # -----------------------------------------------------------------------
    # THE TASKS
    # -----------------------------------------------------------------------
    # There is intentionally NO agent= on these tasks.
    # The hierarchical manager assigns them.


    # -----------------------------------------------------------------------
    # TODO 5 - RESEARCH TASK
    # -----------------------------------------------------------------------
    research_task = Task(
        description=(
            "Research the following question or claim:\n"
            "{question}\n\n"
            "Use the Web Search tool to find evidence. "
            "Report exactly what the tool returns and preserve every source URL. "
            "Do not use your own knowledge as a substitute for search evidence. "
            "If the tool returns NO_RESULTS, report NO_RESULTS plainly. "
            "If the tool returns SEARCH_UNAVAILABLE, report "
            "SEARCH_UNAVAILABLE plainly. "
            "Do not treat these two cases as the same thing."
        ),
        expected_output=(
            "A concise evidence report containing the relevant findings and "
            "source URLs, or an explicit NO_RESULTS / SEARCH_UNAVAILABLE result "
            "when no usable evidence is available."
        ),
    )


    # -----------------------------------------------------------------------
    # TODO 6 - WRITING TASK
    # -----------------------------------------------------------------------
    # This is where the logical branch is expressed as INSTRUCTIONS.
    write_task = Task(
        description=(
            "Prepare the final response for this question:\n"
            "{question}\n\n"
            "Use ONLY the research evidence produced by the crew.\n\n"

            "You must choose exactly ONE of these outcomes:\n\n"

            "OUTCOME 1 - evidence is sufficient:\n"
            "- Begin with exactly: VERDICT: ANSWERED\n"
            "- Answer the question in fewer than 180 words.\n"
            "- Every factual claim must be supported by the research evidence.\n"
            "- Include at least one source URL that appeared in the evidence.\n"
            "- If part of the question is not supported, say so.\n\n"

            "OUTCOME 2 - evidence is insufficient:\n"
            "- Begin with exactly: VERDICT: COULD NOT VERIFY\n"
            "- Do NOT answer the original question.\n"
            "- Write one sentence saying plainly that it could not be verified.\n"
            "- Give one or two short bullets explaining what evidence is missing.\n"
            "- Finish with exactly this format:\n"
            "NEXT SEARCH: <one short search query that could find the missing evidence>\n\n"

            "Never invent facts, dates, people, products, or source URLs."
        ),
        expected_output=(
            "Exactly one final response: either VERDICT: ANSWERED with a "
            "source-backed answer and at least one URL, or "
            "VERDICT: COULD NOT VERIFY with no answer and a final NEXT SEARCH line."
        ),
    )


    # -----------------------------------------------------------------------
    # TODO 7 - HIERARCHICAL CREW
    # -----------------------------------------------------------------------
    return Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.hierarchical,
        manager_llm=llm,
        verbose=True,
        tracing=False,
    )


def main() -> int:

    question = " ".join(sys.argv[1:]).strip() or \
        "Anthropic was founded by former OpenAI employees"

    result = str(
        build_crew().kickoff(
            inputs={"question": question}
        )
    )

    print("\n" + "=" * 70)
    print(f"QUESTION : {question}")
    print("=" * 70)
    print(result)


    # -----------------------------------------------------------------------
    # TODO 8 - LOG WHICH WAY THE CREW WENT
    # -----------------------------------------------------------------------
    #
    # Unlike LangGraph, there is no route_taken state written by a node.
    # We infer the route from the final text produced by the crew.

    upper_result = result.upper()

    if "VERDICT: COULD NOT VERIFY" in upper_result:
        route = "COULD NOT VERIFY"

    elif "VERDICT: ANSWERED" in upper_result:
        route = "ANSWERED"

    else:
        route = "UNKNOWN"


    print("\n" + "=" * 70)
    print(f"ROUTE : {route}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())