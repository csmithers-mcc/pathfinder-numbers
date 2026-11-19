#!/usr/bin/env python3
"""
Pulls the current Core Web Vitals baseline averages from a saved Amplitude
chart and writes them to data/baseline.json.

ASSUMPTIONS TO VERIFY (confirmed against the live project's internal API on
2026-11-19 via the Amplitude MCP connector -- the public REST API v3 response
envelope has NOT been separately confirmed and may differ slightly):
  * AMPLITUDE_CWV_CHART_ID points at the "Performance Marks (web vitals)"
    saved chart (default below is the chart id found during setup:
    https://app.amplitude.com/analytics/mcclatchy/chart/poj9t22s).
  * The chart's response shape matches Amplitude's Dashboard REST API v3
    "chart query" endpoint: GET /api/3/chart/{id}/query
    https://amplitude.com/docs/apis/analytics/dashboard-rest
  * The chart's series/group labels contain the metric names LCP, INP, FCP,
    TTFB, CLS (case-insensitive substring match, see METRIC_KEYS below) --
    confirmed live: the chart's seriesNames come back as exactly
    ["CLS", "FCP", "INP", "LCP", "TTFB"].

This script fails loudly (non-zero exit) rather than writing partial or
guessed data if anything looks off -- a public site should never publish a
silently-wrong number.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

API_KEY = os.environ.get("AMPLITUDE_API_KEY")
SECRET_KEY = os.environ.get("AMPLITUDE_SECRET_KEY")
CHART_ID = os.environ.get("AMPLITUDE_CWV_CHART_ID", "poj9t22s")

# Core Web Vitals thresholds (Google's published "Needs improvement" / "Good"
# cutoffs) -- used only to label status text, not to alter the numbers.
THRESHOLDS = {
    "LCP": {"good": 2500, "needs_improvement": 4000, "unit": "ms"},
    "INP": {"good": 200, "needs_improvement": 500, "unit": "ms"},
    "FCP": {"good": 1800, "needs_improvement": 3000, "unit": "ms"},
    "TTFB": {"good": 800, "needs_improvement": 1800, "unit": "ms"},
    "CLS": {"good": 0.1, "needs_improvement": 0.25, "unit": ""},
}

METRIC_KEYS = ["LCP", "INP", "FCP", "TTFB", "CLS"]


def status_for(metric: str, value: float) -> str:
    t = THRESHOLDS[metric]
    if value <= t["good"]:
        return "Good"
    if value <= t["needs_improvement"]:
        return "Needs improvement"
    return "Poor"


def fetch_chart_data(chart_id: str) -> dict:
    url = f"https://amplitude.com/api/3/chart/{chart_id}/query"
    resp = requests.get(url, auth=(API_KEY, SECRET_KEY), timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_metric_averages(payload: dict) -> dict:
    """
    Expects Amplitude's typical chart-query shape:
      { "data": { "series": [[v1, v2, ...], ...], "seriesLabels": [...] } }
    Falls back to raising a clear error if the shape doesn't match, rather
    than guessing.
    """
    data = payload.get("data")
    if not data or "series" not in data or "seriesLabels" not in data:
        raise ValueError(
            "Unexpected Amplitude response shape -- 'data.series' / "
            "'data.seriesLabels' not found. Inspect the raw response and "
            "update extract_metric_averages()."
        )

    labels = data["seriesLabels"]
    series = data["series"]

    averages = {}
    for metric in METRIC_KEYS:
        idx = next(
            (i for i, label in enumerate(labels) if metric.lower() in str(label).lower()),
            None,
        )
        if idx is None:
            raise ValueError(
                f"Could not find a series matching metric '{metric}' in "
                f"seriesLabels={labels!r}. Update METRIC_KEYS or the chart."
            )
        values = [v for v in series[idx] if isinstance(v, (int, float))]
        if not values:
            raise ValueError(f"No numeric data points for metric '{metric}'.")
        averages[metric] = sum(values) / len(values)

    return averages


def main():
    if not API_KEY or not SECRET_KEY:
        print(
            "AMPLITUDE_API_KEY / AMPLITUDE_SECRET_KEY are not set. "
            "Add them as repo secrets before enabling this workflow.",
            file=sys.stderr,
        )
        sys.exit(1)

    payload = fetch_chart_data(CHART_ID)
    averages = extract_metric_averages(payload)

    out = {"as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    for metric, value in averages.items():
        rounded = round(value, 3) if metric == "CLS" else round(value)
        out[metric] = {
            "value": rounded,
            "status": status_for(metric, value),
            "unit": THRESHOLDS[metric]["unit"],
        }

    out_path = Path(__file__).resolve().parent.parent / "data" / "baseline.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
