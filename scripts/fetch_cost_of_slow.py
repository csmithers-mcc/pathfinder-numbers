#!/usr/bin/env python3
"""
Computes "what share of article pageviews land past the 3-second mark" from
raw Amplitude event segmentation, and writes data/cost_of_slow.json.

IMPORTANT: this intentionally never writes an absolute pageview count, only
a rounded ratio/percentage -- per the site's privacy rules, raw traffic
volume must not appear on the public page. If you change this script, keep
that rule: round(), don't total().

ASSUMPTIONS TO VERIFY (untested from here -- I don't have the secret key to
run this live. Confirm against a manual query in the Amplitude UI before
trusting the automated output):
  * Event: "[Amplitude] Web Vitals" is the event that carries page-load
    timing. Property "[Amplitude] LCP.value" (Largest Contentful Paint, in
    milliseconds) is used as the "how long did this view take" signal --
    chosen because it's the metric closest to the "3-second load mark"
    framing already cited from the Think with Google benchmark.
  * API: Amplitude's Dashboard REST API v2 Event Segmentation
    (https://amplitude.com/docs/apis/analytics/dashboard-rest#event-segmentation),
    GET /api/2/events/segmentation, HTTP Basic Auth (api_key, secret_key).
  * Filter syntax: subprop_type/subprop_key/subprop_op/subprop_value. If
    Amplitude has since moved to a different filter shape, this call will
    fail loudly (see raise_for_status / shape checks below) rather than
    silently return zero.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API_KEY = os.environ.get("AMPLITUDE_API_KEY")
SECRET_KEY = os.environ.get("AMPLITUDE_SECRET_KEY")
EVENT_TYPE = os.environ.get("AMPLITUDE_WEB_VITALS_EVENT", "[Amplitude] Web Vitals")
LATENCY_PROPERTY = os.environ.get("AMPLITUDE_LATENCY_PROPERTY", "[Amplitude] LCP.value")
THRESHOLD_MS = int(os.environ.get("AMPLITUDE_SLOW_THRESHOLD_MS", "3000"))
LOOKBACK_DAYS = int(os.environ.get("AMPLITUDE_LOOKBACK_DAYS", "30"))

SEGMENTATION_URL = "https://amplitude.com/api/2/events/segmentation"


def date_range():
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def query_total(event_def: dict) -> int:
    start, end = date_range()
    params = {
        "e": json.dumps([event_def]),
        "start": start,
        "end": end,
        "m": "totals",
    }
    resp = requests.get(SEGMENTATION_URL, params=params, auth=(API_KEY, SECRET_KEY), timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    data = payload.get("data")
    if not data or "series" not in data:
        raise ValueError(
            f"Unexpected segmentation response shape: {payload!r}. "
            "Check AMPLITUDE_WEB_VITALS_EVENT / filter syntax against "
            "current Amplitude API docs."
        )
    series = data["series"]
    if not series or not series[0]:
        raise ValueError(f"Segmentation query returned no data points: {payload!r}")

    return sum(v for v in series[0] if isinstance(v, (int, float)))


def main():
    if not API_KEY or not SECRET_KEY:
        print(
            "AMPLITUDE_API_KEY / AMPLITUDE_SECRET_KEY are not set. "
            "Add them as repo secrets before enabling this workflow.",
            file=sys.stderr,
        )
        sys.exit(1)

    total_views = query_total({"event_type": EVENT_TYPE})
    slow_views = query_total(
        {
            "event_type": EVENT_TYPE,
            "filters": [
                {
                    "subprop_type": "event",
                    "subprop_key": LATENCY_PROPERTY,
                    "subprop_op": "greater",
                    "subprop_value": [str(THRESHOLD_MS)],
                }
            ],
        }
    )

    if total_views <= 0:
        raise ValueError("Total view count came back as 0 -- refusing to compute a ratio.")

    share = slow_views / total_views

    # Express as a rounded "~1 in N" ratio rather than a percentage with
    # false precision, and NEVER include the raw counts in the output file.
    n = round(1 / share) if share > 0 else None

    out = {
        "share_percent_rounded": round(share * 100),
        "ratio_label": f"~1 in {n}" if n else "< 1 in 100",
        "threshold_ms": THRESHOLD_MS,
        "lookback_days": LOOKBACK_DAYS,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    out_path = Path(__file__).resolve().parent.parent / "data" / "cost_of_slow.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {out_path}: {out}")


if __name__ == "__main__":
    main()
