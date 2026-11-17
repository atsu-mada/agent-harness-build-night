# agent-harness-build-night

Built at "Agent Harness Build Night" (Neo4j), Tuesday 2026-11-17, Ebisu, Tokyo.

**Continuity Checker** is a harness for a video-generation agent. Small character details (a jacket, a necklace, which hand holds a sword) are kept as graph states with an interval (`from`/`to` shot) and a cause. Each shot description is checked against that record, and contradictions are shown in red.

> The LLM only says what changed. A human approves. The graph decides what is red.

## What it does

- **Record as a graph**: `(Entity)-[:HAS]->(State {attr, value, from, to, cause})`, `(State)-[:REPLACED_BY {cause, shot}]->(State)`, `(State)-[:STARTED_AT]->(Shot)`, relationships between characters (`TOWARD`, `RELATES_TO`). Stored in Relate (Neo4j's embedded graph database).
- **Check**: claims from a shot description are compared with the state valid at that shot. Left panel: a baseline that only sees the previous shot. Right panel: the graph.
- **Propose and approve**: `claude -p` proposes a state change only with a cause quoted from the text. Four guards (registered entity and attribute, verbatim cause, change verb, previous value matches the record) run before a human can approve. Nothing is written until a human approves.
- **Before generation**: the states valid at a shot are listed as context for the next prompt.
- **Neo4j mirror**: approved records are copied to a Neo4j server under `CC_` labels for Neo4j Browser.

## Evaluation (16 shot descriptions: 10 contradictions, 6 legitimate changes)

| | Contradictions found | False alarms |
|---|---|---|
| Without memory (previous shot only) | 3 / 10 | 1 / 6 |
| Graph record | 10 / 10 | 0 / 6 (after one approval) |

## Run

```bash
uv sync
```

```bash
uv run python src/continuity_checker/checker.py
```

```bash
scripts/run.sh
```

`scripts/run.sh` starts the Gradio app; the Neo4j password is read from a local encrypted key store and passed only to that process. Without Neo4j, the checker and the evaluation run on the embedded store alone.

Details: [docs/continuity-checker.md](docs/continuity-checker.md), Neo4j Browser queries: [docs/browser-queries.md](docs/browser-queries.md).

## Layout

- `src/continuity_checker/`: record (`world.py`), check and eval (`checker.py`), proposals and guards (`propose.py`), app (`app.py`), Neo4j mirror (`mirror.py`), LLM helpers.
- `src/test/`: tests.
- `docs/`: design notes and run details.
- `config/`: shared settings (no secrets).
- `data/`: the graph store and logs; stays local.

The sample world (Mina and Kai) is original.
