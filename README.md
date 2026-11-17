# agent-harness-build-night

Work for "Agent Harness Build Night" (Neo4j), Tuesday 2026-11-17, 18:00–21:30 (JST), Ebisu.

The product is a shot-list continuity checker: each shot description is split into claims, and each claim is checked against a continuity record kept as a graph in Relate (Neo4j's embedded graph database). Contradictions are shown in red.

## Run

```bash
uv run --with relate-db python src/continuity_checker/checker.py
```

```bash
uv run --with relate-db --with gradio python src/continuity_checker/app.py
```

Details: [docs/continuity-checker.md](docs/continuity-checker.md).

## Layout

- `src/continuity_checker/`: the checker (`world.py`, `checker.py`, `app.py`).
- `docs/`: design notes and run details.
- `config/`: shared settings (`*.local.json` stays local).
- `data/`: the graph store and logs; stays local.
- `old/`: retired material.
