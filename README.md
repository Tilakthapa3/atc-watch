# ATC Watch

A read-only monitor on public FAA data that flags the early pattern of
an air-traffic ground stop. It watches the FAA's own public status
feeds and answers one question: does today look like a normal day, a
day to watch, or the start of a ground stop?

Built 2026-11-13, the evening of the FAA's nationwide ground stop,
when a telecommunications outage hit every Air Route Traffic Control
Center and all US departures were halted for about four hours. That
day is fixture number one.

## Legal box

This tool only reads two public FAA feeds with plain GET requests.
There is no login, no credentials, no cookies, no account, and nothing
is sent to FAA or airline systems. Nothing is scanned, probed, or
interfered with. It polls politely (one check = a handful of requests)
and treats any feed failure as "no data", never as a reason to retry
aggressively. It is a student portfolio project, not an operational
system, and it must never be presented as one.

## How it works

```
public FAA feeds  ->  fetcher.py  ->  parser.py  ->  rules.py  ->  verdict
   (plain GET)        (15s timeout)   (XML / JSON)   (3 rules)   OK / WATCH /
                                                            GROUND_STOP_PATTERN
```

Three rules, no more:

1. **ground_stop_keyword** (critical) — advisory text contains
   "ground stop".
2. **multi_airport_delays** (elevated) — 3 or more distinct airports
   delayed at once. Airport closures do not count; they are NOTAM
   restrictions, not delays.
3. **center_named** (elevated) — an ARTCC center (ZTL, ZDC, …) is
   named in an advisory.

Verdict: `GROUND_STOP_PATTERN` if rule 1 fires, `WATCH` if any other
rule fires, `OK` otherwise.

## Run it

```bash
python3 atc_watch.py check
# live check: fetches the feeds, prints a verdict, appends one line
# to incidents.jsonl

python3 atc_watch.py check --sample data/fixtures/ground_stop_2026-11-13.json
# offline: same rules against a saved fixture. Sample runs do not
# write to incidents.jsonl.

python3 export_snapshot.py
# one live check, written as data/status.json for the dashboard.
# Exit 0 even when some sources fail; when every source fails the
# snapshot still gets written with verdict UNKNOWN.

python3 -m unittest discover -s tests -v
# full test suite, offline (network is mocked)
```

Exit codes: 0 = run completed, 2 = bad arguments or every live source
failed to fetch (for `atc_watch.py check` only; the exporter always
exits 0 once it has written a snapshot).

## Step 2 — dashboard

`export_snapshot.py` runs one check and writes `data/status.json`
(atomically: temp file + rename, so a reader never sees a partial
file). The snapshot carries `generated_at_utc`, `generated_at_ct`,
`verdict`, `findings`, `sources` (per-source true/false),
`delayed_airports`, `counts`, and the feed's own `feed_updated` stamp.

`atc-watch.html` is a standalone dashboard page (dark theme, no
external dependencies) for `tilakthapa.com/atc-watch.html`. It fetches
the snapshot from
`https://raw.githubusercontent.com/Tilakthapa3/atc-watch/main/data/status.json`,
renders a verdict banner (OK green / WATCH amber /
GROUND_STOP_PATTERN red / UNKNOWN grey), the findings, delayed
airports, per-source status, and last-updated times, and re-fetches
every 5 minutes. A failed fetch shows a clear "data unavailable"
state instead of stale data.

`.github/workflows/update-status.yml` runs the exporter every 15
minutes on GitHub Actions and commits `data/status.json` only when it
changed. Workflow files cannot be pushed through the GitHub API, so
this file is added to the repo through the GitHub website.

## Sources and verification status

Checked live on 2026-11-14 (UTC). Statuses change; re-check before
trusting any feed.

| Source | Status |
| --- | --- |
| `nasstatus.faa.gov` root page | Reachable (HTTP 200) but it is a React single-page app: the HTML is a shell with no server-rendered data. The data comes from the API endpoints below. |
| `nasstatus.faa.gov/api/airport-status-information` | **Verified working.** HTTP 200, XML document: `<AIRPORT_STATUS_INFORMATION>` with `<Delay_type>` sections (Ground Delay Programs, Airport Closures, …). Each entry carries `ARPT`, `Reason`, `Avg`, `Max`. This is the feed step 1 reads. |
| `nasstatus.faa.gov/api/general-advisories` | HTTP 404 as of 2026-11-14. Advisory text therefore comes only from the airport-status feed and from saved fixtures. |
| `nasstatus.faa.gov/api/restrictions` | HTTP 404 as of 2026-11-14. |
| `nasstatus.faa.gov/api/enroute-events` | HTTP 200, empty JSON array `[]` as of 2026-11-14. Not used in step 1. |
| `services.faa.gov/airport/status/{CODE}?format=json` | **Unverified.** On 2026-11-13 and 2026-11-14 the server completed the TLS handshake and then closed the connection with an empty reply (and earlier returned an empty body). The fetcher treats this as "no data". The parser's expected field shape is the feed's documented public shape, read defensively — it has not been confirmed against a live response. |

## Honest limits

- This watches **public status text**. It cannot see inside FAA
  systems, and a clean verdict here means "nothing in the public
  feeds looks wrong", not "the airspace is fine".
- The ground-stop fixture's `Ground Stops` XML section is modeled on
  the generic `Delay_type` shape observed live; that section itself
  has not been seen live, because no ground stop was active when the
  feed was checked. The fixture's advisory texts are the FAA's real
  wording from 2026-11-13 as quoted in news coverage.
- Three delayed airports is a weak signal on its own: busy weather
  days can trip the watch rule without any outage. The verdict is a
  prompt to look, not a diagnosis.
- Feeds change shape without notice. If a feed stops returning the
  expected XML, the parser returns no advisories and the run reports
  "no data" rather than guessing.

## Files

- `atc_watch.py` — CLI (`check`, `--sample`, `--log`); `check_live()`
  is the reusable check the exporter calls
- `fetcher.py` — the two public feeds, 15s timeout, polite User-Agent
- `parser.py` — FAA airport-status XML and airport-status JSON
- `rules.py` — the three detection rules, the verdict, and
  `delayed_airports()`
- `export_snapshot.py` — one live check as `data/status.json`
  (atomic write, exit 0 even when sources fail)
- `atc-watch.html` — standalone dashboard page for
  `tilakthapa.com/atc-watch.html`
- `.github/workflows/update-status.yml` — refresh the snapshot every
  15 minutes, commit only on change
- `data/status.json` — generated snapshot (do not hand-edit)
- `data/fixtures/` — ground-stop reconstruction (2026-11-13),
  normal day, three-airport watch case
- `tests/` — `test_fetcher.py`, `test_parser.py`, `test_rules.py`,
  `test_exporter.py`

Stdlib only. Python 3.9 compatible. No `subprocess` anywhere (a test
asserts this).
