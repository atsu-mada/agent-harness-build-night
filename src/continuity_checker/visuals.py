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


# ---------- 16:9 graph card (fixed colors so it exports to PNG as seen) ----------

CARD_W, CARD_H = 1600, 900
C = {
    "bg": "#0B0F19", "panel": "#111827", "line": "#334155", "text": "#F8FAFC",
    "muted": "#94A3B8", "矛盾": "#F43F5E", "OK": "#22C55E", "不明": "#94A3B8",
    "accent": "#38BDF8", "toward": "#C084FC",
}
CFONT = "font-family:'Hiragino Sans','Noto Sans JP','Open Sans',sans-serif"
JACKETS = {"赤": "#F43F5E", "青": "#3B82F6"}


def _ct(x, y, s, size=20, fill=None, weight=400, anchor="middle"):
    return (f"<text x='{x:.0f}' y='{y:.0f}' font-size='{size}' fill='{fill or C['text']}' "
            f"font-weight='{weight}' text-anchor='{anchor}' style=\"{CFONT}\">{escape(str(s))}</text>")


def _fit(s, width, size):
    """Cut a string to the characters that fit (Japanese glyphs are about 1 em)."""
    s = str(s or "")
    n = max(1, int(width / size))
    return s if len(s) <= n else s[: n - 1] + "…"


def _pill(x, y, w, h, fill, stroke=None, sw=0):
    st = f" stroke='{stroke}' stroke-width='{sw}'" if stroke else ""
    return f"<rect x='{x:.0f}' y='{y:.0f}' width='{w:.0f}' height='{h:.0f}' rx='{h / 2:.0f}' fill='{fill}'{st}/>"


def _figure(cx, cy, ent, fs, r=74):
    color = C[_worst([f.status for f in fs])]
    out = [f"<circle cx='{cx:.0f}' cy='{cy:.0f}' r='{r}' fill='{C['bg']}' stroke='{color}' stroke-width='7'/>"]
    if ent in CHARACTERS:
        jacket = next((f.claim.value for f in fs if f.claim.attr == "上着"), None)
        body = JACKETS.get(jacket, C["panel"])
        out.append(f"<circle cx='{cx:.0f}' cy='{cy - 26:.0f}' r='18' fill='none' stroke='{C['text']}' stroke-width='3'/>")
        out.append(f"<path d='M{cx - 32:.0f} {cy + 44:.0f} Q{cx:.0f} {cy - 18:.0f} {cx + 32:.0f} {cy + 44:.0f} Z' "
                   f"fill='{body}' stroke='{C['text']}' stroke-width='3'/>")
    else:
        out.append(_ct(cx, cy + 20, ICONS.get(ent, "◆"), 56))
    out.append(_ct(cx, cy + r + 34, ent, 26, weight=800))
    return out


