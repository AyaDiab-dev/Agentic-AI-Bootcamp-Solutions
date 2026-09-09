"""
The Vendor Onboarding Desk - Module 3 bridge project - STARTER

Read INSTRUCTIONS.md first, then REQUEST.md.

Before you touch this file:
    python verify_tools.py        <- must print "all 10 checks passed"

Everything here is scaffolding you have seen before. What is new is the
BUDGET: you cannot afford to check everything, so something has to decide
what is worth checking. That decision is the project.

Run it now - it will check your setup and tell you what is missing.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Literal, Optional, TypedDict

# the tools live one level up, in bridge-project/ - this lets you run the file
# from either folder without thinking about it
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from registry_tools import (
    LOOKUP_UNAVAILABLE,
    NO_RECORDS,
    NO_SANCTIONS_MATCH,
    gleif_lookup,
    sanctions_screen,
)
from search_tools import web_search

load_dotenv(override=True)

llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    temperature=0,
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

# ===========================================================================
# THE CONSTRAINT
# ===========================================================================
# This rations the EXPENSIVE work: establishing which legal entity a supplier
# actually is. Sanctions screening is a mandatory baseline control - run it for
# everyone, always; it does not come out of this budget.
# Do not raise this number. Working inside it IS the project.
MAX_LOOKUPS = 9
MAX_SCREEN_STEPS = 3

BUDGET = {"used": 0}


def spend(what: str) -> bool:
    """Call before every lookup. Returns False when the budget is gone."""
    if BUDGET["used"] >= MAX_LOOKUPS:
        return False
    BUDGET["used"] += 1
    print(f"  [{BUDGET['used']:2}/{MAX_LOOKUPS}] {what}")
    return True


def has_sanctions_hit(evidence_items: list[str], threshold: float = 0.90) -> bool:
    """Return True when an OFAC candidate score meets the chosen threshold."""
    text = "\n".join(evidence_items)
    scores = re.findall(
        r"^\s*(0(?:\.\d+)?|1(?:\.0+)?)\s+.+\[programme:",
        text,
        flags=re.MULTILINE,
    )
    return any(float(score) >= threshold for score in scores)


# ===========================================================================
# 1 - THE SCHEMAS
# ===========================================================================
# Three decisions, three schemas - same shape as the Module 3 solution.
# Explicit fields only. `args: dict` will earn you an HTTP 400.

class Supplier(BaseModel):
    """One line out of Rana's email."""
    name: str
    # annual_value: float####
    jurisdiction:str
    business_type:str
    priority: int
    priority_reason:str


class Plan(BaseModel):
    """An ordered supplier-screening plan within the lookup budget."""

    ordered_suppliers: list[Supplier] = Field( description=( "All suppliers ordered from highest to lowest screening priority." ))

    budget_strategy: str = Field( description=(
            "A short explanation of how the nine-lookups budget will be "
            "used and which risks receive priority."
        )
    )


class Verdict(BaseModel):
       """An actionable decision for one supplier."""
       supplier: str
       verdict: Literal["APPROVE", "CONDITIONS", "REJECT", "INSUFFICIENT"]
       reason: str = Field(description=  "A clear evidence-based reason that finance manager can repeat to Procurement.")
       next_action: str = Field(description=(
        "The exact action the finance manager should take. For CONDITIONS, "
        "state the required document or check. For REJECT, state not to "
        "release payment and why. For INSUFFICIENT, state what evidence "
        "would settle the case. For APPROVE, state that payment may be released."
    )
)


class ScreeningAction(BaseModel):
    """The next action selected while screening one supplier."""

    tool: Literal["gleif_lookup", "web_search", "finish"]
    query: Optional[str] = Field(
        default=None,
        description=(
            "The supplier name for gleif_lookup, or a concise search query "
            "for web_search."
        ),
    )
    reason: str = Field(
        description="Why this is the best next action based on current evidence.",
    )

# ===========================================================================
# 2 - THE STATE
# ===========================================================================

class State(TypedDict):
    request: str                              # The original supplier request
    queue: list[Supplier]                     # Suppliers not yet screened
    evidence: list[tuple[str, str]]           # Supplier name and retrieved evidence
    current_evidence: list[str]               # Evidence for the current supplier
    verdicts: list[Verdict]                   # One verdict per processed supplier
    skipped: list[Supplier]                   # Suppliers skipped when the budget ends
    plan: Optional[Plan]                      # Complete plan produced by triage
    current_supplier: Optional[Supplier]      # Supplier currently being processed
    memo: Optional[str]                       # Final supplier review report


