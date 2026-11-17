"""Sample world (original) and its continuity record, loaded into Relate.

Every state is a State node valid from shot `from` to shot `to`:

    (:Entity {name, kind})-[:HAS]->(:State {attr, value, from, to, cause, approved_by})
    (:State)-[:STARTED_AT]->(:Shot {no, text})
    (:State)-[:REPLACED_BY {cause, shot}]->(:State)
    (:Shot)-[:NEXT]->(:Shot)

A relationship state (how one character feels about another) is the same
State with `(:State)-[:TOWARD]->(:Entity)`. What never changes between two
characters (seniority, kin) is a fixed `(:Entity)-[:RELATES_TO {kind, fixed}]->(:Entity)`.

A change (taking off a jacket, handing over a key) closes one State and opens
the next with its cause, so a legitimate change is never red.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import relate

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "continuity.rl"
END = 99

# The shot list as written (the "source of truth" the record was built from).
SHOTS = {
    1: "夜・雨。部室。赤い上着でポニーテールのミナが剣を右手に持ち、画面左に立つ。青い上着で眼鏡のカイは画面右。机の左にノートPC、満杯のコーヒー、スマホ。",
    2: "ミナが部室のドアを閉める。",
    3: "ミナが剣を左手に持ち替える。カイがコーヒーを半分飲む。",
    4: "カイが机の脚につまずき、左足をケガする。カイがミナに鍵を渡す。",
    5: "雨上がり。カイが青い上着を脱ぐ。",
    6: "カイがグラスを落とし、グラスが割れる。",
}

ENTITIES = [
    ("Character", "ミナ"),
    ("Character", "カイ"),
    ("Object", "剣"),
    ("Object", "鍵"),
    ("Object", "ノートPC"),
    ("Object", "コーヒー"),
    ("Object", "グラス"),
    ("Place", "部室"),
]

# (entity, attr, value, from, to, cause)
STATES = [
    # A. state carry-over
    ("ミナ", "上着", "赤", 1, END, "S1 設定"),
    ("ミナ", "髪型", "ポニーテール", 1, END, "S1 設定"),
    ("カイ", "上着", "青", 1, 4, "S1 設定"),
    ("カイ", "上着", "なし", 5, END, "S5 上着を脱ぐ"),
    ("カイ", "眼鏡", "あり", 1, END, "S1 設定"),
    ("カイ", "左足", "ケガ", 4, END, "S4 つまずいてケガ"),
    ("コーヒー", "量", "満杯", 1, 2, "S1 設定"),
    ("コーヒー", "量", "半分", 3, END, "S3 半分飲む"),
    ("グラス", "状態", "無事", 1, 5, "S1 設定"),
    ("グラス", "状態", "割れた", 6, END, "S6 割れる"),
    ("部室", "ドア", "閉", 2, END, "S2 ミナが閉める"),
    ("部室", "時間帯", "夜", 1, END, "S1 設定"),
    ("部室", "天気", "雨", 1, 4, "S1 設定"),
    ("部室", "天気", "雨上がり", 5, END, "S5 雨上がり"),
    # B. holding and handing over
    ("剣", "持ち手", "右手", 1, 2, "S1 設定"),
    ("剣", "持ち手", "左手", 3, END, "S3 持ち替え"),
    ("鍵", "持ち主", "カイ", 1, 3, "S1 設定"),
    ("鍵", "持ち主", "ミナ", 4, END, "S4 カイがミナに渡す"),
    # C. spatial placement
    ("ミナ", "立ち位置", "画面左", 1, END, "S1 設定"),
    ("カイ", "立ち位置", "画面右", 1, END, "S1 設定"),
    ("ノートPC", "位置", "机の左", 1, END, "S1 設定"),
    # D. fixed traits
    ("ミナ", "利き手", "右", 1, END, "キャラ設定"),
]

# The demo record: the S5 jacket change has not been entered yet, so Kai's
# blue jacket runs to END and S6 "上着なしのカイ" is red until a human approves it.
DEMO_STATES = [
    ("カイ", "上着", "青", 1, END, "S1 設定") if row[:3] == ("カイ", "上着", "青") else row
    for row in STATES
    if row[:3] != ("カイ", "上着", "なし")
]

# Fixed relations that never change: (from, to, kind)
RELATIONS = [
    ("カイ", "ミナ", "部の先輩"),
]

# Time-layered relationship states: (who, attr, value, from, to, cause, toward)
REL_STATES = [
    ("ミナ", "信頼", "警戒", 1, 3, "S1 設定", "カイ"),
    ("ミナ", "信頼", "信頼", 4, END, "S4 カイがミナに鍵を渡す", "カイ"),
]

# Allowed values the lexicon may claim but the record never holds; used by
# registry() when checker.LEXICON cannot be imported.
EXTRA_VALUES = [
    ("カイ", "左足", "無事", None),
    ("部室", "ドア", "開", None),
    ("部室", "時間帯", "昼", None),
    ("ミナ", "立ち位置", "画面右", None),
    ("カイ", "立ち位置", "画面左", None),
    ("ノートPC", "位置", "机の右", None),
    ("カイ", "眼鏡", "なし", None),
    ("ミナ", "髪型", "下ろし髪", None),
    ("ミナ", "利き手", "左", None),
]

# Shots whose discontinuity is intended (flashback, dream). Never red.
ALLOWED = {}  # e.g. {9: "回想"}

SEED_APPROVER = "設定"


def _rows(db, query: str, params: dict | None = None) -> list[dict]:
    return list(db.execute(query, params or {}))


def _create_state(db, who, attr, value, start, end, cause, approved_by, toward=None) -> int:
    """Create one State under its Entity (plus STARTED_AT and TOWARD); return its id."""
    params = {"who": who, "attr": attr, "value": value, "from": start, "to": end,
              "cause": cause, "by": approved_by}
    if toward is None:
        rows = _rows(db, (
            "MATCH (e:Entity {name: $who}) "
            "CREATE (e)-[:HAS]->(s:State {attr: $attr, value: $value, from: $from, to: $to, "
            "cause: $cause, approved_by: $by}) RETURN id(s) AS id"), params)
    else:
        params["toward"] = toward
        rows = _rows(db, (
            "MATCH (e:Entity {name: $who}), (t:Entity {name: $toward}) "
            "CREATE (e)-[:HAS]->(s:State {attr: $attr, value: $value, from: $from, to: $to, "
            "cause: $cause, approved_by: $by})-[:TOWARD]->(t) RETURN id(s) AS id"), params)
    if not rows:
        raise ValueError(f"unknown entity: {who}" + (f" / {toward}" if toward else ""))
    sid = rows[0]["id"]
    if start >= 1:
        db.execute(
            "MATCH (s:State), (sh:Shot {no: $no}) WHERE id(s) = $sid CREATE (s)-[:STARTED_AT]->(sh)",
            {"sid": sid, "no": start},
        )
    return sid


def _link_replaced(db, old_id: int, new_id: int, cause: str, shot: int) -> None:
    db.execute(
        "MATCH (a:State), (b:State) WHERE id(a) = $a AND id(b) = $b "
        "CREATE (a)-[:REPLACED_BY {cause: $cause, shot: $shot}]->(b)",
        {"a": old_id, "b": new_id, "cause": cause, "shot": shot},
    )


def build(path: Path = DB_PATH, demo: bool = False):
    """Rebuild the store and return an open connection.

    demo=False builds the full record; demo=True builds the demo record
    (without the S5 jacket change).
    """
    path = Path(path)
    if path.exists():
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = relate.connect(str(path))
    for kind, name in ENTITIES:
        db.execute(f"CREATE (:{kind}:Entity {{name: $name, kind: $kind}})", {"name": name, "kind": kind})
    for no, text in SHOTS.items():
        db.execute("CREATE (:Shot {no: $no, text: $text})", {"no": no, "text": text})
    db.execute("MATCH (a:Shot), (b:Shot) WHERE b.no = a.no + 1 CREATE (a)-[:NEXT]->(b)")
    for a, b, kind in RELATIONS:
        db.execute(
            "MATCH (a:Entity {name: $a}), (b:Entity {name: $b}) "
            "CREATE (a)-[:RELATES_TO {kind: $kind, fixed: true}]->(b)",
            {"a": a, "b": b, "kind": kind},
        )

    rows = [(*r, None) for r in (DEMO_STATES if demo else STATES)] + list(REL_STATES)
    last: dict[tuple, tuple[int, int]] = {}  # (who, attr, toward) -> (state id, to)
    for who, attr, value, start, end, cause, toward in sorted(rows, key=lambda r: r[3]):
        sid = _create_state(db, who, attr, value, start, end, cause, SEED_APPROVER, toward)
        key = (who, attr, toward)
        if key in last and last[key][1] + 1 == start:
            _link_replaced(db, last[key][0], sid, cause, start)
        last[key] = (sid, end)
    return db


def reset():
    """Rebuild the demo record (button in the app)."""
    return build(demo=True)


def _toward_clause(toward) -> str:
    return "AND (s)-[:TOWARD]->(:Entity {name: $toward}) " if toward else "AND NOT (s)-[:TOWARD]->() "


def expected(db, entity: str, attr: str, shot: int, toward: str | None = None):
    """The recorded value of (entity, attr[, toward]) at a shot, or None when unknown.

    Returns {value, cause, since}. Without `toward`, relationship States are ignored.
    """
    rows = _rows(db, (
        "MATCH (e:Entity {name: $ent})-[:HAS]->(s:State) "
        "WHERE s.attr = $attr AND s.from <= $shot AND s.to >= $shot "
        + _toward_clause(toward) +
        "RETURN s.value AS value, s.cause AS cause, s.from AS since"),
        {"ent": entity, "attr": attr, "shot": shot, "toward": toward},
    )
    if not rows:
        return None
    return max(rows, key=lambda r: r["since"])


def states_at(db, shot: int) -> list[dict]:
    """Every state valid at a shot: rows {who, attr, toward, value, cause}."""
    rows = _rows(db, (
        "MATCH (e:Entity)-[:HAS]->(s:State) WHERE s.from <= $shot AND s.to >= $shot "
        "OPTIONAL MATCH (s)-[:TOWARD]->(t:Entity) "
        "RETURN e.name AS who, s.attr AS attr, t.name AS toward, s.value AS value, "
        "s.cause AS cause, s.from AS since"), {"shot": shot})
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["who"], r["attr"], r["toward"])
        if key not in best or r["since"] > best[key]["since"]:
            best[key] = r
    order = {name: i for i, (_, name) in enumerate(ENTITIES)}
    out = [{k: r[k] for k in ("who", "attr", "toward", "value", "cause")} for r in best.values()]
    return sorted(out, key=lambda r: (order.get(r["who"], 99), r["toward"] or "", r["attr"]))


def registry() -> dict:
    """Registered entities, attrs and allowed values (for the proposal guards).

    {entities: [...], attrs: {entity: {attr: [values]}}, relations: {(entity, toward): {attr: [values]}}}
    """
    attrs: dict[str, dict[str, list[str]]] = {}
    relations: dict[tuple[str, str], dict[str, list[str]]] = {}

    def add(ent, attr, value, toward=None):
        bucket = attrs.setdefault(ent, {}) if toward is None else relations.setdefault((ent, toward), {})
        values = bucket.setdefault(attr, [])
        if value not in values:
            values.append(value)

    for ent, attr, value, *_ in STATES:
        add(ent, attr, value)
    for who, attr, value, _s, _e, _c, toward in REL_STATES:
        add(who, attr, value, toward)
    try:
        import checker  # lazy: checker imports world
        lexicon = [(row[1], row[2], row[3], row[4] if len(row) > 4 else None) for row in checker.LEXICON]
    except Exception:
        lexicon = EXTRA_VALUES
    for ent, attr, value, toward in lexicon:
        add(ent, attr, value, toward)
    return {"entities": [name for _, name in ENTITIES], "attrs": attrs, "relations": relations}


def apply_change(db, entity: str, attr: str, frm: str, to: str, shot: int, cause: str,
                 toward: str | None = None) -> None:
    """Write a human-approved change: close the State valid at `shot` whose value is
    `frm` (to = shot-1) and open a new State from `shot` with the cause.

    The new State runs to the old State's `to` (END in the demo), so it never
    overlaps a later recorded change. Raises ValueError when no State matches.
    """
    rows = _rows(db, (
        "MATCH (e:Entity {name: $ent})-[:HAS]->(s:State) "
        "WHERE s.attr = $attr AND s.value = $frm AND s.from <= $shot AND s.to >= $shot "
        + _toward_clause(toward) +
        "RETURN id(s) AS id, s.to AS to"),
        {"ent": entity, "attr": attr, "frm": frm, "shot": shot, "toward": toward},
    )
    if not rows:
        target = f"{entity}→{toward}" if toward else entity
        raise ValueError(f"S{shot} に {target} の {attr}「{frm}」の記録がない")
    old_id, old_to = rows[0]["id"], rows[0]["to"]
    db.execute("MATCH (s:State) WHERE id(s) = $id SET s.to = $to", {"id": old_id, "to": shot - 1})
    new_id = _create_state(db, entity, attr, to, shot, old_to if old_to is not None else END,
                           cause, "human", toward)
    _link_replaced(db, old_id, new_id, cause, shot)


def export(db) -> dict:
    """Plain dicts of the whole graph for the Neo4j mirror.

    entities: [{name, kind}]
    shots:    [{no, text}]
    states:   [{id, who, attr, value, from, to, cause, approved_by, toward}]
    rels:     [{type, src, dst, props}] where src/dst are node refs
              {"Entity": name} | {"State": id} | {"Shot": no}
    """
    entities = _rows(db, "MATCH (e:Entity) RETURN e.name AS name, e.kind AS kind")
    shots = sorted(_rows(db, "MATCH (s:Shot) RETURN s.no AS no, s.text AS text"), key=lambda r: r["no"])
    states = _rows(db, (
        "MATCH (e:Entity)-[:HAS]->(s:State) OPTIONAL MATCH (s)-[:TOWARD]->(t:Entity) "
        "RETURN id(s) AS id, e.name AS who, s.attr AS attr, s.value AS value, s.from AS `from`, "
        "s.to AS to, s.cause AS cause, s.approved_by AS approved_by, t.name AS toward"))
    states.sort(key=lambda r: r["id"])
    rels = []
    for s in states:
        rels.append({"type": "HAS", "src": {"Entity": s["who"]}, "dst": {"State": s["id"]}, "props": {}})
        if s["toward"]:
            rels.append({"type": "TOWARD", "src": {"State": s["id"]}, "dst": {"Entity": s["toward"]}, "props": {}})
    for r in _rows(db, "MATCH (s:State)-[:STARTED_AT]->(sh:Shot) RETURN id(s) AS s, sh.no AS no"):
        rels.append({"type": "STARTED_AT", "src": {"State": r["s"]}, "dst": {"Shot": r["no"]}, "props": {}})
    for r in _rows(db, (
            "MATCH (a:State)-[r:REPLACED_BY]->(b:State) "
            "RETURN id(a) AS a, id(b) AS b, r.cause AS cause, r.shot AS shot")):
        rels.append({"type": "REPLACED_BY", "src": {"State": r["a"]}, "dst": {"State": r["b"]},
                     "props": {"cause": r["cause"], "shot": r["shot"]}})
    for r in _rows(db, (
            "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) "
            "RETURN a.name AS a, b.name AS b, r.kind AS kind, r.fixed AS fixed")):
        rels.append({"type": "RELATES_TO", "src": {"Entity": r["a"]}, "dst": {"Entity": r["b"]},
                     "props": {"kind": r["kind"], "fixed": r["fixed"]}})
    for r in _rows(db, "MATCH (a:Shot)-[:NEXT]->(b:Shot) RETURN a.no AS a, b.no AS b"):
        rels.append({"type": "NEXT", "src": {"Shot": r["a"]}, "dst": {"Shot": r["b"]}, "props": {}})
    return {"entities": entities, "states": states, "rels": rels, "shots": shots}


if __name__ == "__main__":
    db = build()
    print(_rows(db, "MATCH (e:Entity) RETURN count(e) AS entities"))
    print(_rows(db, "MATCH (s:State) RETURN count(s) AS states"))
    print(expected(db, "剣", "持ち手", 7))
    print(expected(db, "ミナ", "信頼", 5, toward="カイ"))
