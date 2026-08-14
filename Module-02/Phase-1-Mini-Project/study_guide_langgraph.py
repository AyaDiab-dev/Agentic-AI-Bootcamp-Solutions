"""
Module 2 Phase 1 Mini-Project — LangGraph starter.

Build the same three-task Study Guide Agent in LangGraph and CrewAI.
Read M2-Phase1-Mini-Project.md before filling in the TODOs.

Run it with your own topic:
    python study_guide_langgraph_starter.py "temperature in language models"
"""

from __future__ import annotations

import os
import sys
from typing import TypedDict
#from urllib import response

from dotenv import find_dotenv, load_dotenv
from langgraph.graph import END, StateGraph
from langchain_openai import ChatOpenAI

# Find your .env whether you run this from the repo or from your own project
# folder. Both calls are harmless if the file isn't there.
# This is boilerplate, not the lesson.
load_dotenv()                          # searches upward from this file
load_dotenv(find_dotenv(usecwd=True), override=True)  # searches upward from where you ran it

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    raise RuntimeError(
        "OPENROUTER_API_KEY not found.\n"
        "Create a file named .env in your project folder containing:\n"
        "    OPENROUTER_API_KEY=sk-or-...\n"
        "then run this script again."
    )


# TODO 1: configure the OpenRouter model, as you did in Module 2.
llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    temperature=0,
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)


class StudyGuideState(TypedDict):
    topic: str
    explanation: str
    example: str
    quiz: str


def explain_topic(state: StudyGuideState) -> StudyGuideState:
    """Task 1: explain the topic in plain language."""
    # TODO 2: call the model and store the result in explanation.
    response = llm.invoke(
        f"Explain {state['topic']} in 2-3 sentences in plain language for a beginner, make sure to not invent statistics, and do not include examples or quiz questions yet."
)
    return {**state, "explanation": response.content}


def create_example(state: StudyGuideState) -> StudyGuideState:
    """Task 2: use the explanation to create an example and misconception."""
    # TODO 3: read topic + explanation, call the model, store example.
    response = llm.invoke(
        f"Topic:{state['topic']}\n"
        f"Explanation:{state['explanation']}\n"
        "according to the explanation, create one example and one common misconception, then give a clear distinction between the example and the misconception."
    )
    return {**state, "example": response.content}


def create_quiz(state: StudyGuideState) -> StudyGuideState:
    """Task 3: use earlier state to create three questions and answers."""
    # TODO 4: read the state, call the model, store quiz.
    response = llm.invoke(
        f"Topic:{state['topic']}\n"
        f"Explanation:{state['explanation']}\n"
        f"Example:{state['example']}\n"
        f"Based on the above information, create a quiz of exactly three questions followed by an answer key."
)
    return {**state, "quiz": response.content}


def build_graph():
    graph = StateGraph(StudyGuideState)

    # TODO 5: register all three nodes.
    graph.add_node("explain_topic", explain_topic)
    graph.add_node("create_example", create_example)
    graph.add_node("create_quiz", create_quiz)
    # TODO 6: set the entry point and connect:
    #         explain_topic -> create_example -> create_quiz -> END.
    graph.set_entry_point("explain_topic")
    graph.add_edge("explain_topic", "create_example")   
    graph.add_edge("create_example", "create_quiz")
    graph.add_edge("create_quiz", END)


    return graph.compile()


def run_study_guide(topic: str) -> StudyGuideState:
    app = build_graph()
    initial_state: StudyGuideState = {
        "topic": topic,
        "explanation": "",
        "example": "",
        "quiz": "",
    }
    return app.invoke(initial_state)


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]).strip() or "Model Context Protocol"

    result = run_study_guide(topic)

    print(f"# Study Guide: {result['topic']}\n")
    print("## Explanation\n", result["explanation"])
    print("\n## Example and misconception\n", result["example"])
    print("\n## Quiz\n", result["quiz"])