def graph_card(export: dict, shot, text, base, graph) -> str:
    """One 1600x900 card: shot text, figures ringed by the graph result, the
    no-memory vs graph verdict per claim, and the State chains that decided."""
    p = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {CARD_W} {CARD_H}' width='{CARD_W}' "
         f"height='{CARD_H}' role='img' aria-label='判定に使ったグラフ'>",
         f"<rect width='{CARD_W}' height='{CARD_H}' fill='{C['bg']}'/>",
         "<defs><marker id='cc-ar' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='8' markerHeight='8' "
         f"orient='auto'><path d='M0 0L10 5L0 10z' fill='{C['muted']}'/></marker></defs>"]
    if not graph:
        p.append(_ct(CARD_W / 2, CARD_H / 2, "チェックすると、判定に使ったグラフがここに出ます", 32, C["muted"]))
        p.append("</svg>")
        return "".join(p)

    # Header: shot and verdict counts.
    counts = {s: sum(f.status == s for f in graph) for s in ("矛盾", "OK", "不明")}
    p.append(_pill(48, 40, 104, 56, C["accent"]))
    p.append(_ct(100, 79, f"S{int(shot)}", 30, C["bg"], 800))
    p.append(_ct(176, 80, _fit(text, 900, 34), 34, weight=700, anchor="start"))
    bx = CARD_W - 48
    for s in ("不明", "OK", "矛盾"):
        if counts[s]:
            w = 150
            bx -= w
            p.append(_pill(bx, 44, w - 12, 48, C["bg"], C[s], 3))
            p.append(_ct(bx + (w - 12) / 2, 77, f"{s} {counts[s]}", 24, C[s], 800))

    # Left: the shot picture and the comparison per claim.
    p.append(f"<rect x='48' y='128' width='520' height='690' rx='28' fill='{C['panel']}'/>")
    p.append(_ct(76, 172, "ショットの絵", 22, C["muted"], 700, "start"))
    by_ent: dict[str, list] = {}
    for f in graph:
        by_ent.setdefault(f.claim.entity, []).append(f)
    ents = list(by_ent.items())[:3]
    for i, (ent, fs) in enumerate(ents):
        cx = 48 + 520 * (i + 0.5) / len(ents)
        p += _figure(cx, 300, ent, fs, r=74 if len(ents) < 3 else 62)
    p.append(_ct(76, 478, "記憶なし　→　グラフ", 22, C["muted"], 700, "start"))
    base_by = {(f.claim.entity, f.claim.attr, f.claim.value): f.status for f in base}
    for j, f in enumerate(graph[:5]):
        y = 528 + 60 * j
        c = f.claim
        who = f"{c.entity}→{c.toward}" if getattr(c, "toward", None) else c.entity
        p.append(_ct(76, y, _fit(f"{who}の{c.attr}「{c.value}」", 250, 22), 22, weight=600, anchor="start"))
        b = base_by.get((c.entity, c.attr, c.value), "不明")
        p.append(_pill(340, y - 30, 92, 40, C["bg"], C[b], 2))
        p.append(_ct(386, y - 3, b, 20, C[b], 700))
        p.append(_ct(452, y - 3, "→", 22, C["muted"]))
        p.append(_pill(474, y - 30, 80, 40, C[f.status]))
        p.append(_ct(514, y - 3, f.status, 20, C["bg"], 800))

    # Right: the subgraph that decided each claim.
    gx, gw = 600, CARD_W - 48 - 600
    p.append(f"<rect x='{gx}' y='128' width='{gw}' height='690' rx='28' fill='{C['panel']}'/>")
    p.append(_ct(gx + 28, 172, "判定に使ったグラフ（Entity → HAS → State → REPLACED_BY）", 22, C["muted"], 700, "start"))
    states = export.get("states", [])
    repl = {(r["src"].get("State"), r["dst"].get("State")): r.get("props", {})
            for r in export.get("rels", []) if r.get("type") == "REPLACED_BY"}
    rows, seen = [], set()
    for f in graph:
        c = f.claim
        key = (c.entity, c.attr, getattr(c, "toward", None))
        if key not in seen:
            seen.add(key)
            chain = sorted((s for s in states if (s["who"], s["attr"], s.get("toward")) == key),
                           key=lambda s: s["from"])
            rows.append((key, chain[-3:], f.status, c.value))
    rows = rows[:3]
    top, avail = 200, 600
    rh = min(230, avail / len(rows))
    ew = 150
    for i, ((ent, attr, toward), chain, status, claimed) in enumerate(rows):
        y = top + rh * i
        mid = y + rh / 2 - 24
        p.append(_pill(gx + 28, mid - 28, ew, 56, C["text"]))
        p.append(_ct(gx + 28 + ew / 2, mid + 9, ent, 26, C["bg"], 800))
        if not chain:
            p.append(_ct(gx + 28 + ew + 40, mid + 9, f"{attr}：記録なし → 不明（推測で埋めない）", 24,
                         C["不明"], 700, "start"))
            continue
        x0 = gx + 28 + ew + 70
        gap = 120
        k = len(chain)
        bw = min(300, (gx + gw - 28 - x0 - gap * (k - 1)) / k)
        bh = min(150, rh - 40)
        prev_right = None
        for j, s in enumerate(chain):
            x = x0 + j * (bw + gap)
            valid = s["from"] <= int(shot) <= s["to"]
            stroke = C[status] if valid else C["line"]
            to = "END" if s["to"] >= 99 else f"S{s['to']}"
            p.append(f"<rect x='{x:.0f}' y='{mid - bh / 2:.0f}' width='{bw:.0f}' height='{bh:.0f}' rx='18' "
                     f"fill='{C['bg']}' stroke='{stroke}' stroke-width='{6 if valid else 2}'/>")
            ty = mid - bh / 2
            p.append(_ct(x + bw / 2, ty + 40, _fit(f"{attr}：{s['value']}", bw - 20, 26), 26,
                         C[status] if valid else C["text"], 800))
            p.append(_ct(x + bw / 2, ty + 72, f"S{s['from']} – {to}", 20, C["accent"], 700))
            p.append(_ct(x + bw / 2, ty + 102, _fit(s.get("cause"), bw - 24, 18), 18, C["muted"]))
            if s.get("toward") and bh > 120:
                p.append(_ct(x + bw / 2, ty + 130, f"TOWARD → {s['toward']}", 18, C["toward"], 700))
            if j == 0:
                p.append(f"<line x1='{gx + 28 + ew:.0f}' y1='{mid:.0f}' x2='{x - 4:.0f}' y2='{mid:.0f}' "
                         f"stroke='{C['muted']}' stroke-width='3' marker-end='url(#cc-ar)'/>")
                p.append(_ct((gx + 28 + ew + x) / 2, mid - 12, "HAS", 16, C["muted"], 700))
            else:
                props = repl.get((chain[j - 1]["id"], s["id"]), {})
                p.append(f"<line x1='{prev_right:.0f}' y1='{mid:.0f}' x2='{x - 4:.0f}' y2='{mid:.0f}' "
                         f"stroke='{C['muted']}' stroke-width='3' marker-end='url(#cc-ar)'/>")
                p.append(_ct((prev_right + x) / 2, mid - 12, "REPLACED_BY", 14, C["muted"], 700))
            if valid:
                p.append(_ct(x + bw / 2, mid + bh / 2 + 30, f"S{int(shot)} の判定：「{claimed}」→ {status}",
                             20, C[status], 800))
            prev_right = x + bw

    # Footer legend.
    lx = 48
    for s, label in (("矛盾", "赤＝記録と矛盾"), ("OK", "緑＝記録どおり"), ("不明", "灰＝記録なし")):
        p.append(f"<circle cx='{lx + 12}' cy='{CARD_H - 42}' r='10' fill='{C[s]}'/>")
        p.append(_ct(lx + 32, CARD_H - 34, label, 20, C["muted"], 600, "start"))
        lx += 230
    p.append(_ct(CARD_W - 48, CARD_H - 34, "Continuity Checker · Relate graph → Neo4j", 20, C["muted"], 600, "end"))
    p.append("</svg>")
    return "".join(p)
