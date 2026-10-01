"""
Check both memories against a throwaway store before you spend a game night on them.

    python verify_memory.py               # tests campaign_memory.py

Seventeen checks. Four of them make a model call (extract and fold are model
calls by design) and are marked [llm]; the rest are free. About a minute.
"""

from __future__ import annotations

import datetime as dt
import importlib
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    M = importlib.import_module("campaign_memory")
except ModuleNotFoundError:
    print("campaign_memory.py not found - copy campaign_memory_starter.py to campaign_memory.py first.")
    sys.exit(2)

results: list[tuple[bool, str, str]] = []


def check(label, fn, why):
    ok = False
    try:
        ok = bool(fn())
    except NotImplementedError as e:
        why = f"still raises NotImplementedError ({e}) - that one is yours"
    except Exception as e:                                # noqa: BLE001
        why = f"{why} (raised {type(e).__name__}: {e})"
    results.append((ok, label, "" if ok else why))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")


D1 = dt.date(2026, 8, 14)
tmp = Path(tempfile.mkdtemp(prefix="verify_campaign_"))
print(f"throwaway store: {tmp}\n")

# -------------------------------------------------------------- short-term --
stm = M.ShortTermMemory(budget=300, keep_last=2)
for i in range(6):
    stm.add("user", f"I walk to the {['inn', 'forge', 'mill', 'shrine', 'bridge', 'ferry'][i]} with my dog Biscuit and look around carefully.")
    stm.add("assistant", "You arrive. The place is busy and smells of bread. " * 4)

check("short-term: should_fold() is False under budget",
      lambda: not M.ShortTermMemory(budget=10_000).should_fold() and
              (lambda s: (s.add("user", "hi"), s.add("assistant", "hello"), not s.should_fold())[-1])(M.ShortTermMemory(budget=10_000)),
      "an empty or tiny buffer must not fold")
check("short-term: should_fold() is True over budget",
      lambda: stm.should_fold(), f"buffer is {stm.tokens()} tokens against a budget of 300")
before = stm.tokens()
check("short-term: fold() shrinks the context and keeps KEEP_LAST turns verbatim  [llm]",
      lambda: (stm.fold(), len(stm.buffer) == 2 and stm.summary and stm.tokens() < before and stm.folds == 1)[-1],
      "after a fold: keep_last turns verbatim, a non-empty summary, fewer tokens, folds == 1")
check("short-term: the summary keeps what must survive (the dog's name)  [llm]",
      lambda: "biscuit" in stm.summary.lower(),
      "the fold prompt must tell the model what to keep; a companion's name is inventory")
check("short-term: context() is a system summary followed by real turns",
      lambda: (lambda c: c and c[0][0] == "system" and "summary" in c[0][1].lower() and c[1:] == stm.buffer)(stm.context()),
      "[('system', 'SUMMARY...'), then the buffer as (role, text)]")
check("short-term: fold(drop='Biscuit') removes the subject from the summary  [llm]",
      lambda: (stm.add("user", "I check my pack."), stm.add("assistant", "Biscuit wags. You have rope."),
               stm.add("user", "ok"), stm.add("assistant", "Sure."), stm.fold(drop="Biscuit"),
               "biscuit" not in stm.summary.lower())[-1],
      "a retcon must rewrite the summary, not just the store")

# --------------------------------------------------------------- long-term --
col = M.open_store(tmp)
ltm = M.LongTermMemory(col)
check("long-term: the store uses cosine", lambda: (col.metadata or {}).get("hnsw:space") == "cosine",
      "without cosine every similarity is negative")
check("long-term: DB_DIR is anchored to the file", lambda: M.DB_DIR.is_absolute() and M.DB_DIR.name == "memory_store",
      "Path(__file__).resolve().parent / 'memory_store'")

