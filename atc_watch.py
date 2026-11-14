"""ATC Watch — read-only monitor on public FAA data.

Flags the early pattern of an air-traffic ground stop: a ground-stop
advisory, several airports delayed at once, or an air traffic control
center named in an advisory.

Usage:
    python3 atc_watch.py check
        Fetch the live public feeds, evaluate the rules, print a
        verdict (OK / WATCH / GROUND_STOP_PATTERN) and append the
        findings to incidents.jsonl.
    python3 atc_watch.py check --sample data/fixtures/<name>.json
        Run the same rules against a saved fixture, offline. Sample
        runs do not write to incidents.jsonl.

Exit codes: 0 = run completed, 2 = bad arguments or every live source
failed to fetch.

Legal box: this tool only reads two public FAA feeds with plain GET
requests. No login, no credentials, no cookies, nothing is transmitted
to FAA or airline systems, and nothing is scanned. See README.md.

Stdlib only. Python 3.9 compatible.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import fetcher
import parser
import rules

WATCHLIST = ["ATL", "ORD", "LAX", "DFW", "JFK"]

DEFAULT_LOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "incidents.jsonl"
)


def _build_inputs(nas_text, airport_texts, extra_advisories):
    """Turn raw feed text into the structures rules.evaluate expects."""
    nas_data = (
        parser.parse_nas_xml(nas_text)
        if nas_text
        else {"update_time": None, "advisories": []}
    )
    airport_statuses = []
    for text in airport_texts or []:
        parsed = parser.parse_airport_status_json(text) if text else None
        if parsed is not None:
            airport_statuses.append(parsed)
    return nas_data, airport_statuses, list(extra_advisories or [])


def _print_report(result, sources, update_time):
    print("verdict: %s" % result["verdict"])
    if update_time:
        print("feed updated: %s" % update_time)
    for name, ok in sources:
        print("source %s: %s" % (name, "ok" if ok else "no data"))
    if not result["findings"]:
        print("no findings")
        return
    for finding in result["findings"]:
        print(
            "- [%s] %s: %s"
            % (finding["severity"], finding["rule"], finding["evidence"])
        )


def _append_incident(log_path, result, sources):
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "verdict": result["verdict"],
        "findings": result["findings"],
        "sources": {name: ok for name, ok in sources},
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def check_live():
    """Fetch the live feeds and evaluate the rules once.

    Returns a dict with verdict, findings, sources (per-source True /
    False), update_time (the feed's own update stamp), delayed_airports,
    counts, and all_failed. When every source fails to fetch, the
    verdict is "UNKNOWN" and every source is False; nothing is raised.
    Exporters and dashboards use this; run_live() below adds the
    human-readable report and the incidents log.
    """
    sources = []
    nas_text = fetcher.fetch_nas_status()
    sources.append(
        ("nasstatus.faa.gov/api/airport-status-information", nas_text is not None)
    )
    airport_texts = []
    for code in WATCHLIST:
        text = fetcher.fetch_airport_status(code)
        sources.append(
            ("services.faa.gov/airport/status/%s" % code, text is not None)
        )
        if text:
            airport_texts.append(text)
    if nas_text is None and not airport_texts:
        return {
            "verdict": "UNKNOWN",
            "findings": [],
            "sources": {name: ok for name, ok in sources},
            "update_time": None,
            "delayed_airports": [],
            "counts": {"advisories": 0, "delayed_airports": 0, "findings": 0},
            "all_failed": True,
        }
    nas_data, airport_statuses, extra = _build_inputs(
        nas_text, airport_texts, []
    )
    result = rules.evaluate(nas_data, airport_statuses, extra)
    delayed = rules.delayed_airports(nas_data["advisories"], airport_statuses)
    return {
        "verdict": result["verdict"],
        "findings": result["findings"],
        "sources": {name: ok for name, ok in sources},
        "update_time": nas_data.get("update_time"),
        "delayed_airports": delayed,
        "counts": {
            "advisories": len(nas_data["advisories"]),
            "delayed_airports": len(delayed),
            "findings": len(result["findings"]),
        },
        "all_failed": False,
    }


def run_live(log_path):
    """Fetch the live feeds, evaluate, report, log. Returns exit code."""
    result = check_live()
    if result["all_failed"]:
        print(
            "error: every source failed to fetch; no data to evaluate",
            file=sys.stderr,
        )
        return 2
    sources = list(result["sources"].items())
    _print_report(
        {"verdict": result["verdict"], "findings": result["findings"]},
        sources,
        result["update_time"],
    )
    _append_incident(
        log_path,
        {"verdict": result["verdict"], "findings": result["findings"]},
        sources,
    )
    print("logged to %s" % log_path)
    return 0


def run_sample(fixture_path):
    """Evaluate one saved fixture, offline. Returns exit code."""
    try:
        with open(fixture_path, "r", encoding="utf-8") as fh:
            fixture = json.load(fh)
    except (OSError, ValueError) as exc:
        print("error: cannot read fixture %s: %s" % (fixture_path, exc),
              file=sys.stderr)
        return 2
    airport_texts = []
    airport_json = fixture.get("airport_json")
    if isinstance(airport_json, dict):
        airport_texts.append(json.dumps(airport_json))
    elif isinstance(airport_json, str) and airport_json.strip():
        airport_texts.append(airport_json)
    nas_data, airport_statuses, extra = _build_inputs(
        fixture.get("nas_xml"), airport_texts, fixture.get("advisories", [])
    )
    result = rules.evaluate(nas_data, airport_statuses, extra)
    print("fixture: %s" % fixture.get("name", fixture_path))
    print("expected: %s" % fixture.get("expected", "unknown"))
    _print_report(result, [("fixture", True)], nas_data.get("update_time"))
    return 0


def main(argv=None):
    arg_parser = argparse.ArgumentParser(
        description="ATC Watch: read-only monitor on public FAA data."
    )
    sub = arg_parser.add_subparsers(dest="command")
    check = sub.add_parser("check", help="run one check (live or sample)")
    check.add_argument(
        "--sample",
        metavar="FIXTURE",
        help="run against a saved fixture file instead of live feeds",
    )
    check.add_argument(
        "--log",
        metavar="FILE",
        default=DEFAULT_LOG,
        help="incidents log for live runs (default: incidents.jsonl)",
    )
    args = arg_parser.parse_args(argv)
    if args.command != "check":
        arg_parser.print_usage(sys.stderr)
        return 2
    if args.sample:
        return run_sample(args.sample)
    return run_live(args.log)


if __name__ == "__main__":
    sys.exit(main())
