"""Render console snapshots (board, monitor, launcher) as an SVG terminal window.

The lines come from the tool's own views (`board_lines`, `event_lines`) with their ANSI colours, so the
picture is what the console really shows. One frame gives a still image; several give an animated loop
(CSS, which GitHub plays in a README) that falls back to a single frame for people who prefer less motion.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

ANSI = re.compile(r"\x1b\[(\d+)m")
FG = {"32": "#73c991", "31": "#f48771", "33": "#e2c08d", "36": "#75beff", "2": "#8b8b8b", "1": "#ffffff"}
TEXT = "#cccccc"
BOLD = ' font-weight="bold"'
FONT = "Cascadia Mono, Consolas, 'DejaVu Sans Mono', Menlo, monospace"

WIDTH, TAB_BAR, BOARD_LINES, CAPTION = 1320, 38, 34, 46
LINE, SIZE, PAD = 17, 13, 12
PANES_H = BOARD_LINES * LINE + 2 * PAD
HEIGHT = TAB_BAR + PANES_H + CAPTION
SPLIT = WIDTH // 2
RIGHT_H = PANES_H // 2


def spans(line: str) -> list[tuple[str, str, bool]]:
    out, color, bold, pos = [], TEXT, False, 0
    for match in ANSI.finditer(line):
        if match.start() > pos:
            out.append((line[pos : match.start()], color, bold))
        code = match.group(1)
        if code == "0":
            color, bold = TEXT, False
        elif code == "1":
            bold, color = True, FG["1"]
        else:
            color = FG.get(code, TEXT)
        pos = match.end()
    if pos < len(line):
        out.append((line[pos:], color, bold))
    return out


def text_block(lines: list[str], x: int, y: int) -> str:
    parts = []
    for i, line in enumerate(lines):
        tspans = "".join(
            f'<tspan fill="{color}"{BOLD if bold else ""}>{escape(text)}</tspan>' for text, color, bold in spans(line)
        )
        parts.append(f'<text x="{x}" y="{y + (i + 1) * LINE}" xml:space="preserve">{tspans}</text>')
    return "\n".join(parts)


def frame_svg(frame: dict) -> str:
    tabs, x = [], 10
    for i, title in enumerate(frame["tabs"]):
        w = 26 + 7 * len(title)
        fill, ink = ("#2b2b2b", "#ffffff") if i == 0 else ("#1c1c1c", "#9d9d9d")
        tabs.append(
            f'<rect x="{x}" y="6" width="{w}" height="{TAB_BAR - 6}" rx="6" fill="{fill}"/>'
            f'<text x="{x + 13}" y="{TAB_BAR - 11}" fill="{ink}">{escape(title)}</text>'
        )
        x += w + 4
    top = TAB_BAR
    return f"""
<rect x="0" y="{top}" width="{WIDTH}" height="{PANES_H}" fill="#0c0c0c"/>
{"".join(tabs)}
<line x1="{SPLIT}" y1="{top}" x2="{SPLIT}" y2="{top + PANES_H}" stroke="#3c3c3c" stroke-width="2"/>
<line x1="{SPLIT}" y1="{top + RIGHT_H}" x2="{WIDTH}" y2="{top + RIGHT_H}" stroke="#3c3c3c" stroke-width="2"/>
<rect x="{SPLIT + 1}" y="{top + RIGHT_H + 1}" width="{WIDTH - SPLIT - 2}" height="{PANES_H - RIGHT_H - 2}"
      fill="none" stroke="#0078d4" stroke-width="2"/>
{text_block(frame["board"], PAD, top + PAD - 4)}
{text_block(frame["monitor"], SPLIT + PAD, top + PAD - 4)}
{text_block(frame["launcher"], SPLIT + PAD, top + RIGHT_H + PAD - 4)}
<rect x="0" y="{top + PANES_H}" width="{WIDTH}" height="{CAPTION}" fill="#1f1f1f"/>
<text x="{PAD + 4}" y="{top + PANES_H + 29}" fill="#ffffff" font-size="15" font-weight="bold">{escape(frame["caption"])}</text>
<text x="{WIDTH - PAD - 4}" y="{top + PANES_H + 29}" fill="#8b8b8b" font-size="12" text-anchor="end">simulated session: real board and events from examples/simulate.py</text>
"""


def render(frames: list[dict], seconds: float = 4.5) -> str:
    """One frame: a still. Several: an animated loop."""
    animated = len(frames) > 1
    total = seconds * len(frames)
    share = 100 / len(frames)
    style = ""
    if animated:
        delays = "".join(f".f{i}{{animation-delay:{i * seconds}s}}" for i in range(len(frames)))
        style = (
            f"<style>.frame{{opacity:0;animation:cycle {total}s infinite}}"
            f"@keyframes cycle{{0%{{opacity:1}}{share - 0.5:.2f}%{{opacity:1}}{share:.2f}%{{opacity:0}}100%{{opacity:0}}}}"
            f"{delays}"
            "@media (prefers-reduced-motion: reduce){.frame{animation:none}.f1{opacity:1}}</style>"
        )
    groups = "\n".join(f'<g class="frame f{i}">{frame_svg(frame)}</g>' for i, frame in enumerate(frames))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}"
     font-family="{FONT}" font-size="{SIZE}" role="img"
     aria-label="The agents-collaboration console: the live board, the event monitor and the agent launcher">
<rect width="{WIDTH}" height="{HEIGHT}" rx="10" fill="#1c1c1c"/>
{style}
{groups}
</svg>
"""