facts = []
def _extract():
    global facts
    facts = ltm.extract("Call my character Dax and keep it light. I go find the smith - what's her name?",
                        "The smith is Marra, a broad woman with soot on her sleeves. She waves you in.")
    types = {f.type for f in facts}
    return any(f.type == "preference" for f in facts) and any(f.type == "npc" and "marra" in f.subject.lower() for f in facts)
check("long-term: extract() returns a preference and an npc fact from a real exchange  [llm]", _extract,
      "expected at least one 'preference' (Dax / tone) and one 'npc' (Marra)")
check("long-term: extract() returns [] for chatter  [llm]",
      lambda: ltm.extract("Good session, let's stop here for tonight.", "See you next week!") == [],
      "a sign-off is not a fact")

check("long-term: remember() writes active rows with type, date, ts, night",
      lambda: ltm.remember(facts, D1, 1) >= 2 and all(
          m["status"] == "active" and m["night"] == 1 and m["date"] == "2026-08-14" and isinstance(m["ts"], (int, float))
          for m in col.get(include=["metadatas"])["metadatas"]),
      "metadata: type, subject, subject_norm, text, status, night, date, ts")

dead = M.Fact(type="npc", subject="Marra", text="Marra died in the forge fire.", supersedes="Marra alive, the smith")
def _supersede():
    ltm.remember([dead], D1 + dt.timedelta(days=7), 2)
    rows = col.get(where={"type": "npc"}, include=["metadatas"])["metadatas"]
    marra = [m for m in rows if "marra" in m["subject"].lower()]
    return any(m["status"] == "superseded" for m in marra) and sum(m["status"] == "active" for m in marra) == 1
check("long-term: a superseding fact marks the old row superseded and keeps it", _supersede,
      "update status, do not delete - night 3 asks when Marra died")

check("long-term: recall('is Marra alive') returns the death, not the old row",
      lambda: (lambda h: h and h[0]["subject"].lower().startswith("marra") and "died" in h[0]["text"].lower())(
          ltm.recall("Is Marra the smith still alive?", D1 + dt.timedelta(days=30))),
      "filter status=active IN the query")
try:
    ltm.remember([M.Fact(type="npc", subject="Mirra", text="Mirra runs the herbalist's shop behind the green door.")], D1, 1)
except Exception:                                         # noqa: BLE001 - reported by the remember() check above
    pass
check("long-term: recall('is Mirra alive') never returns Marra (identity check)",
      lambda: all("marra" not in h["subject"].lower() for h in ltm.recall("Is Mirra the herbalist alive?", D1 + dt.timedelta(days=30))),
      "the line names Mirra; npc hits about anyone else must be dropped")
check("long-term: only events decay",
      lambda: abs(ltm.decay(0.8, "event", 28) - 0.2) < 0.01 and ltm.decay(0.8, "npc", 400) == 0.8 and ltm.decay(0.8, "preference", 400) == 0.8,
      "event: sim * 0.5 ** (age / EVENT_HALF_LIFE_DAYS); everything else unchanged")
check("long-term: forget('Marra') deletes every row about her and reports 0 remaining",
      lambda: (lambda r: r[0] >= 2 and r[1] == 0)(ltm.forget("Marra")),
      "delete by subject identity across all statuses, then count again")
check("cite: names the night, the date and the age",
      lambda: (lambda c: "night 1" in c and "2026-08-14" in c and "30" in c)(
          M.cite({"night": 1, "date": "2026-08-14", "age": 30})),
      "(remembered from night 1, 2026-08-14, 30 days ago)")

# ---------------------------------------------------------------- report --
print("-" * 76)
n_fail = sum(1 for ok, _, _ in results if not ok)
for ok, label, why in results:
    if not ok:
        print(f"  FAIL  {label}\n        -> {why}")
shutil.rmtree(tmp, ignore_errors=True)
if n_fail:
    print(f"{n_fail} of {len(results)} checks failed. Fix these before a game night.")
    sys.exit(1)
print(f"all {len(results)} checks passed - both memories are sound. Run night 1.")
