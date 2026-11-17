"""Inline SVG builders for the demo page: a shot card (figures ringed by the
graph result) and the subgraph that decided each claim. Drawn in code, no
image generation. Colors come from Gradio CSS variables so light and dark
themes both work; status colors are fixed tokens.
"""
from __future__ import annotations

from html import escape

STATUS = {"矛盾": "#DC2626", "OK": "#16A34A", "不明": "#9CA3AF"}
FG = "var(--body-text-color, #111827)"
BG = "var(--block-background-fill, #ffffff)"
MUTED = "var(--body-text-color-subdued, #6B7280)"
FONT = "font-family:'Open Sans',sans-serif"

CHARACTERS = {"ミナ", "カイ"}
ICONS = {"剣": "🗡", "鍵": "🔑", "グラス": "🥛", "コーヒー": "☕", "ノートPC": "💻", "部室": "🚪"}


def _t(x, y, s, size=13, fill=FG, weight=400, anchor="middle"):
    return (f"<text x='{x}' y='{y}' font-size='{size}' fill='{fill}' font-weight='{weight}' "
            f"text-anchor='{anchor}' style=\"{FONT}\">{escape(str(s))}</text>")


def _worst(statuses):
    for s in ("矛盾", "不明", "OK"):
        if s in statuses:
            return s
    return None


def shot_card(shot, text, findings) -> str:
    """One figure per entity in the claims, ringed red / green / gray."""
    if not findings:
        return f"<div style='color:{MUTED};{FONT}'>チェックするとショットの絵がここに出ます</div>"
    by_ent: dict[str, list] = {}
    for f in findings:
        by_ent.setdefault(f.claim.entity, []).append(f)
    w, cell, h = max(360, 150 * len(by_ent)), 150, 230
    parts = [f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='S{shot} のショット'>",
             f"<rect x='1' y='1' width='{w - 2}' height='{h - 2}' rx='16' fill='{BG}' stroke='{FG}'/>",
             _t(16, 24, f"S{shot}", 14, FG, 700, "start")]
    x0 = (w - cell * len(by_ent)) / 2
    for i, (ent, fs) in enumerate(by_ent.items()):
        cx, cy = x0 + cell * i + cell / 2, 95
        color = STATUS[_worst([f.status for f in fs])]
        parts.append(f"<circle cx='{cx}' cy='{cy}' r='52' fill='none' stroke='{color}' stroke-width='4'/>")
        if ent in CHARACTERS:
            jacket = next((f.claim.value for f in fs if f.claim.attr == "上着"), None)
            body = {"赤": "#DC2626", "青": "#2563EB"}.get(jacket, "none")
            parts.append(f"<circle cx='{cx}' cy='{cy - 22}' r='13' fill='none' stroke='{FG}' stroke-width='2'/>")
            parts.append(f"<path d='M{cx - 22} {cy + 32} Q{cx} {cy - 12} {cx + 22} {cy + 32} Z' "
                         f"fill='{body}' stroke='{FG}' stroke-width='2'/>")
        else:
            parts.append(_t(cx, cy + 14, ICONS.get(ent, "◆"), 38))
        parts.append(_t(cx, cy + 74, ent, 14, FG, 700))
        for j, f in enumerate(fs[:2]):
            who = f"→{f.claim.toward} " if getattr(f.claim, "toward", None) else ""
            parts.append(_t(cx, cy + 94 + 16 * j, f"{who}{f.claim.attr}：{f.claim.value}", 12,
                            STATUS[f.status], 600))
    parts.append("</svg>")
    return "".join(parts)


def graph_panel(export: dict, shot, findings) -> str:
    """Entity -HAS-> State chain (REPLACED_BY with cause), STARTED_AT shot,
    TOWARD for relationship states; the State valid at the shot is ringed."""
    if not findings:
        return f"<div style='color:{MUTED};{FONT}'>チェックすると判定に使ったグラフがここに出ます</div>"
    states = export.get("states", [])
    repl = {(r["src"]["State"], r["dst"]["State"]): r["props"]
            for r in export.get("rels", []) if r["type"] == "REPLACED_BY"}
    rows, seen = [], set()
    for f in findings:
        c = f.claim
        key = (c.entity, c.attr, getattr(c, "toward", None))
        if key in seen:
            continue
        seen.add(key)
        chain = sorted((s for s in states if (s["who"], s["attr"], s.get("toward")) == key),
                       key=lambda s: s["from"])
        rows.append((key, chain, f.status, c.value))
    ew, sw, gap, rh = 96, 176, 64, 132
    w = ew + 40 + max(1, max(len(r[1]) for r in rows)) * (sw + gap)
    h = rh * len(rows) + 16
    p = [f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='判定に使ったグラフ'>",
         "<defs><marker id='ar' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' "
         f"orient='auto'><path d='M0 0L10 5L0 10z' fill='{FG}'/></marker></defs>"]
    for i, (key, chain, status, claimed) in enumerate(rows):
        ent, attr, toward = key
        y = 16 + rh * i
        p.append(f"<rect x='4' y='{y + 22}' width='{ew}' height='40' rx='20' fill='{FG}'/>")
        p.append(_t(4 + ew / 2, y + 47, ent, 14, BG, 700))
        if not chain:
            p.append(_t(ew + 24, y + 47, f"{attr}：記録なし → 不明", 13, STATUS["不明"], 600, "start"))
            continue
        prev_right = None
        for j, s in enumerate(chain):
            x = ew + 40 + j * (sw + gap)
            valid = s["from"] <= int(shot) <= s["to"]
            stroke = STATUS[status] if valid else FG
            sw_px = 4 if valid else 1.5
            to = "END" if s["to"] >= 99 else f"S{s['to']}"
            p.append(f"<rect x='{x}' y='{y}' width='{sw}' height='84' rx='12' fill='{BG}' "
                     f"stroke='{stroke}' stroke-width='{sw_px}'/>")
            p.append(_t(x + sw / 2, y + 22, f"{attr}：{s['value']}", 14, FG, 700))
            p.append(_t(x + sw / 2, y + 41, f"S{s['from']}–{to}", 12, MUTED))
            p.append(_t(x + sw / 2, y + 60, (s.get("cause") or "")[:14], 11, MUTED))
            if s.get("toward"):
                p.append(_t(x + sw / 2, y + 77, f"TOWARD → {s['toward']}", 11, FG, 600))
            p.append(_t(x + sw / 2, y + 102, f"STARTED_AT S{s['from']}", 10, MUTED))
            if j == 0:
                p.append(f"<line x1='{ew + 4}' y1='{y + 42}' x2='{x}' y2='{y + 42}' stroke='{FG}' "
                         f"marker-end='url(#ar)'/>")
                p.append(_t((ew + 4 + x) / 2, y + 36, "HAS", 10, MUTED))
            else:
                prev = chain[j - 1]
                props = repl.get((prev["id"], s["id"]), {})
                p.append(f"<line x1='{prev_right}' y1='{y + 42}' x2='{x}' y2='{y + 42}' stroke='{FG}' "
                         f"stroke-dasharray='{'' if props else '4 3'}' marker-end='url(#ar)'/>")
                p.append(_t((prev_right + x) / 2, y + 36, "REPLACED_BY", 9, MUTED))
                if props.get("cause"):
                    p.append(_t((prev_right + x) / 2, y + 56, props["cause"][:8], 9, MUTED))
            if valid:
                p.append(_t(x + sw / 2, y + 120, f"S{int(shot)} の判定：「{claimed}」→ {status}", 11,
                            STATUS[status], 700))
            prev_right = x + sw
    p.append("</svg>")
    return "".join(p)
