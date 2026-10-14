"""The allow-lists, and everything that enforces them.

Pure functions and small value objects, no I/O: this is the part of the server
a reviewer has to trust, so it can be read (and tested) on its own.

Two scopes:

* :class:`TableScope` — the CAS tables an agent may see (``ALLOWED_TABLES``).
  Entries are ``caslib.table``; ``*`` matches any run of characters, so
  ``CASUSER.*_TEAM3`` allows every table of one team. Matching is
  case-insensitive because CAS names are.
* :class:`ModelScope` — the MAS modules an agent may score (``ALLOWED_MODELS``).

For FedSQL, :func:`referenced_tables` lists every table a SELECT reads, and
:func:`qualify_query` resolves each one against the scope, rewriting a bare
``REGISTRY_TEAM3`` into ``CASUSER.REGISTRY_TEAM3`` when that is unambiguous and
refusing anything outside the scope. The screening of *what kind* of statement
it is (single SELECT, no write verbs) stays with the upstream FedSQL helper;
this module only answers "which tables, and are they allowed".
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

# --- parsing -----------------------------------------------------------------


def parse_list(raw: str | None) -> list[str]:
    """Split a comma- or newline-separated env value into stripped entries."""
    if not raw:
        return []
    out: list[str] = []
    for part in re.split(r"[,\n]", raw):
        item = part.strip().strip('"').strip("'")
        if item and item not in out:
            out.append(item)
    return out


def _norm(name: str) -> str:
    """Normalise an identifier the way CAS compares it: unquoted, upper-case."""
    return name.strip().strip('"').upper()


# --- tables ------------------------------------------------------------------


@dataclass(frozen=True)
class TableRef:
    caslib: str
    table: str

    @property
    def qualified(self) -> str:
        return f"{self.caslib}.{self.table}"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.qualified


@dataclass(frozen=True)
class TablePattern:
    caslib: str  # upper-case, may contain *
    table: str  # upper-case, may contain *

    @property
    def is_wildcard(self) -> bool:
        return "*" in self.caslib or "*" in self.table

    @property
    def display(self) -> str:
        return f"{self.caslib}.{self.table}"

    def matches_caslib(self, caslib: str) -> bool:
        return fnmatch.fnmatchcase(_norm(caslib), self.caslib)

    def matches(self, caslib: str, table: str) -> bool:
        return self.matches_caslib(caslib) and fnmatch.fnmatchcase(_norm(table), self.table)


class ScopeError(ValueError):
    """A reference outside the configured scope, with a message for the model."""


@dataclass
class TableScope:
    patterns: list[TablePattern] = field(default_factory=list)

    @classmethod
    def from_env(cls, raw: str | None) -> TableScope:
        patterns: list[TablePattern] = []
        for entry in parse_list(raw):
            if "." not in entry:
                raise ScopeError(
                    f"ALLOWED_TABLES entry {entry!r} must be caslib.table (for example CASUSER.REGISTRY_TEAM3)."
                )
            caslib, table = entry.split(".", 1)
            if not caslib.strip() or not table.strip():
                raise ScopeError(f"ALLOWED_TABLES entry {entry!r} is missing the caslib or the table.")
            patterns.append(TablePattern(_norm(caslib), _norm(table)))
        return cls(patterns)

    def __bool__(self) -> bool:
        return bool(self.patterns)

    @property
    def display(self) -> list[str]:
        return [p.display for p in self.patterns]

    @property
    def exact(self) -> list[TableRef]:
        """The entries without wildcards, as concrete table references."""
        return [TableRef(p.caslib, p.table) for p in self.patterns if not p.is_wildcard]

    @property
    def caslibs(self) -> list[str]:
        """Distinct non-wildcard caslibs, in configuration order."""
        seen: list[str] = []
        for p in self.patterns:
            if "*" not in p.caslib and p.caslib not in seen:
                seen.append(p.caslib)
        return seen

    def allows(self, caslib: str, table: str) -> bool:
        return any(p.matches(caslib, table) for p in self.patterns)

    def resolve(self, ref: str) -> TableRef:
        """Turn ``caslib.table`` or a bare ``table`` into an allowed :class:`TableRef`.

        A bare name resolves when exactly one allowed caslib could hold it;
        with several caslibs in scope it must be qualified. Anything the scope
        does not allow raises :class:`ScopeError` naming what is allowed.
        """
        text = ref.strip().strip('"')
        if not text:
            raise ScopeError("A table name is required.")
        if "." in text:
            caslib_raw, table_raw = text.split(".", 1)
            caslib, table = _norm(caslib_raw), _norm(table_raw)
            if not self.allows(caslib, table):
                raise ScopeError(self._refusal(f"{caslib}.{table}"))
            return TableRef(caslib, table)
        table = _norm(text)
        candidates = [c for c in self.caslibs if self.allows(c, table)]
        if len(candidates) == 1:
            return TableRef(candidates[0], table)
        if not candidates:
            raise ScopeError(self._refusal(table))
        raise ScopeError(
            f"{table} is ambiguous: qualify it as one of "
            + ", ".join(f"{c}.{table}" for c in candidates)
            + "."
        )

    def _refusal(self, what: str) -> str:
        return f"{what} is outside this server's scope. Allowed tables: " + ", ".join(self.display) + "."


# --- models ------------------------------------------------------------------


@dataclass
class ModelScope:
    patterns: list[str] = field(default_factory=list)  # lower-case, may contain *

    @classmethod
    def from_env(cls, raw: str | None) -> ModelScope:
        return cls([entry.strip().lower() for entry in parse_list(raw)])

    def __bool__(self) -> bool:
        return bool(self.patterns)

    @property
    def display(self) -> list[str]:
        return list(self.patterns)

    @property
    def exact(self) -> list[str]:
        return [p for p in self.patterns if "*" not in p]

    def allows(self, module_id: str) -> bool:
        mid = module_id.strip().lower()
        return any(fnmatch.fnmatchcase(mid, p) for p in self.patterns)

    def resolve(self, module_id: str) -> str:
        mid = module_id.strip().strip('"')
        if not mid:
            raise ScopeError("A model name is required.")
        if not self.allows(mid):
            raise ScopeError(
                f"Model {mid!r} is outside this server's scope. Allowed models: "
                + ", ".join(self.display)
                + "."
            )
        return mid.lower()


# --- FedSQL table references -------------------------------------------------

# Comments and string literals are blanked (same length, so spans still index
# into the original text) before the table scan, so a table name inside a
# quote or a comment is neither matched nor rewritten.
_BLANK_RE = re.compile(
    r"/\*.*?\*/"  # block comment
    r"|--[^\n]*"  # line comment
    r"|'(?:[^']|'')*'",  # single-quoted string (with '' escapes)
    re.DOTALL,
)

# An identifier: bare word, or double-quoted (which may contain spaces).
_IDENT = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$#@]*)'
# A table reference: identifier optionally qualified once (caslib.table).
_TABLE = rf"({_IDENT}(?:\s*\.\s*{_IDENT})?)"
# What introduces one: FROM, any JOIN, or a comma inside a FROM list.
_INTRO = r"\b(?:from|join)\b"

_WORDS_NOT_TABLES = {
    "SELECT",
    "WHERE",
    "GROUP",
    "ORDER",
    "HAVING",
    "LIMIT",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "ON",
    "USING",
    "AS",
    "INNER",
    "LEFT",
    "RIGHT",
    "FULL",
    "CROSS",
    "NATURAL",
    "OUTER",
    "JOIN",
    "LATERAL",
}


def _blank(sql: str) -> str:
    return _BLANK_RE.sub(lambda m: " " * len(m.group(0)), sql)


def _ref_spans(sql: str) -> list[tuple[int, int, str]]:
    """``(start, end, text)`` of every table reference in *sql*.

    Walks each FROM / JOIN, takes the identifier that follows, then keeps
    consuming ``, next_table`` items of a FROM list (skipping aliases). A ``(``
    after FROM/JOIN is a derived table: its inner SELECT is scanned by the same
    pass, because the regex runs over the whole text.
    """
    text = _blank(sql)
    spans: list[tuple[int, int, str]] = []
    for intro in re.finditer(_INTRO, text, re.IGNORECASE):
        pos = intro.end()
        while True:
            m = re.compile(r"\s*" + _TABLE, re.IGNORECASE).match(text, pos)
            if not m:
                break
            ref = m.group(1)
            head = re.split(r"\s*\.\s*", ref)[0].strip('"').upper()
            if head in _WORDS_NOT_TABLES:
                break
            spans.append((m.start(1), m.end(1), ref))
            pos = m.end()
            # skip an alias: [AS] ident, then look for a comma continuing the list
            alias = re.compile(r"\s+(?:as\s+)?" + _IDENT, re.IGNORECASE).match(text, pos)
            if alias:
                word = alias.group(0).strip().strip('"').upper()
                if word not in _WORDS_NOT_TABLES:
                    pos = alias.end()
            comma = re.compile(r"\s*,").match(text, pos)
            if not comma or intro.group(0).lower() == "join":
                break
            pos = comma.end()
    return spans


def referenced_tables(sql: str) -> list[str]:
    """Every table reference in *sql* (as written, de-duplicated, in order)."""
    out: list[str] = []
    for _, _, ref in _ref_spans(sql):
        clean = re.sub(r"\s*\.\s*", ".", ref)
        if clean not in out:
            out.append(clean)
    return out


def qualify_query(sql: str, scope: TableScope) -> tuple[str, list[TableRef]]:
    """Resolve every table in *sql* against *scope* and return the rewritten SQL.

    Bare names become ``caslib.table`` when the scope makes that unambiguous;
    already-qualified names are kept (normalised to upper-case). The first
    reference outside the scope raises :class:`ScopeError`. A SELECT without any
    table reference (``select 1``) is allowed through unchanged.
    """
    spans = _ref_spans(sql)
    pieces: list[str] = []
    resolved: list[TableRef] = []
    last = 0
    for start, end, ref in spans:
        clean = re.sub(r"\s*\.\s*", ".", ref).replace('"', "")
        table = scope.resolve(clean)
        if table not in resolved:
            resolved.append(table)
        pieces.append(sql[last:start])
        pieces.append(table.qualified)
        last = end
    pieces.append(sql[last:])
    return "".join(pieces), resolved


def check_where(where: str) -> str | None:
    """Reject a WHERE fragment that tries to smuggle a second statement."""
    if not where or not where.strip():
        return None
    blanked = _blank(where)
    if ";" in blanked:
        return "where must be a single condition (no ';')."
    if re.search(
        r"\b(select|from|join|union|into|insert|update|delete|drop|create|alter)\b", blanked, re.IGNORECASE
    ):
        return "where must be a plain condition on the table's columns (no subquery or second statement)."
    return None


__all__ = [
    "ModelScope",
    "ScopeError",
    "TablePattern",
    "TableRef",
    "TableScope",
    "check_where",
    "parse_list",
    "qualify_query",
    "referenced_tables",
]