class ScreeningState(TypedDict):
    supplier: Supplier                        # The single supplier being screened
    scratchpad: list[str]                     # Evidence collected so far
    action: Optional[dict]                    # Next structured action
    done: bool                                # Whether the ReAct loop should stop
    steps_used: int                           # Protection against an endless loop
    failure: Optional[str]                    # Honest record of an agent failure

# ===========================================================================
# 3 - YOUR NODES
# ===========================================================================

def fallback_plan(request: str) -> Plan:
    """Recover the seven request lines if structured planning fails twice."""
    supplier_blocks = re.findall(r"```\s*\n(.*?)```", request, flags=re.DOTALL)
    supplier_text = next(
        (block for block in supplier_blocks if "Maersk A/S" in block),
        "",
    )
    matches = re.findall(
        r"^\s*([^\n—]+?)\s+—\s+([^,\n]+),\s*([^\n]+?)\s*$",
        supplier_text,
        flags=re.MULTILINE,
    )

    suppliers = [
        Supplier(
            name=name.strip(),
            business_type=business_type.strip(),
            jurisdiction=jurisdiction.strip(),
            priority=0,
            priority_reason="Recovered from the request after planning failed.",
        )
        for name, business_type, jurisdiction in matches
    ]

    if not suppliers:
        raise RuntimeError("The supplier list could not be recovered from REQUEST.md.")

    def risk_key(supplier: Supplier) -> tuple[int, str]:
        text = f"{supplier.name} {supplier.business_type}".lower()
        ambiguous = any(
            term in text
            for term in ("trading", "general", "fze")
        )
        return (0 if ambiguous else 1, supplier.name.lower())

    suppliers.sort(key=risk_key)

    for priority, supplier in enumerate(suppliers, start=1):
        supplier.priority = priority

    return Plan(
        ordered_suppliers=suppliers,
        budget_strategy=(
            "Structured planning failed twice. The request was recovered "
            "deterministically, with ambiguous trading entities placed first."
        ),
    )

def triage(state: State) -> State:
    """
    Read the email. Pull out the suppliers. Decide the order.

    TODO (Step 2): extracting seven names is the easy half. The half that
                   counts is deciding which ones get the budget - because it
                   will run out before the list does.

                   Think about which check you would never skip, whatever the
                   supplier. That thought is worth more than the parsing.
    """
    prompt = f"""
                Read the incoming supplier request and create a risk-based screening plan.

REQUEST:
{state["request"]}

Rules:
- Extract all seven suppliers exactly once.
- Preserve each supplier name exactly as Procurement typed it.
- Extract the business type and jurisdiction stated in the request.
- Assign priority 1 to the supplier that should be checked first.
- Give every supplier a clear priority reason.
- Prioritize ambiguous, unfamiliar, and higher-risk trading entities.
- Do not invent an individual annual value. Only the combined value is known.
- Procurement typed the names by hand, so exact legal-name matching may fail.
- The plan must explain how the nine registry lookups will be allocated.
"""

    structured_llm = llm.with_structured_output(Plan)

    try:
        plan = structured_llm.invoke(prompt)
    except Exception:
        try:
            # Retry once if the model fails to return valid structured output.
            plan = structured_llm.invoke(
                prompt + "\nReturn a valid Plan matching the required schema exactly."
            )
        except Exception:
            # Preserve the run instead of losing all work to a malformed reply.
            plan = fallback_plan(state["request"])

    planned_names = [supplier.name for supplier in plan.ordered_suppliers]
    if len(planned_names) != 7 or len(set(planned_names)) != 7:
        plan = fallback_plan(state["request"])

    ordered_suppliers = sorted(
        plan.ordered_suppliers,
        key=lambda supplier: supplier.priority,
    )

    BUDGET["used"] = 0

    state["plan"] = plan
    state["queue"] = ordered_suppliers
    state["current_supplier"] = None
    state["current_evidence"] = []
    state["evidence"] = []
    state["verdicts"] = []
    state["skipped"] = []
    state["memo"] = None

    print("\nSCREENING PLAN")
    print("=" * 60)
    print(plan.budget_strategy)

    for supplier in ordered_suppliers:
        print(
            f"{supplier.priority}. {supplier.name} "
            f"({supplier.jurisdiction})"
        )
        print(f"   Reason: {supplier.priority_reason}")

        sanctions_result = sanctions_screen(supplier.name)

        state["evidence"].append(
            (
                supplier.name,
                f"SANCTIONS SCREEN:\n{sanctions_result}",
            )
        )

    return state


