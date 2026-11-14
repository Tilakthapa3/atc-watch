"""Detection rules for ATC Watch.

Exactly three rules. Each takes parsed feed data and returns a finding
dict {"rule", "severity", "evidence"} or None.

Verdict:
- GROUND_STOP_PATTERN when the ground-stop rule fires
- WATCH when any other rule fires
- OK otherwise

Stdlib only. Python 3.9 compatible.
"""

import re

from parser import find_centers

_GROUND_STOP_RE = re.compile(r"ground stop", re.IGNORECASE)

# Delay_type kinds that count as "an airport is delayed". Closures are
# NOTAM-style restrictions, not delays, so they never count here.
def _is_delay_kind(kind):
    return "delay" in (kind or "") or kind == "ground_stops"


def rule_ground_stop_keyword(advisories):
    """Fire when advisory text contains 'ground stop'."""
    for adv in advisories:
        text = adv.get("text", "")
        if _GROUND_STOP_RE.search(text):
            return {
                "rule": "ground_stop_keyword",
                "severity": "critical",
                "evidence": text[:240],
            }
    return None


def delayed_airports(advisories, airport_statuses=None):
    """Return the sorted list of distinct airports delayed at once."""
    delayed = set()
    for adv in advisories or []:
        if _is_delay_kind(adv.get("kind", "")):
            delayed.update(adv.get("airports_mentioned", []))
    for status in airport_statuses or []:
        if status.get("delayed") and status.get("code"):
            delayed.add(status["code"])
    return sorted(delayed)


def rule_multi_airport_delays(advisories, airport_statuses=None):
    """Fire when 3+ distinct airports are delayed at once."""
    delayed = delayed_airports(advisories, airport_statuses)
    if len(delayed) >= 3:
        return {
            "rule": "multi_airport_delays",
            "severity": "elevated",
            "evidence": "delayed airports: " + ", ".join(delayed),
        }
    return None


def rule_center_named(advisories):
    """Fire when an ARTCC center is named in an advisory."""
    centers = set()
    for adv in advisories or []:
        centers.update(adv.get("centers_mentioned", []))
    if centers:
        return {
            "rule": "center_named",
            "severity": "elevated",
            "evidence": "ARTCC centers mentioned: " + ", ".join(sorted(centers)),
        }
    return None


def evaluate(nas_data, airport_statuses=None, extra_advisories=None):
    """Evaluate all rules over one run's parsed data.

    nas_data is the dict from parser.parse_nas_xml. airport_statuses is
    a list of dicts from parser.parse_airport_status_json.
    extra_advisories is a list of raw advisory text strings (used by
    fixtures and by any future advisory feed).
    """
    advisories = list((nas_data or {}).get("advisories", []))
    for text in extra_advisories or []:
        advisories.append(
            {
                "text": text,
                "airports_mentioned": [],
                "centers_mentioned": sorted(find_centers(text)),
                "kind": "advisory",
            }
        )
    findings = []
    for finding in (
        rule_ground_stop_keyword(advisories),
        rule_multi_airport_delays(advisories, airport_statuses),
        rule_center_named(advisories),
    ):
        if finding is not None:
            findings.append(finding)
    if any(f["rule"] == "ground_stop_keyword" for f in findings):
        verdict = "GROUND_STOP_PATTERN"
    elif findings:
        verdict = "WATCH"
    else:
        verdict = "OK"
    return {"verdict": verdict, "findings": findings}
