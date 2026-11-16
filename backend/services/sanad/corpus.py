"""The Sanad document collections, with page-level retrieval.

Each document is a Markdown file in backend/data/sanad/docs/ with a small header
(title, doc_id, collection, revision) and its pages separated by `<!-- page N -->`
markers. Pages are split into sections at headings, and retrieval is BM25 over
those sections, so every hit carries the document, the page and the section title.
No embedding model and no external service: it works the same everywhere.
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

DOCS_DIR = Path(os.getenv("SANAD_DOCS_DIR") or Path(__file__).resolve().parents[2] / "data" / "sanad" / "docs")

_STOP = set("a an and are as at be by for from has have if in into is it its of on or that the their this to was "
            "were will with what which when who how does do did shall should must may can per not no any each".split())
_PAGE = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.I)
_HEADING = re.compile(r"^#{1,4}\s+(.*)$", re.M)

_docs: list[dict[str, Any]] = []
_chunks: list[dict[str, Any]] = []
_df: Counter = Counter()
_avg_len = 1.0
_loaded = False


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower()):
        if w in _STOP:
            continue
        # light stemming so "intervals" finds "interval" and "inspections" finds "inspection"
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def _parse(path: Path) -> dict[str, Any] | None:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            for line in raw[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
            body = raw[end + 4:]
    parts = _PAGE.split(body)
    pages: list[tuple[int, str]] = []
    if len(parts) == 1:
        pages.append((1, body.strip()))
    else:
        if parts[0].strip():
            pages.append((1, parts[0].strip()))
        for i in range(1, len(parts) - 1, 2):
            pages.append((int(parts[i]), parts[i + 1].strip()))
    title = meta.get("title") or path.stem.replace("_", " ")
    return {"id": meta.get("doc_id") or path.stem, "title": title,
            "collection": meta.get("collection") or "Documents",
            "revision": meta.get("revision", ""), "file": path.name, "pages": pages}


def _sections(page_text: str) -> list[tuple[str, str]]:
    """Split a page at its headings: [(section title, text)]."""
    marks = list(_HEADING.finditer(page_text))
    if not marks:
        return [("", page_text)]
    out = []
    if page_text[:marks[0].start()].strip():
        out.append(("", page_text[:marks[0].start()].strip()))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(page_text)
        text = page_text[m.end():end].strip()
        if text:
            out.append((m.group(1).strip(), text))
    return out


def _load() -> None:
    global _loaded, _avg_len
    if _loaded:
        return
    for path in sorted(DOCS_DIR.glob("*.md")):
        doc = _parse(path)
        if not doc:
            continue
        _docs.append(doc)
        for page_no, page_text in doc["pages"]:
            for section, text in _sections(page_text):
                toks = _tokens(f"{doc['title']} {section} {text}")
                if not toks:
                    continue
                _chunks.append({"doc": doc, "page": page_no, "section": section, "text": text,
                                "tf": Counter(toks), "len": len(toks)})
    for c in _chunks:
        _df.update(c["tf"].keys())
    _avg_len = (sum(c["len"] for c in _chunks) / len(_chunks)) if _chunks else 1.0
    _loaded = True


def collections() -> list[dict[str, Any]]:
    """[{name, documents: [{id, title, revision, pages}]}] in a stable order."""
    _load()
    by: dict[str, list] = {}
    for d in _docs:
        by.setdefault(d["collection"], []).append(
            {"id": d["id"], "title": d["title"], "revision": d["revision"], "pages": len(d["pages"])})
    return [{"name": name, "documents": docs} for name, docs in sorted(by.items())]


def search(query: str, *, collection: str | None = None, top_k: int = 4) -> list[dict[str, Any]]:
    """BM25 over sections. Each hit: {doc_id, title, collection, page, section, text, score}."""
    _load()
    q = _tokens(query)
    if not q or not _chunks:
        return []
    n = len(_chunks)
    k1, b = 1.5, 0.75
    want = (collection or "").strip().lower()
    scored: list[tuple[float, dict]] = []
    for c in _chunks:
        if want and c["doc"]["collection"].lower() != want:
            continue
        score = 0.0
        for term in q:
            tf = c["tf"].get(term)
            if not tf:
                continue
            idf = math.log(1 + (n - _df[term] + 0.5) / (_df[term] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * c["len"] / _avg_len))
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{"doc_id": c["doc"]["id"], "title": c["doc"]["title"], "collection": c["doc"]["collection"],
             "page": c["page"], "section": c["section"], "text": c["text"], "score": round(s, 3)}
            for s, c in scored[:max(1, min(top_k, 8))]]


def catalogue() -> str:
    """The collections as the agent reads them."""
    lines = []
    for col in collections():
        lines.append(f"COLLECTION {col['name']}")
        for d in col["documents"]:
            lines.append(f"  - {d['title']} ({d['id']}, {d['pages']} pages)")
    return "\n".join(lines)