def screen_reason(state: ScreeningState) -> ScreeningState:
    """Choose one next registry action for one supplier."""
    supplier = state["supplier"]
    observations = (
        "\n\n".join(state["scratchpad"])
        if state["scratchpad"]
        else "Nothing collected yet"
    )

    prompt = f"""
Screen exactly one supplier using a ReAct loop.

SUPPLIER:
Name: {supplier.name}
Business type: {supplier.business_type}
Jurisdiction: {supplier.jurisdiction}

OBSERVATIONS SO FAR:
{observations}

Choose exactly one next action: gleif_lookup, web_search, or finish.

Rules:
- Never repeat a lookup already shown in the observations.
- Normally use GLEIF first to establish the legal entity.
- Use web_search only when GLEIF returned NO_RECORDS and another source is
  needed to distinguish a real company from an entity with no trace.
- NO_RECORDS is evidence; it is different from LOOKUP_UNAVAILABLE.
- If GLEIF returned candidates, do not use web search merely to confirm them.
- Finish when the evidence is sufficient for the decision node, when an
  essential lookup was unavailable, or when no useful lookup remains.
- Do not make the final APPROVE/CONDITIONS/REJECT/INSUFFICIENT verdict here.
"""

    structured_llm = llm.with_structured_output(ScreeningAction)

    try:
        chosen_action = structured_llm.invoke(prompt)
    except Exception:
        try:
            chosen_action = structured_llm.invoke(
                prompt + "\nReturn a valid ScreeningAction matching the schema exactly."
            )
        except Exception as error:
            state["failure"] = f"Structured screening decision failed: {error}"
            state["done"] = True
            return state

    state["action"] = chosen_action.model_dump()
    return state


def screen_act(state: ScreeningState) -> ScreeningState:
    """Execute one selected registry action while enforcing the budget."""
    action = state["action"]
    supplier = state["supplier"]

    if action is None:
        state["failure"] = "No screening action was produced."
        state["done"] = True
        return state

    state["steps_used"] += 1
    tool = action["tool"]

    if tool == "finish":
        state["done"] = True

        return state
        if tool == "web_search":
            gleif_has_no_records = any(
            item.strip() == f"GLEIF LOOKUP:\n{NO_RECORDS}"
            for item in state["scratchpad"]
        )

        if not gleif_has_no_records:
            # Web evidence is useful only when GLEIF returned no candidates.
            # Stop instead of spending budget on a redundant lookup.
            state["done"] = True
            return state

    prefix = "GLEIF LOOKUP:" if tool == "gleif_lookup" else "WEB SEARCH:"
    if any(item.startswith(prefix) for item in state["scratchpad"]):
        state["failure"] = f"The agent attempted to repeat {tool}."
        state["done"] = True
        return state

    if not spend(f"{tool}: {supplier.name}"):
        state["scratchpad"].append(
            f"{prefix}\nNOT_RUN_BUDGET_EXHAUSTED"
        )
        state["failure"] = "The lookup budget was exhausted."
        state["done"] = True
        return state

    try:
        if tool == "gleif_lookup":
            result = gleif_lookup(supplier.name)
        else:
            query = action.get("query") or (
                f"{supplier.name} {supplier.jurisdiction}"
            )
            result = web_search(query)
    except Exception as error:
        result = f"{LOOKUP_UNAVAILABLE}: {error}"

    state["scratchpad"].append(f"{prefix}\n{result}")

    if state["steps_used"] >= MAX_SCREEN_STEPS:
        state["done"] = True

    return state


def screen_react_done(state: ScreeningState) -> str:
    """Route the ReAct subgraph without mutating its state."""
    if state["done"]:
        return "end"

    if state["steps_used"] >= MAX_SCREEN_STEPS:
        return "end"

    if BUDGET["used"] >= MAX_LOOKUPS:
        return "end"

    return "loop"


def build_screening_react_graph():
    """Compile the reused reason -> act -> observe loop for one supplier."""
    graph = StateGraph(ScreeningState)
    graph.add_node("reason", screen_reason)
    graph.add_node("act", screen_act)
    graph.set_entry_point("reason")
    graph.add_edge("reason", "act")
    graph.add_conditional_edges(
        "act",
        screen_react_done,
        {
            "loop": "reason",
            "end": END,
        },
    )
    return graph.compile()


