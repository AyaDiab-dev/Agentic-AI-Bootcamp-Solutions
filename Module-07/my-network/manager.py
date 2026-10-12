"""Bootcamp Help Desk: LangGraph lead, two local agents and a remote CrewAI A2A agent."""
import argparse
import json
import operator
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Annotated, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import setup_env  # noqa: E402
from meter import Meter  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

DEFAULT_DESK = "http://127.0.0.1:9999"
CARD_PATH = "/.well-known/agent-card.json"
LOCAL_SPECIALISTS = {
    "setup": (
        "Diagnose Python installation, virtual environments, pip, imports, API keys, "
        "paths and runtime errors. Use this exact structure: Probable cause; "
        "Verification step; Suggested fix; How to confirm the fix. "
        "Do not ask the student to print or share secrets."
    ),
   "concepts": (
    "Explain Agentic AI concepts accurately and clearly. "
    "MCP means Model Context Protocol: a standard for connecting "
    "AI applications to tools and data sources. "
    "A2A means Agent-to-Agent Protocol: a standard for "
    "communication and task delegation between agents. "
    "LangGraph is a framework for stateful agent workflows. "
    "CrewAI is a framework for coordinating AI agents. "
    "Never invent acronym expansions. "
    "If uncertain about a technical definition, say so. "
    "Give a concise explanation and a practical example."
),
}
REMOTE_POLICY = "Answer documented bootcamp policy, deadline, extension, submission, project requirement and grading questions."
MENU = {**LOCAL_SPECIALISTS, "policy": REMOTE_POLICY}
MAX_SPECIALISTS = 3
llm = setup_env.graph_llm()
meter = Meter()
desk_card = None
why_no_desk = "No policy desk has been discovered"


class Whiteboard(TypedDict):
    question: str
    team: list[str]
    findings: Annotated[list[str], operator.add]
    timings: Annotated[list[float], operator.add]
    fanout_started: float
    parallel_seconds: float
    verdict: str
    summary: str


def ask(system: str, question: str) -> str:
    response = llm.invoke([("system", system), ("user", question)])
    meter.record(response)
    return str(response.content).strip()


def read_business_card(url: str) -> dict:
    with urllib.request.urlopen(url.rstrip("/") + CARD_PATH, timeout=10) as response:
        return json.load(response)


def offers(card: dict, tag: str) -> bool:
    return any(tag in skill.get("tags", []) for skill in card.get("skills", []))


def phone(card: dict, text: str) -> str:
    call = {
        "jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "SendMessage",
        "params": {"message": {"role": "ROLE_USER", "messageId": str(uuid.uuid4()), "parts": [{"text": text}]}},
    }
    url = card["supportedInterfaces"][0]["url"]
    request = urllib.request.Request(
        url, data=json.dumps(call).encode("utf-8"),
        headers={"Content-Type": "application/json", "A2A-Version": "1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message", "A2A error"))
    task = (payload.get("result") or {}).get("task")
    if not task or (task.get("status") or {}).get("state") != "TASK_STATE_COMPLETED":
        raise RuntimeError("A2A task did not complete")
    answer = "\n".join(
        part["text"] for artifact in task.get("artifacts", [])
        for part in artifact.get("parts", []) if isinstance(part.get("text"), str)
    ).strip()
    if not answer:
        raise RuntimeError("A2A task has no answer artifact")
    return answer



def lead_decides(board: Whiteboard) -> dict:
    question = board["question"]
    lower = question.lower()

    # Keywords for deterministic routing
    setup_terms = (
        "modulenotfounderror", "importerror", "traceback",
        "pip install", "venv", "environment",
        "api key", "module notfound", "module not found"
    )

    policy_terms = (
        "submit", "submission", "deadline", "extension",
        "grading", "grade", "sick", "monday",
        "late", "instructor approval"
    )

    concept_terms = (
        "explain", "what is", "what are",
        "difference between", "how does",
        "concept", "mcp", "a2a", "langgraph",
        "crewai"
    )

    chosen = []

    if any(term in lower for term in setup_terms):
        chosen.append("setup")

    if any(term in lower for term in policy_terms):
        chosen.append("policy")

    if any(term in lower for term in concept_terms):
        chosen.append("concepts")

    # Use LLM routing only when no keyword matches
    if not chosen:
        menu_text = ", ".join(MENU)
        reply = ask(
            "You are the Bootcamp Help Desk lead. "
            "Your only job is to select the relevant specialists. "
            "Do not answer the student's question. "
            f"Choose only from: {menu_text}. "
            "Reply with specialist names only, separated by commas. "
            "Example: setup, concepts",
            question,
        )

        chosen = [
            word
            for word in dict.fromkeys(
                re.split(r"[^a-z]+", reply.lower())
            )
            if word in MENU
        ][:MAX_SPECIALISTS]

    # Validate allowed specialists and enforce budget
    chosen = [
        name for name in dict.fromkeys(chosen)
        if name in MENU
    ][:MAX_SPECIALISTS]

    if not chosen:
        chosen = ["concepts"]

    print("Lead selected:", ", ".join(chosen))

    return {"team": chosen, "fanout_started": time.perf_counter()}


