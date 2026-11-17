"""Demo screen: the same shot, checked without memory (left) and with the graph (right)."""
from __future__ import annotations

import gradio as gr

import checker
import world

DB = world.build()
COLORS = {"矛盾": "red", "OK": "green", "不明": "gray"}


def to_highlight(text, findings):
    parts, pos = [], 0
    for f in findings:
        if f.claim.start > pos:
            parts.append((text[pos:f.claim.start], None))
        parts.append((text[f.claim.start:f.claim.end], f.status))
        pos = f.claim.end
    if pos < len(text):
        parts.append((text[pos:], None))
    return parts


def notes(findings):
    return "\n".join(f"- {f.claim.entity}の{f.claim.attr}「{f.claim.value}」→ {f.status}：{f.note}" for f in findings) or "（抽出なし）"


def run(shot, text):
    shot = int(shot)
    base = checker.check_without_memory(shot, text)
    graph = checker.check_with_graph(DB, shot, text)
    return to_highlight(text, base), notes(base), to_highlight(text, graph), notes(graph)


def run_eval():
    rows, score, n_bad, n_ok = checker.evaluate(DB)
    table = [[f"S{s}", t, truth, "赤" if b else "", "赤" if g else ""] for s, t, truth, b, g in rows]
    summary = (
        f"### 記憶なし：発見 {score['base'][0]}/{n_bad}・誤検出 {score['base'][1]}/{n_ok}　"
        f"→　グラフあり：発見 {score['graph'][0]}/{n_bad}・誤検出 {score['graph'][1]}/{n_ok}"
    )
    return summary, table


with gr.Blocks(title="Continuity Checker") as demo:
    gr.Markdown("## ショットのつながりチェッカー（Relate / Neo4j）")
    with gr.Row():
        shot = gr.Number(label="ショット番号", value=7, precision=0, scale=1)
        text = gr.Textbox(label="ショットの説明", value="ミナが剣を右手で振る。", scale=5)
    examples = gr.Examples([[s, t] for s, t, _ in checker.CASES], [shot, text])
    btn = gr.Button("チェック", variant="primary")
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 記憶なし（直前のショットだけ）")
            base_hl = gr.HighlightedText(color_map=COLORS, show_legend=True)
            base_md = gr.Markdown()
        with gr.Column():
            gr.Markdown("### ハーネス（グラフの記録を参照）")
            graph_hl = gr.HighlightedText(color_map=COLORS, show_legend=True)
            graph_md = gr.Markdown()
    btn.click(run, [shot, text], [base_hl, base_md, graph_hl, graph_md])
    gr.Markdown("---")
    eval_btn = gr.Button("評価10件を流す")
    eval_md = gr.Markdown()
    eval_df = gr.Dataframe(headers=["ショット", "説明", "正解", "記憶なし", "グラフ"], wrap=True)
    eval_btn.click(run_eval, None, [eval_md, eval_df])

if __name__ == "__main__":
    demo.launch()
