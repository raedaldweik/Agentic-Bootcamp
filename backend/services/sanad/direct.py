"""Answers without a language model.

When no model key is configured, or the model cannot be reached, the standard
questions are still answered: the router picks the view, and the view's own summary,
card and next questions are the answer. Procedure questions fall back to the best
passage in the approved documents. It cannot hold a conversation or take an action,
and it says so rather than guessing.
"""
from __future__ import annotations

import re
from typing import Any

from . import corpus, router, tools

_GREETING = re.compile(r"^\s*(hi|hello|hey|salam|marhaba|good (morning|afternoon|evening)|thanks?|thank you|ok(ay)?|test(ing)?)\b[\s!.?]*$", re.I)
_ACTION = router._ACTION
_WHAT_IF = router._WHAT_IF
CAPABILITIES = ("I cover this shop's engines, parts, tools, job cards, inspection findings and approvals. "
                "Try one of the suggested questions, or ask about an engine, a tool or a job card by its id.")


def answer(question: str, ctx: tools.Context, *, history: list[str], prefetched: list[tuple[str, dict]], model_configured: bool) -> dict[str, Any]:
    """{text, cards, followups} from the views and the documents alone."""
    limited = ("" if model_configured else
               "\n\n_The language model is not connected, so I can answer the standard questions only._")
    q = (question or "").strip()
    if _GREETING.match(q):
        return {"text": "Hello. " + CAPABILITIES, "cards": [], "followups": [s["prompt"] for s in ctx.persona["suggestions"][:3]]}

    if prefetched:
        handle, result = prefetched[0]
        return {"text": result["summary"], "cards": [handle] if result.get("card") else [],
                "followups": _followups(result, q)}

    if _ACTION.match(q):
        return {"text": "I can't take that action right now: raising requests and drafting records needs the language model, which is "
                        + ("temporarily unavailable. Please try again in a moment." if model_configured else "not connected.")
                        + " I can still show the current status.", "cards": [],
                "followups": [s["prompt"] for s in ctx.persona["suggestions"][:3]]}

    if _WHAT_IF.search(q.lower()):
        handle, result = tools.run_view("protect_delivery", {}, ctx)
        return {"text": "I can't run a custom what-if right now" + (" because the language model is temporarily unavailable" if model_configured else " without the language model")
                        + ". Here are the levers that are open now and what each is worth.\n\n" + result["summary"],
                "cards": [handle] if result.get("card") else [], "followups": _followups(result, q)}

    hits = corpus.search(q, top_k=2)
    if hits and _covers(q, hits[0]):
        top = hits[0]
        for h in hits:
            ctx.passages.append(h)
        excerpt = re.sub(r"\s+", " ", top["text"]).strip()
        if len(excerpt) > 520:
            excerpt = excerpt[:520].rsplit(" ", 1)[0] + " ..."
        return {"text": f"From **{top['title']}**, page {top['page']}, {top['section']}:\n\n> {excerpt}" + limited,
                "cards": [], "followups": [s["prompt"] for s in ctx.persona["suggestions"][:3]]}

    return {"text": "I don't have a ready answer for that. " + CAPABILITIES + limited, "cards": [],
            "followups": [s["prompt"] for s in ctx.persona["suggestions"][:3]]}


def _covers(question: str, hit: dict) -> bool:
    """Whether a passage is really about the question: most of its meaningful words appear in it."""
    words = set(corpus._tokens(question))
    if len(words) < 2:
        return False
    found = words & set(corpus._tokens(hit["title"] + " " + hit["section"] + " " + hit["text"]))
    return len(found) >= 2 and len(found) / len(words) >= 0.5


def _followups(result: dict, question: str) -> list[str]:
    asked = _norm(question)
    return [f for f in result.get("followups") or [] if _norm(f) != asked][:3]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
