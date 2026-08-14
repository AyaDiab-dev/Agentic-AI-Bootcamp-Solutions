"""
Module 2 Phase 1 Mini-Project — CrewAI starter.

Build one Agent with three sequential Tasks. Do not create three agents:
multi-agent collaboration is covered later in Module 7.

Run it with your own topic:
    python study_guide_crewai_starter.py "temperature in language models"
"""

from __future__ import annotations

import os
import sys

from dotenv import find_dotenv, load_dotenv
from crewai import Agent, Crew, LLM, Process, Task

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


# TODO 1: configure the same OpenRouter model used in your LangGraph version.
llm = LLM(
        model="openrouter/openai/gpt-4o-mini",
        temperature=0,
        api_key=api_key,
  )


def build_crew() -> Crew:
    # TODO 2: create one study-guide Agent with a role, goal, backstory, and llm.
    teacher = Agent(
        role="Technical Learning Coach",
        goal="Give guidance and help students study technical topics in plain language",
        backstory="you are a technical learning coach who helps students understand complex topics in plain language. You provide clear explanations, practical examples, and quizzes to reinforce learning.and you never invent facts or statistics.",
        llm=llm,          # <- uses the client you built in TODO 1
        verbose=False,
    )

    # TODO 3: create the explanation task.
    explain_task = Task(
        description="Explain {topic} in 2-3 plain-language sentences for a beginner. Dont invent facts or statistics. Also dont add examples or quizzes yet.",
        expected_output="A clear and accurate explanation in 2-3 sentences in plain language.",
        agent=teacher,
    )

    # TODO 4: create the example task and pass explain_task as context.
    example_task = Task(
    description=(
        "Based on the explanation for {topic}, provide one practical example and one common misconception. Clearly distinguish between the example and the misconception. Don't invent facts or statistics." ),
    expected_output=( "One practical example and one common misconception, clearly distinguished." ),
    agent=teacher,
    context=[explain_task],
)

    # TODO 5: create the final study-guide task and pass both previous tasks
    # as context. It must preserve the explanation and example, not only print
    # the quiz.
    quiz_task = Task(
        description=("Assemble the complete study guide for {topic}. Include the explanation, "
            "the practical example and misconception, then exactly three questions followed by a matching answer key."),
        expected_output=( "A complete study guide with Explanation, Example and misconception also Quiz sections."),
        agent=teacher,
        context=[explain_task, example_task],
)

    # TODO 6: assemble one sequential Crew.
    return Crew(
        agents=[teacher],
        tasks=[explain_task, example_task, quiz_task],
        process=Process.sequential,
        verbose=False,
        tracing=False,
    )


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]).strip() or "Model Context Protocol"

    crew = build_crew()
    result = crew.kickoff(inputs={"topic": topic})
    print(result)
