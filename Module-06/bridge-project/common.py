"""
common.py - the four things every file in this project needs. GIVEN.

    chat(messages)            one ChatOpenAI via OpenRouter; returns (text, prompt_tokens as billed)
    structured(schema, ...)   one structured-output call, retried once, None on failure
    count_tokens(text)        tiktoken estimate, no API call - the short-term budget uses this
    say(...)                  print, so receipts can be silenced in one place
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                     # noqa: BLE001
        pass

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
load_dotenv(REPO / ".env")
load_dotenv()

MODEL = os.getenv("MODEL", "openai/gpt-4o-mini")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

say = print
_llms: dict = {}
CALLS = {"n": 0}


def llm(temperature: float = 0.0):
    if temperature not in _llms:
        from langchain_openai import ChatOpenAI
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            sys.exit("OPENROUTER_API_KEY is not set. It lives in the repo-root .env, same as every module.")
        _llms[temperature] = ChatOpenAI(model=MODEL, temperature=temperature, base_url=BASE_URL,
                                        api_key=key, max_tokens=600)
    return _llms[temperature]


def chat(messages, temperature: float = 0.0) -> tuple[str, int]:
    """messages: list of (role, text). Returns (answer, prompt_tokens as billed)."""
    CALLS["n"] += 1
    resp = llm(temperature).invoke(messages)
    usage = resp.usage_metadata or {}
    return resp.content.strip(), int(usage.get("input_tokens", 0))


def structured(schema, prompt: str, fallback=None):
    """One structured-output call, retried once. A single bad reply must not kill a session."""
    for attempt in (1, 2):
        CALLS["n"] += 1
        try:
            return llm(0.0).with_structured_output(schema).invoke(prompt)
        except Exception:                                 # noqa: BLE001
            if attempt == 2:
                return fallback
    return fallback


_enc = None


def count_tokens(text: str) -> int:
    global _enc
    if _enc is None:
        import tiktoken
        _enc = tiktoken.get_encoding("o200k_base")
    return len(_enc.encode(text or ""))
