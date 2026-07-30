"""Parse FOLIO.owl into `folio_concepts` (+ `folio_aliases`), preserving hierarchy.

Design notes worth knowing before editing:

* **`code` is the IRI suffix**, e.g. `RCSG4k3ah1Pu5YgPexPgOmL` for Health Care Industry.
  FOLIO's IRIs are opaque and stable; labels are not (they get retitled between releases),
  so the label is emphatically not the key.
* **Ancestry is denormalized into `level_1_code`/`level_2_code`/`level_3_code`** at load
  time. Cube reads those columns directly. A recursive CTE per facet query would be correct
  and slow, and Cube has no clean way to express one as a dimension (#13).
* **FOLIO is a DAG, not a tree.** 830 of 18k classes declare more than one `rdfs:subClassOf`.
  A `parent_code` column can hold one, so we pick the lexicographically smallest parent code.
  Cost accepted: for a multi-parent concept the roll-up path shown in the UI is one of
  several true paths, not the only one. The alternative — a closure table — buys correctness
  for concepts the product does not currently facet on, at the price of a join in every
  Cube dimension. Revisit if a mapped dimension (#9) lands on a multi-parent branch.
* **DEPRECATED and SANDBOX subtrees are dropped.** They are dead vocabulary; keeping them
  would let `resolve()` return a code nothing is tagged with, which reads as "no comparable
  deals" downstream (the failure mode #25 exists to prevent).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from psycopg import Connection
from rdflib import OWL, RDF, RDFS, SKOS, Graph, URIRef

FOLIO_NS = "https://folio.openlegalstandard.org/"

# Root labels whose entire subtree is excluded from the load.
EXCLUDED_ROOT_PREFIXES = ("DEPRECATED", "ZZZ - SANDBOX")


@dataclass(frozen=True)
class Concept:
    code: str
    label: str
    parent_code: str | None
    level: int
    definition: str | None = None
    level_1_code: str | None = None
    level_2_code: str | None = None
    level_3_code: str | None = None
    aliases: tuple[str, ...] = field(default=())


def _code(iri: URIRef) -> str | None:
    """IRI suffix, or None for anything outside the FOLIO namespace (owl:Thing, blank nodes)."""
    text = str(iri)
    if not text.startswith(FOLIO_NS):
        return None
    suffix = text[len(FOLIO_NS) :]
    # a handful of classes carry a malformed fragment IRI (`#GovB-...`); they have no label
    # and no children, and are dropped by the label filter below anyway.
    return suffix or None


def parse_folio(path: Path) -> list[Concept]:
    """Parse the OWL file into concepts with resolved, denormalized ancestry."""
    graph = Graph()
    graph.parse(str(path), format="xml")

    labels: dict[str, str] = {}
    parents: dict[str, list[str]] = {}
    definitions: dict[str, str] = {}
    aliases: dict[str, list[str]] = {}

    for subject in graph.subjects(RDF.type, OWL.Class):
        if not isinstance(subject, URIRef):
            continue
        code = _code(subject)
        if code is None:
            continue
        label_node = graph.value(subject, RDFS.label)
        if label_node is None:
            continue  # unlabelled classes cannot be displayed or resolved; skip
        label_text = str(label_node)
        labels[code] = label_text

        parent_codes = sorted(
            c
            for c in (
                _code(o) for o in graph.objects(subject, RDFS.subClassOf) if isinstance(o, URIRef)
            )
            if c is not None
        )
        parents[code] = parent_codes

        definition = graph.value(subject, SKOS.definition)
        if definition is not None:
            definitions[code] = str(definition)

        seen: set[str] = set()
        for alt in graph.objects(subject, SKOS.altLabel):
            text = str(alt).strip()
            if not text or text == label_text or text in seen:
                continue
            seen.add(text)
            aliases[code] = aliases.get(code, []) + [text]

    excluded = _excluded_codes(labels, parents)

    concepts: list[Concept] = []
    for code, label in labels.items():
        if code in excluded:
            continue
        chain = _ancestor_chain(code, parents, labels, excluded)
        parent = chain[-2] if len(chain) > 1 else None
        concepts.append(
            Concept(
                code=code,
                label=label,
                parent_code=parent,
                level=len(chain),
                definition=definitions.get(code),
                level_1_code=chain[0],
                level_2_code=chain[1] if len(chain) > 1 else None,
                level_3_code=chain[2] if len(chain) > 2 else None,
                aliases=tuple(aliases.get(code, ())),
            )
        )
    return concepts


def _excluded_codes(labels: dict[str, str], parents: dict[str, list[str]]) -> set[str]:
    """Codes in a DEPRECATED/SANDBOX subtree, roots included."""
    roots = {c for c, label in labels.items() if label.startswith(EXCLUDED_ROOT_PREFIXES)}
    children: dict[str, list[str]] = {}
    for code, parent_codes in parents.items():
        for parent in parent_codes:
            children.setdefault(parent, []).append(code)
    excluded: set[str] = set()
    stack = list(roots)
    while stack:
        code = stack.pop()
        if code in excluded:
            continue
        excluded.add(code)
        stack.extend(children.get(code, ()))
    return excluded


def _ancestor_chain(
    code: str,
    parents: dict[str, list[str]],
    labels: dict[str, str],
    excluded: set[str],
) -> list[str]:
    """Root-first chain ending at `code`. Cycle-safe: FOLIO is authored by hand."""
    chain = [code]
    seen = {code}
    current = code
    while True:
        candidates = [
            p
            for p in parents.get(current, ())
            if p in labels and p not in excluded and p not in seen
        ]
        if not candidates:
            break
        current = candidates[0]  # smallest code: deterministic across runs
        seen.add(current)
        chain.append(current)
    chain.reverse()
    return chain


UPSERT_CONCEPT = """
INSERT INTO folio_concepts
    (code, label, parent_code, level, definition, level_1_code, level_2_code, level_3_code)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (code) DO UPDATE SET
    label = EXCLUDED.label,
    parent_code = EXCLUDED.parent_code,
    level = EXCLUDED.level,
    definition = EXCLUDED.definition,
    level_1_code = EXCLUDED.level_1_code,
    level_2_code = EXCLUDED.level_2_code,
    level_3_code = EXCLUDED.level_3_code
"""


def upsert_concepts(conn: Connection, concepts: list[Concept]) -> int:
    """Idempotent load. Returns the number of concept rows written.

    Parents are inserted before children — `parent_code` is a self-referencing foreign key,
    so a child-first order fails. Sorting by level does that in one pass.
    """
    ordered = sorted(concepts, key=lambda c: c.level)
    with conn.cursor() as cur:
        cur.executemany(
            UPSERT_CONCEPT,
            [
                (
                    c.code,
                    c.label,
                    c.parent_code,
                    c.level,
                    c.definition,
                    c.level_1_code,
                    c.level_2_code,
                    c.level_3_code,
                )
                for c in ordered
            ],
        )
        cur.executemany(
            "INSERT INTO folio_aliases (alias, code) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            [(alias, c.code) for c in ordered for alias in c.aliases],
        )
    conn.commit()
    return len(ordered)