SCREENING_REACT_APP = build_screening_react_graph()


def screen(state: State) -> State:
    """
    Gather evidence on the NEXT supplier in the queue.

    TODO (Step 3): this is where your Module 3 ReAct agent earns its keep.
                   Do not write a new reason/act loop here - hand ONE supplier
                   to the agent you already built and let it decide which
                   registry to ask and when it has seen enough.

                   Call spend() before every lookup. If it returns False,
                   stop - do not silently exceed the budget.

                   Note: when a registry returns NO_RECORDS you have not
                   learned nothing. You have learned something. What?
    """
    if not state["queue"]:
        return state

    supplier = state["queue"].pop(0)
    state["current_supplier"] = supplier

    state["current_evidence"] = [
        evidence_text
        for supplier_name, evidence_text in state["evidence"]
        if supplier_name == supplier.name
    ]
    if has_sanctions_hit(state["current_evidence"]):
        # A strong sanctions match is already enough to stop further checks.
        return state

    starting_evidence_count = len(state["current_evidence"])
    screening_result = SCREENING_REACT_APP.invoke(
        {
            "supplier": supplier,
            "scratchpad": list(state["current_evidence"]),
            "action": None,
            "done": False,
            "steps_used": 0,
            "failure": None,
        },
        config={"recursion_limit": 12},
    )

    state["current_evidence"] = screening_result["scratchpad"]

    for item in state["current_evidence"][starting_evidence_count:]:
        state["evidence"].append((supplier.name, item))

    if screening_result.get("failure"):
        failure_evidence = (
            "SCREENING AGENT FAILURE:\n"
            f"{screening_result['failure']}"
        )
        state["current_evidence"].append(failure_evidence)
        state["evidence"].append((supplier.name, failure_evidence))

    return state

