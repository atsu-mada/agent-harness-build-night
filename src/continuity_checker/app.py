"""Demo screen: check a shot without memory (left) and with the graph (right),
let the LLM propose state changes, approve them as a human, and read the
record that would be passed to a generation prompt.

Calls only the contract names (world.reset / expected / states_at /
apply_change / export, checker.check_with_graph / check_without_memory /
evaluate, propose.propose_change, mirror.sync). Names that are not merged
yet are looked up with getattr, so the page still starts on develop.
"""
from __future__ import annotations

import base64
import functools
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import gradio as gr

import checker
import visuals
import world

try:
    import propose
except ImportError:  # W2 not merged yet
    propose = None
try:
    import mirror
except ImportError:  # W4 not merged yet
    mirror = None

COLORS = {"矛盾": "red", "OK": "green", "不明": "gray"}
MISSING = "（未実装：{}）"


def _reset_db():
    if hasattr(world, "reset"):
        return world.reset()
    return world.build()


# Relate connections are thread-affine, while Gradio runs handlers on a
# thread pool. Every handler that touches the store runs on this one thread.
_DB_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relate")


def on_db_thread(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return _DB_THREAD.submit(fn, *args, **kwargs).result()
    return wrapper


DB = {"db": _DB_THREAD.submit(_reset_db).result()}


def db():
    return DB["db"]


def sync_mirror() -> str:
    """Mirror the record to the local Neo4j; never break the page."""
    if mirror is None or not hasattr(mirror, "sync") or not hasattr(world, "export"):
        return "Neo4j 未接続（mirror 未実装）"
    try:
        n = mirror.sync(world.export(db()))
        return f"Neo4j に同期しました（{n} ノード）"
    except Exception as e:  # noqa: BLE001 - shown on screen instead
        return f"Neo4j 未接続（{type(e).__name__}）"


# ---------- check ----------

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
    lines = []
    for f in findings:
        who = f.claim.entity
        toward = getattr(f.claim, "toward", None)
        if toward:
            who = f"{who}→{toward}"
        lines.append(f"- {who}の{f.claim.attr}「{f.claim.value}」→ {f.status}：{f.note}")
    return "\n".join(lines) or "（抽出なし）"


def check_pair(shot, text):
    base = checker.check_without_memory(shot, text)
    graph = checker.check_with_graph(db(), shot, text)
    return base, graph


def get_proposals(shot, text) -> tuple[list[dict], str]:
    fn = getattr(propose, "propose_change", None) if propose else None
    if fn is None:
        return [], MISSING.format("propose.propose_change")
    try:
        props = fn(db(), shot, text)
    except Exception as e:  # noqa: BLE001
        return [], f"提案を作れなかった（{type(e).__name__}）"
    out = []
    for p in props or []:
        get = p.get if isinstance(p, dict) else (lambda k, d=None, _p=p: getattr(_p, k, d))
        out.append({
            "entity": get("entity"), "attr": get("attr"),
            "frm": get("frm", get("from")), "to": get("to"),
            "cause_quote": get("cause_quote", ""), "toward": get("toward"),
            "ok": bool(get("ok", False)), "reason": get("reason", "") or "",
            "shot": shot, "status": "提案",
        })
    return out, "" if out else "変化の提案なし"


@on_db_thread
def run(shot, text, reds):
    shot = int(shot)
    base, graph = check_pair(shot, text)
    if any(f.status == "矛盾" for f in graph):
        reds = [r for r in reds if r != [shot, text]] + [[shot, text]]
    props, msg = get_proposals(shot, text)
    return (*render_check(shot, text, base, graph), props, msg, reds)


# ---------- approve / reject ----------

@on_db_thread
def approve(i, props, reds, shot, text):
    props = [dict(x) for x in props]
    p = props[i]
    if not hasattr(world, "apply_change"):
        p["status"] = "失敗"
        return props, MISSING.format("world.apply_change"), shot, text, *recheck(shot, text)
    cause = f"S{p['shot']} {p['cause_quote']}".strip()
    try:
        world.apply_change(db(), p["entity"], p["attr"], p["frm"], p["to"], p["shot"], cause,
                           toward=p["toward"])
    except Exception as e:  # noqa: BLE001
        p["status"] = "失敗"
        return props, f"書き込めませんでした：{e}", shot, text, *recheck(shot, text)
    p["status"] = "承認済み"
    msg = f"承認：{label(p)} を S{p['shot']} から記録しました。{sync_mirror()}"
    # Re-check the latest shot that was red, so the effect (S6 green) shows at once.
    later = [r for r in reds if r[0] > p["shot"]]
    if later:
        shot, text = later[-1]
        msg += f"　→ S{shot} を再チェック"
    return props, msg, shot, text, *recheck(shot, text)


def reject(i, props):
    props = [dict(x) for x in props]
    props[i]["status"] = "却下"
    return props, f"却下：{label(props[i])}（記録は変わりません）"


def recheck(shot, text):
    base, graph = check_pair(int(shot), text)
    return render_check(int(shot), text, base, graph)


def render_check(shot, text, base, graph):
    """Text highlights and notes for both sides, plus the shot card and graph SVGs."""
    try:
        export = world.export(db()) if hasattr(world, "export") else {}
        card = visuals.graph_card(export, shot, text, base, graph)
    except Exception as e:  # noqa: BLE001 - never break the check
        card = f"図を描けませんでした（{type(e).__name__}）"
    return (to_highlight(text, base), notes(base), to_highlight(text, graph), notes(graph), card)


def label(p):
    who = f"{p['entity']}→{p['toward']}" if p.get("toward") else p["entity"]
    return f"{who}の{p['attr']}：{p['frm']} → {p['to']}"


# ---------- reset / eval / before generation ----------

@on_db_thread
def do_reset():
    DB["db"] = _reset_db()
    return f"デモ記録に戻しました。{sync_mirror()}", [], [], "", EMPTY_CARD


@on_db_thread
def run_eval():
    rows, score, n_bad, n_ok = checker.evaluate(db())
    table = [[f"S{s}", t, truth, "赤" if b else "", "赤" if g else ""] for s, t, truth, b, g in rows]
    summary = (
        f"### 記憶なし：発見 {score['base'][0]}/{n_bad}・誤検出 {score['base'][1]}/{n_ok}　"
        f"→　グラフあり：発見 {score['graph'][0]}/{n_bad}・誤検出 {score['graph'][1]}/{n_ok}"
    )
    return summary, table


@on_db_thread
def before_generation(shot):
    if not hasattr(world, "states_at"):
        return [], MISSING.format("world.states_at")
    rows = world.states_at(db(), int(shot))
    table = [[r.get("who"), r.get("attr"), r.get("toward") or "", r.get("value"), r.get("cause")]
             for r in rows]
    return table, f"S{int(shot)} の生成プロンプトに渡す記録：{len(table)} 件"


# ---------- page ----------

EMPTY_CARD = visuals.graph_card({}, 0, "", [], [])
EXPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "exports"


def save_png(data_url, shot):
    """Write the card that the browser rasterized (1920x1080 PNG) to data/exports/."""
    if not data_url or not str(data_url).startswith("data:image/png;base64,"):
        return gr.update(visible=False), "画像を作れませんでした（先にチェックしてください）"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"cc-graph-S{int(shot or 0)}-{datetime.now():%Y%m%d-%H%M%S}.png"
    out = EXPORT_DIR / name
    out.write_bytes(base64.b64decode(str(data_url).split(",", 1)[1]))
    return gr.update(value=str(out), visible=True), f"保存しました：data/exports/{name}（1920×1080）"


# Rasterize the card's SVG in the browser, so the PNG matches what is on screen
# (system Japanese fonts and emoji included) without a server-side renderer.
SVG_TO_PNG_JS = """
async (dataUrl, shot) => {
  const svg = document.querySelector('#graph-card svg');
  if (!svg) return ['', shot];
  const xml = new XMLSerializer().serializeToString(svg);
  const img = new Image();
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
  await img.decode();
  const c = document.createElement('canvas');
  c.width = 1920; c.height = 1080;
  c.getContext('2d').drawImage(img, 0, 0, 1920, 1080);
  return [c.toDataURL('image/png'), shot];
}
"""

# Default design system 'codex': black on white, Open Sans, pill controls,
# no shadows or gradients. Dark mode inverts black and white.
THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.neutral,
    neutral_hue=gr.themes.colors.neutral,
    font=[gr.themes.GoogleFont("Open Sans"), "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    radius_size=gr.themes.sizes.radius_lg,
).set(
    body_background_fill="#ffffff", body_background_fill_dark="#0a0a0a",
    body_text_color="#111827", body_text_color_dark="#f5f5f5",
    block_background_fill="#ffffff", block_background_fill_dark="#0a0a0a",
    block_border_color="#e5e5e5", block_border_color_dark="#262626",
    block_shadow="none", block_shadow_dark="none",
    button_primary_background_fill="#000000", button_primary_background_fill_dark="#ffffff",
    button_primary_background_fill_hover="#262626", button_primary_background_fill_hover_dark="#e5e5e5",
    button_primary_text_color="#ffffff", button_primary_text_color_dark="#000000",
    button_secondary_background_fill="#ffffff", button_secondary_background_fill_dark="#0a0a0a",
    button_secondary_border_color="#000000", button_secondary_border_color_dark="#ffffff",
    button_secondary_text_color="#000000", button_secondary_text_color_dark="#ffffff",
)
CSS = """
* { box-shadow: none !important; background-image: none !important; }
button { border-radius: 9999px !important; font-weight: 600 !important; }
h2 { font-weight: 800 !important; letter-spacing: -0.02em; }
h3 { font-weight: 700 !important; }
#graph-card svg { display: block; width: 100%; height: auto; border-radius: 28px; }
#graph-card { padding: 0 !important; border: none !important; }
"""

with gr.Blocks(title="Continuity Checker") as demo:
    gr.Markdown("## ショットのつながりチェッカー（Relate / Neo4j）")
    props_state = gr.State([])
    reds_state = gr.State([])
    with gr.Row():
        shot = gr.Number(label="ショット番号", value=7, precision=0, scale=1)
        text = gr.Textbox(label="ショットの説明", value="ミナが剣を右手で振る。", scale=5)
    gr.Examples([[c[0], c[1]] for c in checker.CASES] + [[5, world.SHOTS.get(5, "")]], [shot, text])
    with gr.Row():
        btn = gr.Button("チェック", variant="primary")
        reset_btn = gr.Button("リセット")
    status_md = gr.Markdown()
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 記憶なし（直前のショットだけ）")
            base_hl = gr.HighlightedText(color_map=COLORS, show_legend=True)
            base_md = gr.Markdown()
        with gr.Column():
            gr.Markdown("### ハーネス（グラフの記録を参照）")
            graph_hl = gr.HighlightedText(color_map=COLORS, show_legend=True)
            graph_md = gr.Markdown()

    gr.Markdown("### 変化の提案（LLM → ガード → 人が承認）")
    prop_msg = gr.Markdown()
    card_html = gr.HTML(EMPTY_CARD, render=False, elem_id="graph-card")
    check_outputs = [base_hl, base_md, graph_hl, graph_md, card_html]

    @gr.render(inputs=props_state)
    def cards(props):
        for i, p in enumerate(props):
            with gr.Group():
                if not p["ok"]:
                    gr.Markdown(
                        f"<span style='color:gray'>✕ {label(p)}　「{p['cause_quote']}」<br>"
                        f"却下（ガード）：{p['reason']}</span>")
                    continue
                gr.Markdown(f"**{label(p)}**　原因「{p['cause_quote']}」　S{p['shot']}　"
                            f"［{p['status']}］")
                if p["status"] != "提案":
                    continue
                with gr.Row():
                    ok_btn = gr.Button("承認", variant="primary", size="sm")
                    ng_btn = gr.Button("却下", size="sm")
                ok_btn.click(lambda ps, rs, s, t, i=i: approve(i, ps, rs, s, t),
                             [props_state, reds_state, shot, text],
                             [props_state, status_md, shot, text, *check_outputs])
                ng_btn.click(lambda ps, i=i: reject(i, ps), [props_state], [props_state, status_md])

    btn.click(run, [shot, text, reds_state], [*check_outputs, props_state, prop_msg, reds_state])
    reset_btn.click(do_reset, None, [status_md, props_state, reds_state, prop_msg, card_html])

    gr.Markdown("---")
    gr.Markdown("## グラフで見る（ショットの絵・記憶なしとの比較・判定に使った記録）")
    card_html.render()
    with gr.Row():
        png_btn = gr.Button("画像として保存（PNG）", variant="primary", scale=1)
        png_msg = gr.Markdown()
    png_file = gr.File(label="保存した画像", interactive=False, visible=False)
    png_data = gr.Textbox(visible=False)
    png_btn.click(save_png, [png_data, shot], [png_file, png_msg], js=SVG_TO_PNG_JS)

    gr.Markdown("---")
    gr.Markdown("### 生成の前の欄（このショットで有効な記録＝プロンプトに渡す文脈）")
    with gr.Row():
        gen_shot = gr.Number(label="ショット番号", value=6, precision=0, scale=1)
        gen_btn = gr.Button("記録を読む", scale=1)
    gen_md = gr.Markdown()
    gen_df = gr.Dataframe(headers=["だれ／なに", "属性", "相手", "値", "原因"], wrap=True)
    gen_btn.click(before_generation, [gen_shot], [gen_df, gen_md])

    gr.Markdown("---")
    eval_btn = gr.Button(f"評価{len(checker.CASES)}件を流す（いまの記録で）")
    eval_md = gr.Markdown()
    eval_df = gr.Dataframe(headers=["ショット", "説明", "正解", "記憶なし", "グラフ"], wrap=True)
    eval_btn.click(run_eval, None, [eval_md, eval_df])

if __name__ == "__main__":
    demo.launch(theme=THEME, css=CSS)
