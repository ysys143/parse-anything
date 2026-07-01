"""Document ontology: an external, runtime-injected vocabulary + signal->tag rules (R15).

The set of node ROLES (title/heading/paragraph/figure/table/equation/caption/reference/...) and ZONES
(cover/toc/body/references/appendix/metadata/furniture), plus the RULES that map raw extraction signals
to them, live OUTSIDE the code in a per-family markdown file with YAML frontmatter
(``ontology/<family>.md``). A new document family (contract, form, financial report) is added by writing a
new ontology file -- never by editing the pipeline. This mirrors how ``profile.py`` externalises the
diagnosis result, and keeps the pipeline doc-type-agnostic.

The frontmatter carries the machine-readable ontology (node_types / zones / figure_kinds / rules /
chunking); the markdown body is human documentation. Rules are ORDERED; the first rule whose ``when``
predicate matches fills each still-unset axis (type / zone / level / opens_zone) of the verdict -- a
"first-match-wins per axis" resolution. Predicates compose a fixed, tested registry of primitives over
the node's signals (page_index, odl_type, odl_role, odl_heading_level, font_rank, numbering, text) with
NO ``eval`` -- the ontology is data, not code.

To stay dependency-free (the pipeline's deps are deliberately minimal + license-clean), a small YAML
SUBSET is parsed here rather than pulling in PyYAML: block mappings, one-level nested block mappings,
block sequences of flow items, and flow collections/scalars. Anything outside the subset raises a clear
error at load time (fail-loud, never a silent mis-parse).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .numbering import classify_numbering


# --------------------------------------------------------------------------------------------------
# Ontology data model
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class NodeTypeDef:
    name: str
    meaning: str | None = None          # optional linked-data CURIE (e.g. "doco:Title") -- agent-optional
    atomic: bool = False                # table/figure/equation -> never split by the chunker (Phase 3)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    when: dict                          # predicate tree over the primitive registry
    then: dict                          # {type?, zone?, level?, opens_zone?}


@dataclass(frozen=True, slots=True)
class ChunkPolicy:
    child_tokens: int = 384
    tokenizer: str = "cl100k_base"
    parent: str = "section"
    keep_atomic: tuple[str, ...] = ("table", "figure", "equation")


@dataclass(frozen=True, slots=True)
class Verdict:
    role: str | None = None
    zone: str | None = None
    level: Any = None                   # int | "from_numbering" | "from_font_rank" | None
    opens_zone: bool = False


@dataclass(frozen=True, slots=True)
class Ontology:
    id: str
    version: str
    sha256: str
    family: str
    conforms_to: str | None
    node_types: dict[str, NodeTypeDef]
    zones: tuple[str, ...]
    figure_kinds: tuple[str, ...]
    rules: tuple[Rule, ...]
    chunking: ChunkPolicy
    default_zone: str = "body"

    def profile_stamp(self) -> dict[str, Any]:
        """The block stamped into an emitted document declaring which ontology + version produced it."""
        out = {"id": self.id, "family": self.family, "version": self.version, "sha256": self.sha256}
        if self.conforms_to:
            out["conformsTo"] = self.conforms_to
        return out

    def classify(self, signals: dict[str, Any]) -> Verdict:
        """First-match-per-axis verdict for one node's signals. Rules are tried in order; each matching
        rule fills any still-unset axis of the verdict from its ``then``. Stops once type+zone are set."""
        role: str | None = None
        zone: str | None = None
        level: Any = None
        opens = False
        for rule in self.rules:
            if role is not None and zone is not None:
                break
            if not _match(rule.when, signals):
                continue
            then = rule.then
            if role is None and "type" in then:
                role = then["type"]
                if "level" in then:
                    level = then["level"]
                if then.get("opens_zone"):
                    opens = True
            if zone is None and "zone" in then:
                zone = then["zone"]
                if then.get("opens_zone"):
                    opens = True
        return Verdict(role=role, zone=zone, level=level, opens_zone=opens)


# --------------------------------------------------------------------------------------------------
# Predicate registry (the ONLY code path a rule can exercise -- no eval, closed set)
# --------------------------------------------------------------------------------------------------
def _as_num(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _cmp(value: Any, spec: Any) -> bool:
    """A leaf comparison spec: a scalar (equality) or a dict of operators {eq,in,gte,lte,gt,lt,not_null,matches}."""
    if not isinstance(spec, dict):
        return value == spec
    for op, want in spec.items():
        if op == "eq":
            if value != want:
                return False
        elif op == "in":
            if value not in want:
                return False
        elif op == "not_in":
            if value in want:
                return False
        elif op == "gte":
            n = _as_num(value)
            if n is None or n < want:
                return False
        elif op == "lte":
            n = _as_num(value)
            if n is None or n > want:
                return False
        elif op == "gt":
            n = _as_num(value)
            if n is None or n <= want:
                return False
        elif op == "lt":
            n = _as_num(value)
            if n is None or n >= want:
                return False
        elif op == "not_null":
            if (value is not None) != bool(want):
                return False
        else:
            raise ValueError(f"ontology: unknown comparison operator {op!r}")
    return True


def _match(clause: Any, signals: dict[str, Any]) -> bool:
    """Evaluate a ``when`` clause: combinators (all/any/not) or a mapping of predicate-name -> spec."""
    if not isinstance(clause, dict):
        raise ValueError(f"ontology: a rule 'when' must be a mapping, got {clause!r}")
    for key, spec in clause.items():
        if key == "all":
            if not all(_match(sub, signals) for sub in spec):
                return False
        elif key == "any":
            if not any(_match(sub, signals) for sub in spec):
                return False
        elif key == "not":
            if _match(spec, signals):
                return False
        elif key == "classify_numbering":
            # special primitive: is the node's text a recognised numbering-prefixed heading?
            has = classify_numbering(signals.get("text") or "") is not None
            want = True if spec == "not_null" else bool(_cmp(has, spec) if isinstance(spec, dict) else spec)
            if has != want:
                return False
        elif key == "text_matches":
            pat, flags = (spec, 0)
            if isinstance(spec, dict):
                pat = spec.get("pattern") or spec.get("re") or spec.get("value")
                flags = re.IGNORECASE if str(spec.get("flags", "")).lower().find("i") >= 0 else 0
            if not re.search(str(pat), signals.get("text") or "", flags):
                return False
        else:
            if key not in _SIGNAL_KEYS:
                raise ValueError(f"ontology: unknown predicate {key!r} (allowed: {sorted(_SIGNAL_KEYS)})")
            if not _cmp(signals.get(key), spec):
                return False
    return True


# signals a rule may test directly (combinators + classify_numbering + text_matches handled above)
_SIGNAL_KEYS = frozenset({
    "page_index", "odl_type", "odl_role", "odl_heading_level", "font_size", "font_rank",
    "is_landscape", "bbox_area_frac", "centered", "text",
})


# --------------------------------------------------------------------------------------------------
# Loader + minimal YAML-subset parser
# --------------------------------------------------------------------------------------------------
def _strip_comment(s: str) -> str:
    """Drop a trailing ``# comment`` that is outside any quotes/brackets."""
    out, quote, depth = [], "", 0
    for ch in s:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "#" and (not out or out[-1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(tok: str) -> Any:
    """Parse a flow/scalar token: quoted string, int, float, bool, null, else a bare string."""
    tok = tok.strip()
    if not tok:
        return None
    if (tok[0] == tok[-1]) and tok[0] in "\"'" and len(tok) >= 2:
        return tok[1:-1]
    low = tok.lower()
    if low in ("null", "~", "none"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


def _split_flow(body: str) -> list[str]:
    """Split a flow body on top-level commas, respecting nested [] {} and quotes."""
    parts, cur, quote, depth = [], [], "", 0
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in "[{":
            depth += 1
            cur.append(ch)
        elif ch in "]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def _split_kv(item: str) -> tuple[str, str]:
    """Split ``key: value`` at the first top-level colon (outside quotes/brackets)."""
    quote, depth = "", 0
    for i, ch in enumerate(item):
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            return item[:i].strip(), item[i + 1:].strip()
    raise ValueError(f"ontology: expected 'key: value' in flow mapping, got {item!r}")


def _parse_flow(s: str) -> Any:
    """Recursively parse a flow value: {map}, [seq], or a scalar."""
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        out: dict[str, Any] = {}
        for item in _split_flow(s[1:-1]):
            if not item.strip():
                continue
            k, v = _split_kv(item)
            out[_scalar(k) if not (k and k[0] in "\"'") else k[1:-1]] = _parse_flow(v)
        return out
    if s.startswith("[") and s.endswith("]"):
        return [_parse_flow(x) for x in _split_flow(s[1:-1]) if x.strip()]
    return _scalar(s)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse the YAML-subset frontmatter block (between the first two ``---`` fences)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("ontology: file must start with a '---' frontmatter fence")
    fm: list[str] = []
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        fm.append(ln)
    else:
        raise ValueError("ontology: unterminated frontmatter (missing closing '---')")

    # Tokenise into (indent, content) skipping blanks/comments.
    rows: list[tuple[int, str]] = []
    for raw in fm:
        content = _strip_comment(raw)
        if not content.strip():
            continue
        rows.append((len(raw) - len(raw.lstrip(" ")), content.strip()))
    value, _ = _parse_block(rows, 0, rows[0][0] if rows else 0)
    if not isinstance(value, dict):
        raise ValueError("ontology: frontmatter root must be a mapping")
    return value


def _parse_block(rows: list[tuple[int, str]], idx: int, indent: int) -> tuple[Any, int]:
    """Indent-based block parser for the YAML subset. Returns (value, next_index)."""
    if idx >= len(rows):
        return None, idx
    is_seq = rows[idx][1].startswith("- ") or rows[idx][1] == "-"
    if is_seq:
        seq: list[Any] = []
        while idx < len(rows) and rows[idx][0] == indent and (rows[idx][1] == "-" or rows[idx][1].startswith("- ")):
            item = rows[idx][1][1:].strip()
            if item:
                seq.append(_parse_flow(item))   # inline flow item (rules are authored as one-line flow maps)
                idx += 1
            else:                               # nested block under a bare '-'
                val, idx = _parse_block(rows, idx + 1, rows[idx + 1][0]) if idx + 1 < len(rows) else (None, idx + 1)
                seq.append(val)
        return seq, idx
    mapping: dict[str, Any] = {}
    while idx < len(rows) and rows[idx][0] == indent:
        key, rest = _split_kv(rows[idx][1])
        idx += 1
        if rest:                                # inline value (scalar or flow)
            mapping[key] = _parse_flow(rest)
        elif idx < len(rows) and rows[idx][0] > indent:   # nested block mapping/sequence
            mapping[key], idx = _parse_block(rows, idx, rows[idx][0])
        else:
            mapping[key] = None
    return mapping, idx


def _build_ontology(fm: dict[str, Any], *, family: str, sha256: str) -> Ontology:
    node_types: dict[str, NodeTypeDef] = {}
    for name, spec in (fm.get("node_types") or {}).items():
        spec = spec or {}
        node_types[name] = NodeTypeDef(name=name, meaning=spec.get("meaning"), atomic=bool(spec.get("atomic", False)))
    rules: list[Rule] = []
    for r in (fm.get("rules") or []):
        if not isinstance(r, dict) or "id" not in r or "when" not in r or "then" not in r:
            raise ValueError(f"ontology: each rule needs id/when/then, got {r!r}")
        rules.append(Rule(id=str(r["id"]), when=r["when"], then=r["then"]))
    ck = fm.get("chunking") or {}
    chunking = ChunkPolicy(
        child_tokens=int(ck.get("child_tokens", 384)),
        tokenizer=str(ck.get("tokenizer", "cl100k_base")),
        parent=str(ck.get("parent", "section")),
        keep_atomic=tuple(ck.get("keep_atomic", ("table", "figure", "equation"))),
    )
    if "id" not in fm or "version" not in fm:
        raise ValueError("ontology: frontmatter must declare 'id' and 'version'")
    return Ontology(
        id=str(fm["id"]), version=str(fm["version"]), sha256=sha256, family=family,
        conforms_to=fm.get("conformsTo"),
        node_types=node_types,
        zones=tuple(fm.get("zones") or ()),
        figure_kinds=tuple(fm.get("figure_kinds") or ()),
        rules=tuple(rules),
        chunking=chunking,
        default_zone=str(fm.get("default_zone", "body")),
    )


# --------------------------------------------------------------------------------------------------
# Applying an ontology to graph nodes (role + zone tagging)
# --------------------------------------------------------------------------------------------------
_ODL_TYPE_TO_ROLE = {"paragraph": "paragraph", "text block": "paragraph", "list item": "list_item",
                     "heading": "heading"}


def _node_page(n: dict) -> int:
    return n.get("page") or (n.get("pages") or [0])[0] or 0


def compute_font_ranks(blocks: list[dict]) -> dict[object, float | None]:
    """block id -> font-size percentile within the document (fraction of blocks with a SMALLER font),
    or None when the block has no font size. A heading tends to sit near 1.0."""
    import bisect

    sizes = sorted(b["font_size"] for b in blocks if b.get("font_size"))
    n = len(sizes)
    ranks: dict[object, float | None] = {}
    for b in blocks:
        fs = b.get("font_size")
        ranks[b["id"]] = None if (fs is None or n == 0) else bisect.bisect_left(sizes, fs) / n
    return ranks


def node_signals(block: dict, font_ranks: dict[object, float | None] | None = None, *,
                 is_landscape: bool = False) -> dict[str, Any]:
    """The signal bundle a rule's ``when`` predicate sees for one block node."""
    return {
        "page_index": (block.get("page") or 1) - 1,
        "odl_type": block.get("type"),
        "odl_role": block.get("odl_role"),
        "odl_heading_level": block.get("heading_level"),
        "font_size": block.get("font_size"),
        "font_rank": font_ranks.get(block["id"]) if font_ranks else None,
        "is_landscape": is_landscape,
        "text": block.get("text", ""),
    }


def tag_nodes(blocks: list[dict], tables: list[dict], figures: list[dict], ontology: Ontology,
              font_ranks: dict[object, float | None] | None = None, *, is_landscape: bool = False) -> None:
    """Stamp ``role`` (ontology node type) + ``zone`` onto every graph node, in reading order so a
    zone-opening heading (references/appendix/toc) carries its zone to the nodes that follow. Tables and
    figures inherit the current zone and keep their own role. Mutates the node dicts in place."""
    if font_ranks is None:
        font_ranks = compute_font_ranks(blocks)
    ordered = sorted([*blocks, *tables, *figures], key=lambda n: (_node_page(n), n.get("order", 0)))
    current_zone = ontology.default_zone
    for n in ordered:
        t = n.get("type")
        if t in ("table", "figure"):
            n["role"] = t
            n["zone"] = current_zone
            continue
        v = ontology.classify(node_signals(n, font_ranks, is_landscape=is_landscape))
        if v.zone is not None:
            n["zone"] = v.zone
            if v.opens_zone:
                current_zone = v.zone
        else:
            n["zone"] = current_zone
        n["role"] = v.role or _ODL_TYPE_TO_ROLE.get(t or "", "paragraph")


def ontology_path(root: str | Path, family: str) -> Path:
    return Path(root) / f"{family}.md"


def load_ontology(family: str, root: str | Path) -> Ontology:
    """Load ``<root>/<family>.md`` into a frozen Ontology. Raises FileNotFoundError / ValueError loudly
    (an explicit lever must never silently degrade -- a missing/broken ontology is a misconfiguration)."""
    path = ontology_path(root, family)
    raw = path.read_bytes()
    fm = _parse_frontmatter(raw.decode("utf-8"))
    return _build_ontology(fm, family=family, sha256=hashlib.sha256(raw).hexdigest())
