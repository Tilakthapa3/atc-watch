"""Export one ATC Watch check as a JSON snapshot for the dashboard.

Runs a single live check through atc_watch.check_live() and writes
data/status.json, which atc-watch.html reads from the published repo.
The snapshot is the dashboard's only data source.

Usage:
    python3 export_snapshot.py [--output data/status.json]

Exit 0 on a completed run even when some sources fail. When every
source fails, the snapshot still gets written, with verdict UNKNOWN
and every source marked False. The write is atomic: the snapshot is
written to a temporary file in the same directory and renamed over
the old file, so a reader never sees a partial file.

Legal box: same as atc_watch.py — this only reads two public FAA feeds
with plain GET requests. No login, no credentials, no cookies, nothing
is sent to FAA or airline systems. See README.md.

Stdlib only. Python 3.9 compatible.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

import atc_watch

try:
    from zoneinfo import ZoneInfo

    CHICAGO_TZ = ZoneInfo("America/Chicago")
except Exception:
    # Fallback for systems without tz data: Central Standard Time.
    CHICAGO_TZ = timezone(timedelta(hours=-6))

DEFAULT_OUTPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "status.json"
)


def build_snapshot(result, now=None):
    """Build the snapshot dict from one check_live() result.

    `now` is a datetime (UTC-aware) used as the generation stamp; it
    defaults to the current time and exists so tests can pin it.
    """
    now = now or datetime.now(timezone.utc)
    return {
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_ct": now.astimezone(CHICAGO_TZ).isoformat(),
        "verdict": result["verdict"],
        "findings": result["findings"],
        "sources": result["sources"],
        "delayed_airports": result["delayed_airports"],
        "counts": result["counts"],
        "feed_updated": result.get("update_time"),
    }


def write_snapshot(snapshot, output_path):
    """Write the snapshot atomically: temp file + rename.

    A reader of output_path never sees a half-written file. On any
    failure the temporary file is removed and the old snapshot is
    left untouched.
    """
    directory = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".status-", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, output_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main(argv=None):
    arg_parser = argparse.ArgumentParser(
        description="Export one ATC Watch check as data/status.json."
    )
    arg_parser.add_argument(
        "--output",
        metavar="FILE",
        default=DEFAULT_OUTPUT,
        help="snapshot path (default: data/status.json)",
    )
    args = arg_parser.parse_args(argv)
    snapshot = build_snapshot(atc_watch.check_live())
    write_snapshot(snapshot, args.output)
    print("verdict: %s" % snapshot["verdict"])
    print("wrote %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
