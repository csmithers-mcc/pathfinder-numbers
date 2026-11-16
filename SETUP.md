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
- `AMPLITUDE_LATENCY_PROPERTY` -- defaults to `[Amplitude] LCP.value`
  (milliseconds). This is the property the cost-of-slow script thresholds
  at 3 seconds.

## Things to verify before trusting this fully (I could not test live)

I don't have the Amplitude secret key, so none of this has run against the
real account. Before you turn on the schedule, run the workflow manually
once (Actions tab &rarr; "Daily data refresh" &rarr; "Run workflow") and
check the opened PR's diff carefully:

1. **`fetch_baseline.py`** assumes Amplitude's chart-query response has the
   shape `{"data": {"series": [...], "seriesLabels": [...]}}` and that the
   series labels contain the strings "LCP", "INP", "FCP", "TTFB", "CLS". If
   the saved chart's series are named differently, the script will raise a
   clear error (not silently publish a wrong number) -- fix the label match
   in `extract_metric_averages()`.
2. **`fetch_cost_of_slow.py`** assumes the Dashboard REST API v2 Event
   Segmentation endpoint and its `subprop_type`/`subprop_key`/`subprop_op`/
   `subprop_value` filter syntax are still current. If Amplitude has changed
   this, the script will fail loudly rather than return a guessed ratio.
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
