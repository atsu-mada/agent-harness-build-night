# Neo4j Browser queries (demo)

Open Neo4j Browser at http://localhost:7474 on the Mac mini. The continuity record is mirrored there by `mirror.sync()` after each reset and each approval, with `CC_` labels only (`CC_Entity`, `CC_State`, `CC_Shot`). Paste one query at a time.

## 1. Kai's jacket history

Shows the jacket States of カイ, the REPLACED_BY edge with its cause, and STARTED_AT S5 on the State approved by a human.

```cypher
MATCH p=(:CC_Entity {name:'カイ'})-[:HAS]->(s:CC_State {attr:'上着'})
OPTIONAL MATCH r=(s)-[:REPLACED_BY]->()
OPTIONAL MATCH q=(s)-[:STARTED_AT]->()
RETURN p, r, q
```

## 2. States valid at S6

Shows, as a table, what goes into the prompt before generating S6: every State whose interval covers shot 6, with its cause.

```cypher
MATCH (e:CC_Entity)-[:HAS]->(s:CC_State)
WHERE s.from <= 6 <= s.to
OPTIONAL MATCH (s)-[:TOWARD]->(t:CC_Entity)
RETURN e.name AS who, s.attr AS attr, t.name AS toward, s.value AS value, s.cause AS cause
ORDER BY who, attr
```

## 3. Relationship network

Shows the fixed base (カイ -RELATES_TO 部の先輩-> ミナ) and the time-layered trust State ミナ→カイ (警戒 → 信頼) with STARTED_AT the S4 hand-over.

```cypher
MATCH (a:CC_Entity)-[r:RELATES_TO]-(b:CC_Entity)
OPTIONAL MATCH p=(a)-[:HAS]->(s:CC_State)-[:TOWARD]->(b)
OPTIONAL MATCH q=(s)-[:STARTED_AT]->(:CC_Shot)
RETURN a, r, b, p, q
```

## Clean-up

Removes this app's copy only; the PixLight demo graph (`CC_PX_` labels) and other graphs stay.

```cypher
MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'CC_')
  AND NOT any(l IN labels(n) WHERE l STARTS WITH 'CC_PX_')
DETACH DELETE n
```