def decide(state: State) -> State:
    """
    Turn the evidence for one supplier into one of the four verdicts.

    TODO (Step 4): read the four traps in INSTRUCTIONS.md before you write
                   this prompt. At least three of them live in this function.
    """
    supplier = state["current_supplier"]

    if supplier is None:
        return state

    if has_sanctions_hit(state["current_evidence"]):
        verdict = Verdict(
            supplier=supplier.name,
            verdict="REJECT",
            reason=(
                "The supplier has a name match at or above the 0.90 "
                "OFAC sanctions threshold. Releasing payment is prohibited."
            ),
            next_action=(
                "Do not release payment. Refer the case to Legal and "
                "do not contact the supplier directly."
            ),
        )

        state["verdicts"].append(verdict)

        print(f"\n{verdict.verdict}: {verdict.supplier}")
        print(f"Reason: {verdict.reason}")
        print(f"Next action: {verdict.next_action}")

        state["current_supplier"] = None
        state["current_evidence"] = []

        return state

    evidence_text = (
        "\n\n".join(state["current_evidence"])
        if state["current_evidence"]
        else "NO EVIDENCE COLLECTED"
    )

    gleif_has_no_record = any(
        evidence.strip() == f"GLEIF LOOKUP:\n{NO_RECORDS}"
        for evidence in state["current_evidence"]
    )
    web_has_no_result = any(
        evidence.strip() == "WEB SEARCH:\nNO_RESULTS"
        for evidence in state["current_evidence"]
    )

    if gleif_has_no_record and web_has_no_result:
        verdict = Verdict(
            supplier=supplier.name,
            verdict="REJECT",
            reason=(
                "The completed GLEIF and web checks found no trace from which "
                "a legal entity could be established."
            ),
            next_action=(
                "Do not release payment. Ask Procurement to provide a certificate "
                "of incorporation or official registration number before reconsideration."
            ),
        )

        state["verdicts"].append(verdict)

        print(f"\n{verdict.verdict}: {verdict.supplier}")
        print(f"Reason: {verdict.reason}")
        print(f"Next action: {verdict.next_action}")

        state["current_supplier"] = None
        state["current_evidence"] = []

        return state

    candidate_blocks = evidence_text.split("\n\n")

    active_but_lapsed = any(
    "exact name match: yes" in block.lower()
    and "entity status: active" in block.lower()
    and "registration status: lapsed" in block.lower()
    for block in candidate_blocks
)

    if active_but_lapsed:
        verdict = Verdict(
            supplier=supplier.name,
            verdict="CONDITIONS",
            reason=(
                "The legal entity is ACTIVE, but its LEI registration is "
                "LAPSED, meaning the LEI record is overdue for renewal. "
                "This does not by itself mean that the company is inactive."
            ),
            next_action=(
                "Request a renewed LEI record or current official company "
                "registration evidence before releasing payment."
            ),
        )

        state["verdicts"].append(verdict)

        print(f"\n{verdict.verdict}: {verdict.supplier}")
        print(f"Reason: {verdict.reason}")
        print(f"Next action: {verdict.next_action}")

        state["current_supplier"] = None
        state["current_evidence"] = []

        return state

    gleif_was_completed = any(
        evidence.startswith("GLEIF LOOKUP:")
        and "NOT_RUN_BUDGET_EXHAUSTED" not in evidence
        and str(LOOKUP_UNAVAILABLE) not in evidence
        for evidence in state["current_evidence"]
    )

    if not gleif_was_completed:
        verdict = Verdict(
            supplier=supplier.name,
            verdict="INSUFFICIENT",
            reason=(
                "The supplier's legal identity could not be checked reliably "
                "because the required GLEIF lookup was not completed."
            ),
            next_action=(
                "Hold payment and complete the GLEIF lookup, or request the "
                "supplier's LEI or official registration number."
            ),
        )

        state["verdicts"].append(verdict)

        print(f"\n{verdict.verdict}: {verdict.supplier}")
        print(f"Reason: {verdict.reason}")
        print(f"Next action: {verdict.next_action}")

        state["current_supplier"] = None
        state["current_evidence"] = []

        return state

    prompt = f"""
Review the retrieved evidence and make one actionable supplier decision.

SUPPLIER:
Name: {supplier.name}
Business type: {supplier.business_type}
Jurisdiction: {supplier.jurisdiction}

RETRIEVED EVIDENCE:
{evidence_text}

Return exactly one of:
APPROVE, CONDITIONS, REJECT, or INSUFFICIENT.

Decision rules:

1. SANCTIONS
- Treat similarity scores below 0.90 as possible fuzzy-match noise.
- REJECT only when the evidence shows a strong name match at or above 0.90
  and the listed name reasonably identifies this supplier.
- If sanctions screening was unavailable, do not APPROVE. Return
  INSUFFICIENT and require a completed sanctions screen.

2. GLEIF IDENTITY
- Do not assume the first GLEIF result is the requested supplier.
- If several legal entities are returned and there is no single exact match,
  return CONDITIONS and request the LEI or registration number.
- If there is one exact match with ACTIVE entity status and ISSUED
  registration status, it may be APPROVED if the sanctions screen is clean.
- If the entity is ACTIVE but its registration is LAPSED, return CONDITIONS
  and request current legal-entity or LEI confirmation.

3. NO GLEIF RECORD
- NO_RECORDS does not prove that the supplier is fake.
- If reliable web evidence clearly shows that it is a real company, return
  CONDITIONS and request a certificate of incorporation, LEI, or official
  registration number before payment.
- If both GLEIF and web search return no trace, return REJECT because no
  legal entity could be established.

4. UNAVAILABLE OR INCOMPLETE EVIDENCE
- LOOKUP_UNAVAILABLE means the check did not complete; it is not the same
  as NO_RECORDS.
- If an essential lookup was unavailable, or a required lookup was not run
  because the budget ended, return INSUFFICIENT and state the exact check
  or document needed.

General rules:
- Use only the evidence shown above.
- Do not invent facts, registration numbers, statuses, or sanctions matches.
- Make the reason concise and suitable for Procurement.
- Make next_action specific and immediately actionable.
"""

    structured_llm = llm.with_structured_output(Verdict)

    try:
        verdict = structured_llm.invoke(prompt)
    except Exception:
        try:
            verdict = structured_llm.invoke(
                prompt
                + "\nReturn a valid Verdict matching the required schema exactly."
            )
        except Exception:
            verdict = Verdict(
                supplier=supplier.name,
                verdict="INSUFFICIENT",
                reason=(
                    "The decision model failed twice, so the retrieved evidence "
                    "could not be assessed reliably."
                ),
                next_action=(
                    "Hold payment and have Compliance review the retrieved "
                    "registry evidence manually."
                ),
            )

    # Keep the supplier name consistent with the original request.
    verdict.supplier = supplier.name

    state["verdicts"].append(verdict)

    print(f"\n{verdict.verdict}: {verdict.supplier}")
    print(f"Reason: {verdict.reason}")
    print(f"Next action: {verdict.next_action}")

    state["current_supplier"] = None
    state["current_evidence"] = []

    return state


