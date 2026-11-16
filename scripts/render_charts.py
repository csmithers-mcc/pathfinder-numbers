#!/usr/bin/env python3
"""
Reads data/baseline.json and data/cost_of_slow.json (written by
fetch_baseline.py / fetch_cost_of_slow.py) and generates fresh
assets/chart1.svg + assets/chart5.svg (and their PNGs) from scratch,
programmatically, rather than patching the original hand-authored SVGs.

This intentionally regenerates the whole chart rather than find/replacing
numbers inside the old file: bar widths, cutoff-line positions and status
colors all depend on the new values, so a from-scratch render is more
robust for a daily automated job than string substitution would be.

Colors match the rest of the site (see style.css custom properties).
"""
import json
import sys
from pathlib import Path

import cairosvg

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"

BG = "#f3f1ea"
INK = "#1a1d1f"
INK_SOFT = "#52585e"
GOOD = "#1f6f4e"
WARN = "#b4791c"
BAD = "#b0392a"

STATUS_COLOR = {"Good": GOOD, "Needs improvement": WARN, "Poor": BAD}

# Per-metric scale max (ms, or unitless for CLS) used only to size the bar
# -- chosen so each metric's "Needs improvement" cutoff sits comfortably
# inside the bar, not to reproduce any specific prior pixel layout.
SCALE_MAX = {
    "LCP": 5000,
    "INP": 700,
    "FCP": 3800,
    "TTFB": 2200,
    "CLS": 0.3,
}

GOOD_CUTOFF = {"LCP": 2500, "INP": 200, "FCP": 1800, "TTFB": 800, "CLS": 0.1}

METRIC_ORDER = ["LCP", "INP", "FCP", "TTFB", "CLS"]


def render_baseline_svg(baseline: dict, as_of: str) -> str:
    bar_x = 90
    bar_w_max = 620
    rows = []
    for i, metric in enumerate(METRIC_ORDER):
        m = baseline[metric]
        value = m["value"]
        status = m["status"]
        unit = m["unit"]
        color = STATUS_COLOR.get(status, INK_SOFT)
        scale_max = SCALE_MAX[metric]
        width = max(2, min(bar_w_max, round((value / scale_max) * bar_w_max)))
        cutoff_x = bar_x + round((GOOD_CUTOFF[metric] / scale_max) * bar_w_max)
        value_label = f"{value:g}{unit} avg" if unit else f"{value:g} avg (scale 0-{scale_max})"
        y = 30 + i * 55
        rows.append(f"""
 <g transform="translate(0,{y})">
 <text x="0" y="16" fill="{INK}" font-size="13" font-weight="600">{metric}</text>
 <rect x="{bar_x}" y="2" width="{bar_w_max}" height="20" fill="#d8d3c4"/>
 <rect x="{bar_x}" y="2" width="{width}" height="20" fill="{color}"/>
 <line x1="{cutoff_x}" y1="-4" x2="{cutoff_x}" y2="28" stroke="{INK}" stroke-dasharray="2,2"/>
 <text x="{bar_x}" y="40" font-size="11" fill="{INK_SOFT}">{value_label}</text>
 <text x="700" y="16" font-size="11" fill="{color}" font-weight="600">{status}</text>
 </g>""")

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 360" width="100%" role="img" aria-label="Core Web Vitals baseline chart">
<rect x="0" y="0" width="900" height="360" fill="{BG}"/>
<g transform="translate(20,20)">
 <g font-size="11" fill="{INK_SOFT}">
 <text x="{bar_x}" y="16">0</text>
 <text x="710" y="16">Dashed line = Google's "good" cutoff</text>
 </g>
{"".join(rows)}
 <text x="0" y="330" font-size="10" fill="{INK_SOFT}">Data as of {as_of} &#8226; refreshed daily</text>
</g>
</svg>
'''


def render_cost_of_slow_svg(cost: dict) -> str:
    ratio_label = cost["ratio_label"]
    threshold_s = cost["threshold_ms"] / 1000
    as_of = cost["as_of"]
    lookback = cost["lookback_days"]

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 360" width="100%" role="img" aria-label="Cost of slow: share of article views past the {threshold_s:g}-second mark">
<rect x="0" y="0" width="900" height="360" fill="{BG}"/>
<g transform="translate(48,56)">
 <g font-size="13" fill="{INK_SOFT}" letter-spacing="0.5">
  <text x="0" y="18">COST OF SLOW</text>
 </g>
 <g>
  <text x="0" y="130" font-size="80" font-weight="700" fill="{BAD}">{ratio_label}</text>
 </g>
 <g font-size="22" fill="{INK}" font-weight="600">
  <text x="0" y="168">article views land past the {threshold_s:g}-second mark</text>
 </g>
 <g font-size="15" fill="{INK_SOFT}">
  <text x="0" y="200">A meaningful share of our monthly article traffic currently loads past that threshold.</text>
  <text x="0" y="224">Industry data cited above puts abandonment above 24% past the 3-second load mark.</text>
  <text x="0" y="256" font-style="italic">Scaling a cited benchmark to our real traffic, not a new measurement of Pathfinder itself.</text>
  <text x="0" y="288" font-size="11">Data as of {as_of} &#8226; trailing {lookback} days &#8226; refreshed daily</text>
 </g>
</g>
</svg>
'''


def main():
    baseline_path = DATA_DIR / "baseline.json"
    cost_path = DATA_DIR / "cost_of_slow.json"

    if not baseline_path.exists() or not cost_path.exists():
        print(
            "Missing data/baseline.json or data/cost_of_slow.json -- run the "
            "fetch scripts first.",
            file=sys.stderr,
        )
        sys.exit(1)

    baseline = json.loads(baseline_path.read_text())
    cost = json.loads(cost_path.read_text())

    missing = [m for m in METRIC_ORDER if m not in baseline]
    if missing:
        print(f"baseline.json is missing metrics: {missing}", file=sys.stderr)
        sys.exit(1)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    chart1_svg = render_baseline_svg(baseline, as_of=cost.get("as_of", ""))
    chart5_svg = render_cost_of_slow_svg(cost)

    (ASSETS_DIR / "chart1.svg").write_text(chart1_svg)
    (ASSETS_DIR / "chart5.svg").write_text(chart5_svg)

    cairosvg.svg2png(url=str(ASSETS_DIR / "chart1.svg"), write_to=str(ASSETS_DIR / "chart1.png"), scale=2)
    cairosvg.svg2png(url=str(ASSETS_DIR / "chart5.svg"), write_to=str(ASSETS_DIR / "chart5.png"), scale=2)

    print("Re-rendered chart1 and chart5 (svg + png).")


if __name__ == "__main__":
    main()
