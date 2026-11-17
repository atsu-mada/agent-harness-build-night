"""Mirror the continuity record (world.export()) to the local Neo4j with `CC_` labels.

`sync(export)` replaces the whole `CC_` copy in one transaction: it deletes every node
with a label starting with `CC_` except `CC_PX_` (the PixLight demo graph in the same
database stays), then writes `CC_Entity`, `CC_State`, `CC_Shot` and the relationships
HAS / TOWARD / REPLACED_BY / STARTED_AT / RELATES_TO / NEXT with UNWIND parameters.

Connection: NEO4J_URI (default from config/neo4j.json, bolt://localhost:7687),
NEO4J_USER, NEO4J_PASSWORD from the environment; `scripts/run.sh` fills the password
through api_secrets. The password is never printed.

Export shape accepted (plain dicts):
    {
      "entities": [{"name": "カイ", "kind": "Character"}, ...],
      "shots":    [{"no": 1, "text": "..."}, ...],
      "states":   [{"id": "s1", "entity": "カイ", "attr": "上着", "value": "青",
                    "from": 1, "to": 4, "cause": "...", "approved_by": "設定",
                    "toward": None}, ...],
      "rels": {"REPLACED_BY": [{"src": "s1", "dst": "s2", "cause": "...", "shot": 5}],
               "STARTED_AT":  [{"src": "s2", "dst": 5}],
               "TOWARD":      [{"src": "s3", "dst": "カイ"}],
               "RELATES_TO":  [{"src": "カイ", "dst": "ミナ", "kind": "部の先輩", "fixed": True}],
               "NEXT":        [{"src": 1, "dst": 2}]}
    }
Endpoints: entities by name, states by id, shots by number. `rels` may also be a list
of {"type": ..., "src": ..., "dst": ..., **props}; "source"/"target" and "start"/"end"
are accepted for src/dst. HAS comes from state["entity"]. When `rels` has no TOWARD
rows they come from state["toward"]; when it has no NEXT rows they link shots in order.
A state without "id" gets "<entity>|<attr>|<toward>|<from>".
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "neo4j.json"
try:
    CONFIG = json.loads(_CONFIG_PATH.read_text())
except (OSError, ValueError):
    CONFIG = {"uri": "bolt://localhost:7687", "user": "neo4j", "database": "neo4j"}

# Deletes only this app's copy; CC_PX_ (PixLight demo) and every other label stay.
DELETE_CC = (
    "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'CC_') "
    "AND NOT any(l IN labels(n) WHERE l STARTS WITH 'CC_PX_') DETACH DELETE n"
)
COUNT_CC = (
    "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'CC_') "
    "AND NOT any(l IN labels(n) WHERE l STARTS WITH 'CC_PX_') RETURN count(n) AS n"
)

# relationship type -> (start label, start key, end label, end key)
ENDPOINTS = {
    "HAS": ("CC_Entity", "name", "CC_State", "sid"),
    "TOWARD": ("CC_State", "sid", "CC_Entity", "name"),
    "REPLACED_BY": ("CC_State", "sid", "CC_State", "sid"),
    "STARTED_AT": ("CC_State", "sid", "CC_Shot", "no"),
    "RELATES_TO": ("CC_Entity", "name", "CC_Entity", "name"),
    "NEXT": ("CC_Shot", "no", "CC_Shot", "no"),
}

_SRC_KEYS = ("src", "source", "start")
_DST_KEYS = ("dst", "target", "end")


def _pick(row: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in row:
            return row[k]
    raise KeyError(f"relationship row has none of {keys}: {row}")


def _state_id(s: dict):
    return s.get("id") or f"{s['entity']}|{s['attr']}|{s.get('toward')}|{s['from']}"


def _rel_rows(rels) -> dict[str, list[dict]]:
    """Normalise rels to {TYPE: [{src, dst, props}]}."""
    out: dict[str, list[dict]] = {t: [] for t in ENDPOINTS}
    if isinstance(rels, dict):
        items = [(t, row) for t, rows in rels.items() for row in rows]
    else:
        items = [(row["type"], row) for row in rels or []]
    for rtype, row in items:
        rtype = rtype.upper()
        if rtype not in ENDPOINTS:
            raise ValueError(f"unknown relationship type {rtype}")
        skip = set(_SRC_KEYS + _DST_KEYS + ("type", "props"))
        props = {k: v for k, v in row.items() if k not in skip}
        props.update(row.get("props") or {})
        out[rtype].append({"src": _pick(row, _SRC_KEYS), "dst": _pick(row, _DST_KEYS), "props": props})
    return out


def build_statements(export: dict) -> list[tuple[str, dict]]:
    """The Cypher statements (with parameters) that sync() runs, in order. No I/O."""
    entities = [{"name": e["name"], "kind": e.get("kind")} for e in export.get("entities", [])]
    shots = sorted(
        ({"no": s["no"], "text": s.get("text")} for s in export.get("shots", [])),
        key=lambda s: s["no"],
    )
    states = [
        {
            "sid": _state_id(s),
            "entity": s["entity"],
            "attr": s["attr"],
            "value": s.get("value"),
            "from": s.get("from"),
            "to": s.get("to"),
            "cause": s.get("cause"),
            "approved_by": s.get("approved_by"),
            "toward": s.get("toward"),
        }
        for s in export.get("states", [])
    ]
    rels = _rel_rows(export.get("rels", {}))
    rels["HAS"] = [{"src": s["entity"], "dst": s["sid"], "props": {}} for s in states]
    if not rels["TOWARD"]:
        rels["TOWARD"] = [
            {"src": s["sid"], "dst": s["toward"], "props": {}} for s in states if s["toward"]
        ]
    if not rels["NEXT"]:
        rels["NEXT"] = [
            {"src": a["no"], "dst": b["no"], "props": {}} for a, b in zip(shots, shots[1:])
        ]

    stmts: list[tuple[str, dict]] = [(DELETE_CC, {})]
    stmts.append(("UNWIND $rows AS r CREATE (:CC_Entity {name: r.name, kind: r.kind})", {"rows": entities}))
    stmts.append(("UNWIND $rows AS r CREATE (:CC_Shot {no: r.no, text: r.text})", {"rows": shots}))
    stmts.append((
        "UNWIND $rows AS r CREATE (:CC_State {sid: r.sid, entity: r.entity, attr: r.attr, "
        "value: r.value, `from`: r.`from`, `to`: r.`to`, cause: r.cause, "
        "approved_by: r.approved_by, toward: r.toward})",
        {"rows": states},
    ))
    for rtype, (la, ka, lb, kb) in ENDPOINTS.items():
        rows = rels[rtype]
        if not rows:
            continue
        stmts.append((
            f"UNWIND $rows AS r MATCH (a:{la} {{{ka}: r.src}}) MATCH (b:{lb} {{{kb}: r.dst}}) "
            f"CREATE (a)-[t:{rtype}]->(b) SET t += r.props",
            {"rows": rows},
        ))
    return stmts


def _driver(uri=None, user=None, password=None):
    from neo4j import GraphDatabase

    password = password or os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD is not set: start this through scripts/run.sh")
    uri = uri or os.environ.get("NEO4J_URI", CONFIG["uri"])
    user = user or os.environ.get("NEO4J_USER", CONFIG["user"])
    return GraphDatabase.driver(uri, auth=(user, password))


def sync(export: dict, uri=None, user=None, password=None) -> int:
    """Replace the CC_ copy (not CC_PX_) with `export` in one transaction; return its node count."""
    stmts = build_statements(export)
    database = os.environ.get("NEO4J_DATABASE", CONFIG.get("database", "neo4j"))

    def work(tx):
        for cypher, params in stmts:
            tx.run(cypher, **params).consume()
        return tx.run(COUNT_CC).single()["n"]

    with _driver(uri, user, password) as d, d.session(database=database) as s:
        return s.execute_write(work)


def clear(uri=None, user=None, password=None) -> None:
    """Delete the CC_ copy (CC_PX_ stays)."""
    database = os.environ.get("NEO4J_DATABASE", CONFIG.get("database", "neo4j"))
    with _driver(uri, user, password) as d:
        d.execute_query(DELETE_CC, database_=database)


SAMPLE = {
    "entities": [{"name": "カイ", "kind": "Character"}, {"name": "ミナ", "kind": "Character"}],
    "shots": [{"no": 4, "text": "カイがミナに鍵を渡す。"}, {"no": 5, "text": "カイが青い上着を脱ぐ。"}],
    "states": [
        {"id": "kai-jacket-1", "entity": "カイ", "attr": "上着", "value": "青", "from": 1, "to": 4,
         "cause": "S1 設定", "approved_by": "設定"},
        {"id": "kai-jacket-2", "entity": "カイ", "attr": "上着", "value": "なし", "from": 5, "to": 99,
         "cause": "カイが青い上着を脱ぐ", "approved_by": "human"},
        {"id": "mina-trust-2", "entity": "ミナ", "attr": "信頼", "value": "信頼", "from": 4, "to": 99,
         "cause": "カイがミナに鍵を渡す", "approved_by": "設定", "toward": "カイ"},
    ],
    "rels": {
        "REPLACED_BY": [{"src": "kai-jacket-1", "dst": "kai-jacket-2", "cause": "カイが青い上着を脱ぐ", "shot": 5}],
        "STARTED_AT": [{"src": "kai-jacket-2", "dst": 5}, {"src": "mina-trust-2", "dst": 4}],
        "RELATES_TO": [{"src": "カイ", "dst": "ミナ", "kind": "部の先輩", "fixed": True}],
    },
}

if __name__ == "__main__":
    import sys

    if "--offline" in sys.argv:
        for cypher, params in build_statements(SAMPLE):
            print(cypher, "|", len(params.get("rows", [])), "rows")
    else:
        n = sync(SAMPLE)
        print(f"mirror sync wrote {n} CC_ nodes")
        if "--keep" not in sys.argv:
            clear()
            print("CC_ test nodes deleted (CC_PX_ untouched)")