def budget_left(state: State) -> str:
    """
    Router. Reads only - anything written here is discarded.

    TODO (Step 5): "next" while there is queue AND budget, else "memo".
    """
    if state["queue"] and BUDGET["used"] < MAX_LOOKUPS:
        return "next"

    return "memo"


def write_memo(state: State) -> State:
    """
    The deliverable.

    TODO (Step 6): every supplier gets a line, INCLUDING the ones you never
                   checked. Print the lookup count. Hiding what you skipped
                   is the one unforgivable bug in this project.
    """
    skipped_names = {
        supplier.name
        for supplier in state["skipped"]
    }

    # Any suppliers still in the queue were not fully checked.
    for supplier in state["queue"]:
        if supplier.name not in skipped_names:
            state["skipped"].append(supplier)
            skipped_names.add(supplier.name)

    state["queue"] = []

    total_suppliers = (
        len(state["plan"].ordered_suppliers)
        if state["plan"] is not None
        else len(state["verdicts"]) + len(state["skipped"])
    )

    lines = [
        (
            f"SUPPLIER REVIEW · Thursday payment run · "
            f"{total_suppliers} suppliers · "
            f"{BUDGET['used']} lookups used"
        ),
        "",
    ]

    for verdict in state["verdicts"]:
        lines.extend(
            [
                f"## {verdict.verdict} — {verdict.supplier}",
                "",
                verdict.reason,
                "",
                f"**Next action:** {verdict.next_action}",
                "",
            ]
        )

    if state["skipped"]:
        lines.extend(
            [
                "## NOT CHECKED (budget)",
                "",
            ]
        )

        for supplier in state["skipped"]:
            lines.extend(
                [
                    f"### {supplier.name}",
                    "",
                    (
                        f"{supplier.business_type}, "
                        f"{supplier.jurisdiction}. The mandatory sanctions "
                        f"screen was completed, but the legal-entity review "
                        f"was not completed because the lookup budget ended."
                    ),
                    "",
                    (
                        "**Verdict:** INSUFFICIENT — identity not fully assessed."
                    ),
                    "",
                    (
                        "**Next action:** Request the supplier's certificate "
                        "of incorporation, LEI, or official registration number "
                        "and complete the registry check before payment."
                    ),
                    "",
                ]
            )

    memo = "\n".join(lines).strip() + "\n"

    state["memo"] = memo

    with open("MEMO.md", "w", encoding="utf-8") as file:
        file.write(memo)

    print("\n" + memo)
    print("MEMO.md created.")

    return state


def build_graph():
    """
    TODO (Step 7): wire it. triage -> screen -> decide -> (loop | memo)

    The loop-back edge is the whole point, same as Module 3. If you find
    yourself writing `for s in suppliers:` inside a node, stop and reread
    the executor in the Module 3 solution.
    """
    graph = StateGraph(State)

    graph.add_node("triage", triage)
    graph.add_node("screen", screen)
    graph.add_node("decide", decide)
    graph.add_node("write_memo", write_memo)

    graph.set_entry_point("triage")

    graph.add_edge("triage", "screen")
    graph.add_edge("screen", "decide")

    graph.add_conditional_edges(
        "decide",
        budget_left,
        {
            "next": "screen",
            "memo": "write_memo",
        },
    )

    graph.add_edge("write_memo", END)

    return graph.compile()


# ===========================================================================
if __name__ == "__main__":
    print("Vendor Onboarding Desk\n")

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is missing.")
        sys.exit(1)

    if not os.path.exists("REQUEST.md"):
        print("REQUEST.md was not found.")
        print("Run this file from the bridge-project directory.")
        sys.exit(1)

    with open("REQUEST.md", "r", encoding="utf-8") as file:
        request_text = file.read()

    initial_state: State = {
        "request": request_text,
        "queue": [],
        "evidence": [],
        "current_evidence": [],
        "verdicts": [],
        "skipped": [],
        "plan": None,
        "current_supplier": None,
        "memo": None,
    }

    app = build_graph()

    result = app.invoke(
        initial_state,
        config={"recursion_limit": 50},
    )

    print("\nRun completed.")
    print(f"Lookups used: {BUDGET['used']}/{MAX_LOOKUPS}")
    print(f"Verdicts produced: {len(result['verdicts'])}")
    print(f"Suppliers skipped: {len(result['skipped'])}")
