"""Connection to the Mac mini's local Neo4j for the `CC_` copy of the continuity record.

The password comes only from the environment variable NEO4J_PASSWORD, which
`scripts/run.sh` fills through `api_secrets.run_with_key` (key id `neo4j_local_password`).
URI, user name and database are not secret and live in `config/neo4j.json`.

The database also holds other graphs (`Character`, `Shot`, ...). Code here writes and
deletes nodes whose labels start with `CC_` only.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from neo4j import GraphDatabase

CONFIG = json.loads((Path(__file__).resolve().parents[2] / "config" / "neo4j.json").read_text())


def driver():
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise SystemExit("NEO4J_PASSWORD is not set: start this through scripts/run.sh")
    uri = os.environ.get("NEO4J_URI", CONFIG["uri"])
    user = os.environ.get("NEO4J_USER", CONFIG["user"])
    return GraphDatabase.driver(uri, auth=(user, password))


def probe() -> None:
    """Write one CC_Probe node, read it back, delete it. Touches no other label."""
    token = uuid.uuid4().hex
    with driver() as d:
        d.verify_connectivity()
        db = CONFIG["database"]
        d.execute_query("CREATE (:CC_Probe {token: $t})", t=token, database_=db)
        found = d.execute_query(
            "MATCH (p:CC_Probe {token: $t}) RETURN count(p) AS n", t=token, database_=db
        ).records[0]["n"]
        d.execute_query("MATCH (p:CC_Probe {token: $t}) DELETE p", t=token, database_=db)
        left = d.execute_query(
            "MATCH (p:CC_Probe {token: $t}) RETURN count(p) AS n", t=token, database_=db
        ).records[0]["n"]
    if found != 1 or left != 0:
        raise SystemExit(f"probe failed: written={found}, left after delete={left}")
    print(f"Neo4j probe passed: {CONFIG['uri']} wrote, read and deleted one CC_Probe node")


if __name__ == "__main__":
    probe()
