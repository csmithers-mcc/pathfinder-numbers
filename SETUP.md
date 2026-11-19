# Setup: daily data refresh

This repo has a scheduled GitHub Action (`.github/workflows/refresh-data.yml`)
that pulls fresh data from Amplitude once a day and opens a pull request with
the updated charts. Nothing auto-merges -- someone glances at the PR and
merges it, same as any other change.

## What refreshes, and what doesn't

| Chart | Refreshes daily? | Why |
|---|---|---|
| chart1 (baseline Core Web Vitals) | Yes | Pulled live from Amplitude |
| chart5 (cost of slow, "~1 in 4") | Yes | Computed live from Amplitude |
| chart2 (staging vs. production lab comparison) | No | It was a one-off browser timing test. The staging URL is internal/VPN-only, so a public GitHub-hosted runner can't reach it to re-run the comparison. It stays a manual, dated snapshot (see its caption on the page) -- re-run it by hand and update the image/caption when you have a new comparison worth publishing. |
| chart3 (industry case studies), chart4 (Netzwelt callout) | No | These are fixed external citations (other publishers' numbers), not our own metrics. |
| compare-before / compare-after (the "same site" wireframes) | No | Hand-authored illustrative wireframes, not pulled from any data source. Update by hand if the real layouts change enough to need it. |

## Required repo secrets

Settings &rarr; Secrets and variables &rarr; Actions &rarr; **Secrets**:

- `AMPLITUDE_API_KEY` -- from your Amplitude project's API Keys settings page.
- `AMPLITUDE_SECRET_KEY` -- same page, the paired secret key. Dashboard REST
  API calls use these as HTTP Basic Auth (api_key as username, secret_key as
  password).

Treat these like any other credential: don't paste them into issues, PR
descriptions, or commit messages. GitHub masks secret values in logs
automatically, but double-check an action's output before sharing it anyway.

## Optional repo variables

Settings &rarr; Secrets and variables &rarr; Actions &rarr; **Variables**
(not secret, but configurable without touching the workflow file):

- `AMPLITUDE_CWV_CHART_ID` -- defaults to `poj9t22s` (the "Performance Marks
  (web vitals)" saved chart). Change this if that chart is renamed, cloned,
  or replaced.
- `AMPLITUDE_WEB_VITALS_EVENT` -- defaults to `[Amplitude] Web Vitals`.
- `AMPLITUDE_LATENCY_PROPERTY` -- defaults to `performance-mark.value`
  (milliseconds), read together with `AMPLITUDE_LATENCY_KEY_PROPERTY`
  (defaults to `performance-mark.key`, filtered to `LCP`). Confirmed live
  against the project's taxonomy on 2026-11-19 -- see "Verified" below.

## Verified against the live project (2026-11-19)

Unlike the original draft of this pipeline, these points have now actually
been checked against the real Amplitude project, not just assumed:

- The event is genuinely `[Amplitude] Web Vitals`, and web vitals measurements
  live on a single key/value pair per event -- `performance-mark.key` (the
  metric name: `LCP`, `FCP`, `INP`, `TTFB`, `CLS`, plus some internal
  lifecycle marks) and `performance-mark.value` (the number). **This is a
  correction**: earlier drafts of `fetch_cost_of_slow.py` assumed a
  per-metric property like `[Amplitude] LCP.value`, which doesn't exist --
  `fetch_cost_of_slow.py` now filters on `performance-mark.key = "LCP"` and
  reads `performance-mark.value`, matching the real schema.
- `fetch_baseline.py`'s live pull from chart `poj9t22s` works end to end --
  `data/baseline.json`'s `as_of` date reflects the day it last pulled
  successfully (2026-11-19 as of this note).
- `fetch_cost_of_slow.py`'s live pull is **still unverified**. A segmentation
  query filtered to this event + key returned an all-zero total over the
  trailing 30 days, and a follow-up query timed out -- that smells like a
  remaining mismatch (filter shape, or the REST API's exact parameter names
  differing from the internal API used to verify the property names above),
  not genuinely zero traffic. `data/cost_of_slow.json` still holds its last
  known-good value (2026-11-16) rather than a fabricated new one. Don't trust
  this script's output until someone runs it manually and sanity-checks the
  numbers against the Amplitude UI directly.

## Things to verify before trusting this fully

Before you turn on the schedule, run the workflow manually once (Actions tab
&rarr; "Daily data refresh" &rarr; "Run workflow") and check the opened PR's
diff carefully:

1. **`fetch_baseline.py`** assumes Amplitude's chart-query response has the
   shape `{"data": {"series": [...], "seriesLabels": [...]}}` and that the
   series labels contain the strings "LCP", "INP", "FCP", "TTFB", "CLS". This
   has been confirmed against the live chart's internal API shape; the public
   REST API v3 response envelope may still differ slightly -- if the script
   raises a shape error, inspect the raw response and adjust
   `extract_metric_averages()`.
2. **`fetch_cost_of_slow.py`** now filters on the verified
   `performance-mark.key` / `performance-mark.value` properties, but the
   segmentation query itself has not been confirmed to return non-zero data
   through the public REST API -- see "Verified" above. Treat its output as
   unverified until a manual run produces numbers that match the Amplitude UI.
3. Both scripts refuse to write output (non-zero exit) on anything that
   looks wrong, specifically so a bad run can't quietly publish an incorrect
   number to a public page. If the workflow fails, nothing gets committed --
   check the Action's logs.
4. The workflow uses [`peter-evans/create-pull-request`](https://github.com/peter-evans/create-pull-request)
   to open the PR. First run may need you to approve the action if your org
   restricts third-party actions.

## Privacy rules this pipeline must keep

This repo is public. The automated scripts are written to only ever emit
rounded ratios/percentages and metric averages -- never raw pageview counts
or other absolute traffic figures. If you modify `fetch_cost_of_slow.py` or
`fetch_baseline.py`, keep that rule: round(), don't total().
