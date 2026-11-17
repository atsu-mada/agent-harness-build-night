# Continuity Checker (Agent Harness Build Night)

A shot list continuity checker. Each shot description is split into claims, and each claim is compared with the continuity record stored as a graph in Relate (Neo4j's embedded graph database). Contradictions are shown in red. The left panel is a baseline that only sees the previous shot; the right panel is the harness that reads the graph.

## Files

- `world.py` — sample world (original), the shot list S1–S6, and the state record as intervals (`from`/`to` shot, with the cause of each change). `build()` writes `continuity.rl`.
- `checker.py` — claim extraction (phrase lexicon), graph check, no-memory baseline, and the 10 eval cases (7 with a contradiction, 3 with a legitimate change).
- `app.py` — Gradio screen: side-by-side highlight and the eval button.

## Run (MacBook)

With uv:

```bash
uv run --with relate-db python src/continuity_checker/checker.py
```

```bash
uv run --with relate-db --with gradio python src/continuity_checker/app.py
```

Without uv (venv):

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install relate-db gradio
```

```bash
python src/continuity_checker/checker.py
```

```bash
python src/continuity_checker/app.py
```

Expected eval result: baseline finds 2/7 with 1/3 false positives; graph finds 7/7 with 0/3.

## Show the graph in Neo4j Browser (unverified)

Relate's README says Neo4j Browser connects over Bolt. After `python src/continuity_checker/world.py`:

```bash
relate serve --database ./data/continuity.rl --bolt 7687 --http 7474
```

Use the token it prints to sign in. Not tested yet.

## Ideas for the build time

- Replace `extract()` with an LLM extractor (`claude -p` or ai& credits) that returns the same tuples; keep the red decision in the graph query.
- Add a shot that is an intended flashback to `world.ALLOWED` and show it stays green.
- Add "teleport" checks: a character's place changes without a move event.
