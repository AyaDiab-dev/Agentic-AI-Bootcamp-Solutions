"""
run_campaign.py - one game night per process. GIVEN.

    python run_campaign.py --night 1              # your campaign_memory.py; wipes the store first
    python run_campaign.py --night 2              # NEW PROCESS. Quiz on night 1, then play
    python run_campaign.py --night 3              # NEW PROCESS. Quiz on nights 1-2, retcon, play
    python run_campaign.py --night 2 --goldfish   # the control: no memory at all
    python run_campaign.py --play                 # free play, your memory, tonight's date

The three nights are dated relative to today, so a fact from night 1 is 37 days
old on night 3 without anybody waiting:

    night 1   today - 37 d     the party arrives
    night 2   today - 30 d     a week later
    night 3   today            a month after that

Each night MUST be a separate process. Short-term memory dies with the process -
that is the point - and only what your LongTermMemory wrote is there next time.

Outputs in out/:  RECEIPT.txt  receipt.json  transcript-nightN.md  quiz-nightN.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE))

from common import CALLS, say   # noqa: E402

TODAY = dt.date.today()
NIGHTS = {1: TODAY - dt.timedelta(days=37), 2: TODAY - dt.timedelta(days=30), 3: TODAY}


def load_memory():
    if (HERE / "campaign_memory.py").exists():
        mod = importlib.import_module("campaign_memory")
        say("[memory] campaign_memory.py  (yours)")
        return mod
    mod = importlib.import_module("campaign_memory_starter")
    sys.modules["campaign_memory"] = mod
    say("[memory] campaign_memory_starter.py  - copy it to campaign_memory.py first")
    return mod


def script_lines(night: int) -> list[str]:
    text = (HERE / "world" / f"player_night{night}.md").read_text(encoding="utf-8")
    return [ln[2:].strip() if ln.startswith("- ") else ln.strip()
            for ln in text.splitlines() if ln.startswith("- ") or ln.startswith("/")]


def load_rows() -> list[dict]:
    p = OUT / "receipt.json"
    return json.loads(p.read_text()) if p.exists() else []


def save_rows(rows: list[dict]) -> None:
    (OUT / "receipt.json").write_text(json.dumps(rows, indent=1))


def render_receipt(rows: list[dict]) -> str:
    L = ["RECEIPT - the campaign", f"generated {TODAY.isoformat()}", ""]
    for mode in ("memory", "goldfish"):
        sel = [r for r in rows if r["mode"] == mode]
        if not sel:
            continue
        L.append(f"{mode.upper()} GAME MASTER")
        L.append(f"{'night':>5}  {'as of':<11} {'turns':>5} {'folds':>5} {'max prompt':>10} {'area':>7} "
                 f"{'quiz':>7} {'facts stored':>12} {'model calls':>11}")
        for r in sorted(sel, key=lambda r: r["night"]):
            quiz = f"{r['quiz_score']}/{r['quiz_total']}" if r.get("quiz_total") else "-"
            L.append(f"{r['night']:>5}  {r['asof']:<11} {r['turns']:>5} {r['folds']:>5} {r['max_prompt']:>10,} "
                     f"{r['area']:>7,} {quiz:>7} {r['facts_stored']:>12} {r['model_calls']:>11}")
        L.append("")
    for r in rows:
        if r.get("forget"):
            f = r["forget"]
            L.append(f"retcon '{f['subject']}' (night {r['night']}): {f['deleted']} rows deleted, {f['remaining']} remaining; "
                     f"summary mentions it after re-fold: {'YES <- not gone' if f['in_summary'] else 'no'}; "
                     f"GM's next answer mentions it: {'yes - read it' if f['in_reply'] else 'no'}")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--night", type=int, choices=(1, 2, 3))
    ap.add_argument("--goldfish", action="store_true", help="the control: no memory")
    ap.add_argument("--play", action="store_true", help="free play with your memory, dated today")
    ap.add_argument("--keep", action="store_true", help="do not wipe the store before night 1")
    ap.add_argument("--quiz-only", action="store_true", help="ask tonight's quiz and stop (cheap: ~10 calls, nothing stored)")
    args = ap.parse_args()
    if not args.night and not args.play:
        ap.error("--night N or --play")

    mem = load_memory()
    OUT.mkdir(exist_ok=True)

    if args.night == 1 and not args.keep and not args.goldfish:
        shutil.rmtree(mem.DB_DIR, ignore_errors=True)        # wipe BEFORE anything opens it
        say(f"[store] wiped {mem.DB_DIR}")

    import gm_base
    night = args.night or 3
    asof = NIGHTS[night] if args.night else TODAY
    use_memory = not args.goldfish
    ltm = mem.LongTermMemory() if use_memory else None
    stm = mem.ShortTermMemory() if use_memory else None
    gm = gm_base.GameMaster(use_memory, asof, night, ltm, stm)

    say("\n" + "#" * 78)
    say(f"# GAME NIGHT {night}  -  {asof.isoformat()}  -  {'MEMORY' if use_memory else 'GOLDFISH'} game master")
    if use_memory:
        say(f"# store: {mem.DB_DIR}  ({ltm.col.count()} facts on disk at start)")
    say("#" * 78)

    # ------------------------------------------------------------- free play --
    if args.play:
        say("\nFree play. Type your line; 'quit' to stop.\n")
        while True:
            try:
                line = input("you > ").strip()
            except EOFError:
                break
            if line.lower() in ("quit", "exit", "q"):
                break
            r = gm.respond(line)
            say(f"\nGM  > {r['text']}\n      [prompt {r['prompt_tokens']} tok]\n")
        return

    # ------------------------------------------------------------------ quiz --
    quiz_score = quiz_total = 0
    quiz_rows: list[dict] = []
    quiz_path = HERE / "world" / f"quiz_night{night}.json"
    if quiz_path.exists():
        quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
        say(f"\nCONTINUITY QUIZ - {len(quiz['questions'])} questions about earlier nights, asked as the player\n")
        quiz_score, quiz_rows = gm_base.run_quiz(gm, quiz)
        quiz_total = len(quiz["questions"])
        say(f"\n    score {quiz_score}/{quiz_total}\n")
        (OUT / f"quiz-night{night}{'-goldfish' if args.goldfish else ''}.md").write_text(
            f"# Continuity quiz - night {night} - {'goldfish' if args.goldfish else 'memory'}\n\n"
            f"score {quiz_score}/{quiz_total}\n\n" +
            "\n".join(f"- {'ok  ' if r['ok'] else 'MISS'} **{r['q']}**\n  {r['answer']}" for r in quiz_rows),
            encoding="utf-8")
        if args.quiz_only:
            # re-quiz after a fix: update tonight's row on the receipt, play nothing, store nothing
            rows = load_rows()
            for r in rows:
                if r["mode"] == ("goldfish" if args.goldfish else "memory") and r["night"] == night:
                    r["quiz_score"], r["quiz_total"] = quiz_score, quiz_total
            save_rows(rows)
            (OUT / "RECEIPT.txt").write_text(render_receipt(rows) + "\n", encoding="utf-8")
            say(render_receipt(rows))
            return

    # ------------------------------------------------------------------ play --
    say("PLAY\n")
    transcript = [f"# Night {night} - {asof.isoformat()} - {'goldfish' if args.goldfish else 'memory'}\n"]
    forget_report = None
    pending_check = None
    for line in script_lines(night):
        if line.startswith("/forget "):
            subject = line[len("/forget "):].strip()
            if use_memory:
                say(f"\n  -- retcon: forget '{subject}' --")
                deleted, remaining = ltm.forget(subject)
                stm.fold(drop=subject)
                in_summary = subject.lower() in stm.summary.lower()
                say(f"    [short-term] summary mentions '{subject}': {'YES <- not gone' if in_summary else 'no'}")
                forget_report = {"subject": subject, "deleted": deleted, "remaining": remaining,
                                 "in_summary": in_summary, "in_reply": None}
                pending_check = subject
            continue
        say(f"you > {line}")
        r = gm.respond(line)
        say(f"GM  > {r['text']}\n      [prompt {r['prompt_tokens']} tok]\n")
        transcript.append(f"**you:** {line}\n\n**GM:** {r['text']}\n\n`prompt {r['prompt_tokens']} tok`\n")
        if pending_check:
            forget_report["in_reply"] = pending_check.lower() in r["text"].lower()
            say(f"    [check] GM's answer mentions '{pending_check}': {'yes - read it' if forget_report['in_reply'] else 'no'}\n")
            pending_check = None

    (OUT / f"transcript-night{night}{'-goldfish' if args.goldfish else ''}.md").write_text("\n".join(transcript), encoding="utf-8")

    # --------------------------------------------------------------- receipt --
    row = {"mode": "memory" if use_memory else "goldfish", "night": night, "asof": asof.isoformat(),
           "turns": gm.turns, "folds": stm.folds if stm else 0, "max_prompt": gm.max_prompt, "area": gm.area,
           "quiz_score": quiz_score, "quiz_total": quiz_total, "facts_stored": gm.facts_stored,
           "model_calls": CALLS["n"], "forget": forget_report}
    rows = [r for r in load_rows() if not (r["mode"] == row["mode"] and r["night"] == night)] + [row]
    save_rows(rows)
    receipt = render_receipt(rows)
    (OUT / "RECEIPT.txt").write_text(receipt + "\n", encoding="utf-8")
    say("\n" + receipt)
    if use_memory:
        say(f"\n{ltm.col.count()} facts on disk at end. Now STOP this process. Next night is a new one.")


if __name__ == "__main__":
    main()
