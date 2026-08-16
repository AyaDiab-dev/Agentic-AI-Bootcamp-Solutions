# Module 2 Bridge Project

This project implements the same evidence-based research agent using LangGraph and CrewAI, then compares how each framework decides whether to answer a question or refuse when there is not enough evidence.

## 1. Which framework would you ship for your use case, and why?

I would choose LangGraph for this use case because the decision-making flow is explicit and easier to control. The graph checks whether the evidence is sufficient and then follows a specific code path to either answer the question or report that there is not enough evidence.

CrewAI is more flexible because the manager decides how to delegate the work, but this also means that the decision depends more on the manager following the instructions correctly. For a research agent where avoiding unsupported answers is important, I would prefer the more explicit control provided by LangGraph.

## 2. On the nonsense query, did each version refuse?

The nonsense query was:

`the flurbotron 9000 was released in 2019`

Yes, both versions refused to answer.

### LangGraph

LangGraph returned:

`VERDICT: NOT_ENOUGH`

`ROUTE: GAP REPORTED`

It explained that the claim could not be verified because no search results were found, and it ended with:

`NEXT SEARCH: Flurbotron 9000 product information`

### CrewAI

CrewAI also refused to answer. It returned:

`VERDICT: COULD NOT VERIFY`

`ROUTE: COULD NOT VERIFY`

It did not invent information about the Flurbotron 9000 and ended with a `NEXT SEARCH:` suggestion.

In this experiment, both frameworks correctly refused the unsupported claim.

## 3. Where does the decision live in each framework?

In LangGraph, the decision lives directly in the graph logic. The `assess` node sets the verdict, and `choose_next` uses that verdict to route execution to either `write_answer` or `report_gap`.

In CrewAI, the decision is delegated to the hierarchical manager. The manager uses the task instructions and agent roles to decide how the work should be handled.

If a customer asked, "How do I know it will never make something up?", LangGraph would be easier to prove because the refusal behavior is enforced by an explicit code path. In CrewAI, the behavior depends more on the manager following the instructions correctly.

## 4. Why couldn't the agent run the NEXT SEARCH?

The graph ends after `report_gap`, because that node is connected directly to `END`. There is no loop or conditional edge that sends the suggested `NEXT SEARCH` query back to `run_search`, so the agent can suggest another search but cannot execute it.