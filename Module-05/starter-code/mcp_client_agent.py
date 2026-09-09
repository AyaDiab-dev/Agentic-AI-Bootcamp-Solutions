"""
Module 5 Lab — MCP CLIENT AGENT
A LangGraph ReAct agent that connects to the MCP server
and calls tools through MCP.
"""

import os
import asyncio
from typing import TypedDict, Optional, Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END


load_dotenv("../../.env", override=True)

MAX_STEPS = 8

SERVER = StdioServerParameters(
    command="python",
    args=["mcp_server.py"]
)


class Action(BaseModel):
    tool: Literal["read_data", "web_search", "final_answer"]
    args: dict


class State(TypedDict):
    question: str
    scratchpad: list
    action: Optional[dict]
    answer: Optional[str]
    tool_catalog: str
    steps: int


llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)


async def main():

    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:

            await session.initialize()

            # Discover MCP tools
            tools = await session.list_tools()

            print("Discovered tools:")
            for tool in tools.tools:
                print("-", tool.name)

            # Discover MCP resources
            resources = await session.list_resources()

            print("\nDiscovered resources:")
            for resource in resources.resources:
                print("-", resource.uri)

            # Build tool catalog dynamically
            catalog_lines = []

            for tool in tools.tools:
                catalog_lines.append(
                    f"""
Tool name: {tool.name}
Description: {tool.description}
Input schema: {tool.inputSchema}
"""
                )

            tool_catalog = "\n".join(catalog_lines)

            async def reason(state: State):

                prompt = f"""
You are a ReAct agent.

Question:
{state["question"]}

Available MCP tools:
{state["tool_catalog"]}

Observations so far:
{state["scratchpad"]}

Choose exactly one next action.

Rules:
- Use read_data when country information is needed.
- Use web_search when a recent headline is needed.
- Do not repeat a tool call if its result is already in observations.
- When the observations fully answer the question, use final_answer.
- For final_answer, put the complete answer inside:
  {{"answer": "..."}}
"""

                action = await llm.with_structured_output(
    Action,
    method="function_calling"
).ainvoke(prompt)

                state["action"] = action.model_dump()

                print("\nReason chose:")
                print(state["action"])

                return state

            async def act(state: State):

                action = state["action"]

                tool_name = action["tool"]
                arguments = action["args"]

                if tool_name == "final_answer":
                    state["answer"] = arguments.get(
                        "answer",
                        "No answer provided."
                    )
                    return state

                result = await session.call_tool(
                    tool_name,
                    arguments=arguments
                )

                observation = "\n".join(
                    block.text
                    for block in result.content
                    if hasattr(block, "text")
                )

                print(
                    f"MCP call -> {tool_name}:",
                    observation
                )

                state["scratchpad"].append(
                    {
                        "tool": tool_name,
                        "arguments": arguments,
                        "result": observation
                    }
                )

                state["steps"] += 1

                if state["steps"] >= MAX_STEPS:
                    state["answer"] = (
                        "Stopped after max steps "
                        "without a confirmed answer."
                    )

                return state

            def is_done(state: State):

                if state["answer"]:
                    return "end"

                return "continue"

            graph = StateGraph(State)

            graph.add_node("reason", reason)
            graph.add_node("act", act)

            graph.set_entry_point("reason")

            graph.add_edge("reason", "act")

            graph.add_conditional_edges(
                "act",
                is_done,
                {
                    "continue": "reason",
                    "end": END
                }
            )

            app = graph.compile()

            question = (
                "What's the capital of the country with ISO code 'JO', "
                "and find one recent headline about it?"
            )

            initial_state = {
                "question": question,
                "scratchpad": [],
                "action": None,
                "answer": None,
                "tool_catalog": tool_catalog,
                "steps": 0
            }

            result = await app.ainvoke(initial_state)

            print("\nFinal Answer:")
            print(result["answer"])


if __name__ == "__main__":
    asyncio.run(main())