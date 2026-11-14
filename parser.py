"""Parser for ATC Watch.

Turns public FAA feed text into structured advisory dicts. All parsing
is defensive: unknown shapes, empty input, and malformed documents
produce empty results, never an exception.

Stdlib only. Python 3.9 compatible.
"""

import json
import re
import xml.etree.ElementTree as ET

# The 20 FAA Air Route Traffic Control Centers (ARTCCs), by code.
ARTCC_CODES = (
    "ZAB", "ZAU", "ZBW", "ZDC", "ZDV", "ZFW", "ZHU", "ZID", "ZJX", "ZKC",
    "ZLA", "ZLC", "ZMA", "ZME", "ZMP", "ZNY", "ZOA", "ZOB", "ZSE", "ZTL",
)

# Center name -> code. Names only count when followed by "Center"
# (e.g. "Atlanta Center"), so a city name alone never matches.
ARTCC_NAMES = {
    "Albuquerque": "ZAB",
    "Chicago": "ZAU",
    "Boston": "ZBW",
    "Washington": "ZDC",
    "Denver": "ZDV",
    "Fort Worth": "ZFW",
    "Houston": "ZHU",
    "Indianapolis": "ZID",
    "Jacksonville": "ZJX",
    "Kansas City": "ZKC",
    "Los Angeles": "ZLA",
    "Salt Lake City": "ZLC",
    "Miami": "ZMA",
    "Memphis": "ZME",
    "Minneapolis": "ZMP",
    "New York": "ZNY",
    "Oakland": "ZOA",
    "Cleveland": "ZOB",
    "Seattle": "ZSE",
    "Atlanta": "ZTL",
}

_CODE_RE = re.compile(r"\b(Z[A-Z]{2})\b")
_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in ARTCC_NAMES) + r") Center\b"
)


def find_centers(text):
    """Return the set of ARTCC codes mentioned in free text."""
    found = set()
    if not text:
        return found
    for code in _CODE_RE.findall(text):
        if code in ARTCC_CODES:
            found.add(code)
    for name in _NAME_RE.findall(text):
        found.add(ARTCC_NAMES[name])
    return found


def parse_minutes(text):
    """Parse '34 minutes' -> 34, '2 hours and 18 minutes' -> 138.

    Returns None when no duration is present.
    """
    if not text:
        return None
    hours = re.search(r"(\d+)\s*hour", text)
    minutes = re.search(r"(\d+)\s*minute", text)
    if not hours and not minutes:
        return None
    total = 0
    if hours:
        total += int(hours.group(1)) * 60
    if minutes:
        total += int(minutes.group(1))
    return total


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def parse_nas_xml(text):
    """Parse the FAA airport-status-information XML.

    Returns {"update_time": str|None, "advisories": [...]} where each
    advisory is {"text", "airports_mentioned", "centers_mentioned",
    "kind"}. One advisory is produced per <Delay_type> section, and
    the parser is generic over the section names: any Delay_type the
    feed carries (Ground Delay Programs, Airport Closures, Ground
    Stops, ...) is handled the same way. Empty or malformed input
    returns no advisories.
    """
    result = {"update_time": None, "advisories": []}
    if not text or not text.strip():
        return result
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return result
    result["update_time"] = root.findtext("Update_Time")
    for delay_type in root.findall("Delay_type"):
        name = delay_type.findtext("Name") or "unknown"
        parts = []
        airports = set()
        for lst in delay_type:
            if lst.tag == "Name":
                continue
            for entry in lst:
                fields = {}
                for child in entry:
                    fields[child.tag] = (child.text or "").strip()
                arpt = fields.get("ARPT", "")
                reason = fields.get("Reason", "")
                avg = fields.get("Avg", "")
                if arpt:
                    airports.add(arpt)
                bits = " ".join(v for v in (arpt, reason, avg) if v)
                if bits:
                    parts.append(bits)
        joined = (name + ": " + "; ".join(parts)) if parts else name
        result["advisories"].append(
            {
                "text": joined,
                "airports_mentioned": sorted(airports),
                "centers_mentioned": sorted(find_centers(joined)),
                "kind": _slug(name),
            }
        )
    return result


def parse_airport_status_json(text):
    """Parse one airport-status JSON document.

    Returns {"code", "delayed", "delay_minutes", "reason"} or None when
    the input is empty, not JSON, or carries no usable fields. The
    field names below are the feed's documented public shape; the feed
    itself has not returned a live response as of 2026-11-14 (empty
    replies), so every field is read defensively with .get().
    """
    if not text or not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    code = data.get("IATA") or data.get("code") or ""
    status = data.get("status") or {}
    if not isinstance(status, dict):
        status = {}
    reason = status.get("reason") or data.get("reason") or ""
    avg = status.get("avgDelay") or status.get("avg_delay") or ""
    flag = str(data.get("delay", "")).strip().lower()
    delayed = flag in ("true", "yes", "1") or bool(avg)
    if not code and not reason and not avg:
        return None
    return {
        "code": code,
        "delayed": delayed,
        "delay_minutes": parse_minutes(avg) if avg else None,
        "reason": reason,
    }
