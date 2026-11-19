#!/usr/bin/env python3
"""
Computes "what share of article pageviews land past the 3-second mark" from
raw Amplitude event segmentation, and writes data/cost_of_slow.json.

IMPORTANT: this intentionally never writes an absolute pageview count, only
a rounded ratio/percentage -- per the site's privacy rules, raw traffic
volume must not appear on the public page. If you change this script, keep
that rule: round(), don't total().

CORRECTED 2026-11-19 against the live project's taxonomy: web vitals
measurements live on a single event ("[Amplitude] Web Vitals") carrying a
key/value pair per event -- AMPLITUDE_LATENCY_KEY_PROPERTY (default
"performance-mark.key", filtered to the metric name, e.g. "LCP") and
AMPLITUDE_LATENCY_PROPERTY (default "performance-mark.value", the number in
milliseconds). An earlier draft of this script assumed a per-metric property
like "[Amplitude] LCP.value", which does not exist in this project -- that
was never run live and would have failed. See SETUP.md's "Verified" section.

STILL UNVERIFIED: a live segmentation query using this filter shape returned
an all-zero total over the trailing 30 days, and a follow-up query timed out.
That looks like a remaining mismatch between this script's REST API v2 call
shape and the real API (the correction above was verified through a
different, internal API, not this exact endpoint) rather than genuinely zero
traffic. Do not trust this script's output until it's been run manually and
cross-checked against the Amplitude UI directly.

ASSUMPTIONS TO VERIFY:
  * API: Amplitude's Dashboard REST API v2 Event Segmentation
    (https://amplitude.com/docs/apis/analytics/dashboard-rest#event-segmentation),
    GET /api/2/events/segmentation, HTTP Basic Auth (api_key, secret_key).
  * Filter syntax: subprop_type/subprop_key/subprop_op/subprop_value. If
    Amplitude has since moved to a different filter shape, this call will
    fail loudly (see raise_for_status / shape checks below) rather than
    silently return zero -- but an all-zero result that LOOKS successful is
    exactly the failure mode that isn't caught yet. Sanity-check manually.
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
LATENCY_KEY_PROPERTY = os.environ.get("AMPLITUDE_LATENCY_KEY_PROPERTY", "performance-mark.key")
LATENCY_KEY_VALUE = os.environ.get("AMPLITUDE_LATENCY_KEY_VALUE", "LCP")
LATENCY_PROPERTY = os.environ.get("AMPLITUDE_LATENCY_PROPERTY", "performance-mark.value")
THRESHOLD_MS = int(os.environ.get("AMPLITUDE_SLOW_THRESHOLD_MS", "3000"))
LOOKBACK_DAYS = int(os.environ.get("AMPLITUDE_LOOKBACK_DAYS", "30"))

SEGMENTATION_URL = "https://amplitude.com/api/2/events/segmentation"


def date_range():
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def query_total(extra_filters: list) -> int:
    start, end = date_range()
    event_def = {
        "event_type": EVENT_TYPE,
        "filters": [
            {
                "subprop_type": "event",
                "subprop_key": LATENCY_KEY_PROPERTY,
                "subprop_op": "is",
                "subprop_value": [LATENCY_KEY_VALUE],
            }
        ]
        + extra_filters,
    }
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

    total_views = query_total([])
    slow_views = query_total(
        [
            {
                "subprop_type": "event",
                "subprop_key": LATENCY_PROPERTY,
                "subprop_op": "greater",
                "subprop_value": [str(THRESHOLD_MS)],
            }
        ]
    )

    if total_views <= 0:
        raise ValueError(
            "Total view count came back as 0 -- refusing to compute a ratio. "
            "This exact failure was seen during manual verification on "
            "2026-11-19; check the filter shape against the Amplitude UI "
            "before assuming traffic is genuinely zero."
        )

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