def send_to_team(board: Whiteboard) -> list[str]:
    return board["team"]


def make_local_specialist(name: str, instructions: str):
    def specialist(board: Whiteboard) -> dict:
        start = time.perf_counter()
        response = ask(
            f"You are the Bootcamp Help Desk {name} specialist. {instructions} "
            "Answer only the part of the student's question related to your specialty. "
            "Other specialists will handle the remaining parts. "
            "Do not escalate simply because another part is outside your specialty. "
            "Use ESCALATE: only when your own part cannot be answered safely or requires instructor approval. "
            "Otherwise begin with ANSWER:. Be clear and concise.",
            board["question"],
        )
        if not response.startswith(("ANSWER:", "ESCALATE:")):
            response = "ANSWER: " + response
        elapsed = time.perf_counter() - start
        print(f"{name}: completed in {elapsed:.1f}s")
        return {"findings": [f"[{name}] {response}"], "timings": [elapsed]}
    specialist.__name__ = name
    return specialist


def policy_desk(board: Whiteboard) -> dict:
    start = time.perf_counter()
    try:
        if desk_card is None:
            raise ConnectionError(why_no_desk)
        response = phone(desk_card, board["question"])
        if not response.startswith(("ANSWER:", "ESCALATE:")):
            raise ValueError("Unrecognized policy answer format")
    except Exception as exc:
        response = f"ESCALATE: Remote policy specialist unavailable or invalid ({exc}). Instructor confirmation required."
    elapsed = time.perf_counter() - start
    print(f"policy (A2A): completed in {elapsed:.1f}s")
    return {"findings": [f"[policy·A2A] {response}"], "timings": [elapsed]}


def lead_summarizes(board: Whiteboard) -> dict:
    elapsed = time.perf_counter() - board["fanout_started"]
    findings = board["findings"]
    escalated = any(re.search(r"\]\s*ESCALATE:", item, re.IGNORECASE) for item in findings)
    # Decision is computed in Python, never delegated to an LLM.
    verdict = "SEND TO THE INSTRUCTOR" if escalated else "ANSWER"
    summary = "\n".join(findings) if findings else "ESCALATE: No specialist response was produced."
    if not findings:
        verdict = "SEND TO THE INSTRUCTOR"
    return {"verdict": verdict, "summary": summary, "parallel_seconds": elapsed}


def build_graph():
    graph = StateGraph(Whiteboard)
    graph.add_node("lead_decides", lead_decides)
    for name, job in LOCAL_SPECIALISTS.items():
        graph.add_node(name, make_local_specialist(name, job))
        graph.add_edge(name, "lead_summarizes")
    graph.add_node("policy", policy_desk)
    graph.add_edge("policy", "lead_summarizes")
    graph.add_node("lead_summarizes", lead_summarizes)
    graph.add_edge(START, "lead_decides")
    graph.add_conditional_edges("lead_decides", send_to_team, list(MENU))
    graph.add_edge("lead_summarizes", END)
    return graph.compile()


def main() -> int:
    global desk_card, why_no_desk
    parser = argparse.ArgumentParser(description="Bootcamp Help Desk multi-agent system")
    parser.add_argument("question", nargs="*", help="Student question")
    parser.add_argument("--desk", default=DEFAULT_DESK)
    args = parser.parse_args()
    question = " ".join(args.question).strip() or input("Student question: ").strip()
    if not question:
        print("Please enter a question")
        return 1
    try:
        card = read_business_card(args.desk)
        if not offers(card, "policy") or not offers(card, "deadlines"):
            why_no_desk = "The remote agent card does not advertise policy and deadlines"
            print("Remote agent rejected:", why_no_desk)
        else:
            desk_card = card
            print(f"Discovered A2A agent: {card['name']}")
    except Exception as exc:
        why_no_desk = str(exc)
        print(f"Remote policy desk unavailable: {exc}")
    result = build_graph().invoke(
        {"question": question, "findings": [], "timings": []},
        config={"recursion_limit": 10},
    )
    print("\n=== BOOTCAMP HELP DESK ===")
    print("Question:", question)
    print("Specialists:", ", ".join(result["team"]))
    print("\nResponses:\n", result["summary"])
    print("\nFINAL VERDICT:", result["verdict"])
    print(f"Parallel time: {result['parallel_seconds']:.1f}s | Sequential total: {sum(result['timings']):.1f}s")
    print(meter.card(agents=len(result["team"]) + 1, model=setup_env.MODEL,
                     note="Remote CrewAI tokens are measured separately in the remote desk process."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
