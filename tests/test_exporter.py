"""Tests for export_snapshot.py.

No real network is used: the live check is replaced with fixture
data or with a fabricated all-failed result.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import atc_watch
import export_snapshot
import parser
import rules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "data", "fixtures")

FIXED_NOW = datetime(2026, 11, 14, 3, 18, 24, tzinfo=timezone.utc)

REQUIRED_KEYS = (
    "generated_at_utc",
    "generated_at_ct",
    "verdict",
    "findings",
    "sources",
    "delayed_airports",
    "counts",
)


def fixture_result(name):
    """Run the step-1 check logic over a saved fixture, offline."""
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as fh:
        fixture = json.load(fh)
    nas_data, airport_statuses, extra = atc_watch._build_inputs(
        fixture.get("nas_xml"), [], fixture.get("advisories", [])
    )
    result = rules.evaluate(nas_data, airport_statuses, extra)
    return {
        "verdict": result["verdict"],
        "findings": result["findings"],
        "sources": {"fixture": True},
        "update_time": nas_data.get("update_time"),
        "delayed_airports": rules.delayed_airports(
            nas_data["advisories"], airport_statuses
        ),
        "counts": {
            "advisories": len(nas_data["advisories"]),
            "delayed_airports": len(
                rules.delayed_airports(nas_data["advisories"], airport_statuses)
            ),
            "findings": len(result["findings"]),
        },
        "all_failed": False,
    }


class TestBuildSnapshot(unittest.TestCase):
    def test_ground_stop_fixture_has_all_keys(self):
        snapshot = export_snapshot.build_snapshot(
            fixture_result("ground_stop_2026-11-13.json"), now=FIXED_NOW
        )
        for key in REQUIRED_KEYS:
            self.assertIn(key, snapshot)
        self.assertEqual(snapshot["verdict"], "GROUND_STOP_PATTERN")
        self.assertEqual(
            snapshot["delayed_airports"],
            ["ATL", "DFW", "JFK", "LAX", "ORD", "SFO"],
        )
        self.assertEqual(snapshot["counts"]["delayed_airports"], 6)
        self.assertEqual(snapshot["counts"]["findings"], 2)

    def test_timestamps_are_utc_and_chicago(self):
        snapshot = export_snapshot.build_snapshot(
            fixture_result("normal_day.json"), now=FIXED_NOW
        )
        # 03:18 UTC is 21:18 the previous evening in Chicago (CST, UTC-6).
        self.assertEqual(snapshot["generated_at_utc"], "2026-11-14T03:18:24Z")
        self.assertTrue(
            snapshot["generated_at_ct"].startswith("2026-11-13T21:18:24"),
            snapshot["generated_at_ct"],
        )
        self.assertTrue(
            snapshot["generated_at_ct"].endswith("-06:00"),
            snapshot["generated_at_ct"],
        )

    def test_normal_day_snapshot_is_ok(self):
        # One isolated delay (SFO, wind): below the 3-airport watch
        # threshold, so the verdict is OK but SFO is still listed.
        snapshot = export_snapshot.build_snapshot(
            fixture_result("normal_day.json"), now=FIXED_NOW
        )
        self.assertEqual(snapshot["verdict"], "OK")
        self.assertEqual(snapshot["findings"], [])
        self.assertEqual(snapshot["delayed_airports"], ["SFO"])


class TestWriteSnapshot(unittest.TestCase):
    def test_roundtrip_and_no_temp_files_left(self):
        snapshot = export_snapshot.build_snapshot(
            fixture_result("watch_multi_delay.json"), now=FIXED_NOW
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data", "status.json")
            export_snapshot.write_snapshot(snapshot, path)
            with open(path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            self.assertEqual(loaded, snapshot)
            leftovers = [
                name
                for name in os.listdir(os.path.join(tmp, "data"))
                if name.startswith(".status-")
            ]
            self.assertEqual(leftovers, [])

    def test_failed_write_leaves_old_snapshot(self):
        snapshot = export_snapshot.build_snapshot(
            fixture_result("normal_day.json"), now=FIXED_NOW
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "status.json")
            export_snapshot.write_snapshot(snapshot, path)
            with open(path, "r", encoding="utf-8") as fh:
                before = fh.read()
            with mock.patch(
                "json.dump", side_effect=OSError("disk full")
            ):
                with self.assertRaises(OSError):
                    export_snapshot.write_snapshot(snapshot, path)
            with open(path, "r", encoding="utf-8") as fh:
                after = fh.read()
            self.assertEqual(after, before)
            leftovers = [
                name for name in os.listdir(tmp) if name.startswith(".status-")
            ]
            self.assertEqual(leftovers, [])


class TestMain(unittest.TestCase):
    def test_all_sources_failed_writes_unknown(self):
        failed = {
            "verdict": "UNKNOWN",
            "findings": [],
            "sources": {
                "nasstatus.faa.gov/api/airport-status-information": False,
                "services.faa.gov/airport/status/ATL": False,
            },
            "update_time": None,
            "delayed_airports": [],
            "counts": {"advisories": 0, "delayed_airports": 0, "findings": 0},
            "all_failed": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "status.json")
            with mock.patch(
                "atc_watch.check_live", return_value=failed
            ):
                self.assertEqual(
                    export_snapshot.main(["--output", path]), 0
                )
            with open(path, "r", encoding="utf-8") as fh:
                snapshot = json.load(fh)
            for key in REQUIRED_KEYS:
                self.assertIn(key, snapshot)
            self.assertEqual(snapshot["verdict"], "UNKNOWN")
            self.assertEqual(
                snapshot["sources"],
                {
                    "nasstatus.faa.gov/api/airport-status-information": False,
                    "services.faa.gov/airport/status/ATL": False,
                },
            )

    def test_main_writes_live_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "status.json")
            with mock.patch(
                "atc_watch.check_live",
                return_value=fixture_result("watch_multi_delay.json"),
            ):
                self.assertEqual(
                    export_snapshot.main(["--output", path]), 0
                )
            with open(path, "r", encoding="utf-8") as fh:
                snapshot = json.load(fh)
            self.assertEqual(snapshot["verdict"], "WATCH")
            self.assertEqual(
                snapshot["delayed_airports"], ["LGA", "SAN", "SFO"]
            )


if __name__ == "__main__":
    unittest.main()
