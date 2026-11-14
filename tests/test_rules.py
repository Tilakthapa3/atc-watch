"""Tests for rules.py, including the fixture verdicts and the
no-subprocess safety assertion."""

import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parser
import rules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "data", "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def evaluate_fixture(fixture):
    nas_data = parser.parse_nas_xml(fixture.get("nas_xml"))
    airport_statuses = []
    airport_json = fixture.get("airport_json")
    if isinstance(airport_json, dict):
        parsed = parser.parse_airport_status_json(json.dumps(airport_json))
        if parsed is not None:
            airport_statuses.append(parsed)
    return rules.evaluate(nas_data, airport_statuses, fixture.get("advisories", []))


class TestFixtureVerdicts(unittest.TestCase):
    def test_ground_stop_fixture(self):
        fixture = load_fixture("ground_stop_2026-11-13.json")
        result = evaluate_fixture(fixture)
        self.assertEqual(result["verdict"], "GROUND_STOP_PATTERN")
        self.assertEqual(result["verdict"], fixture["expected"])
        self.assertTrue(
            any(f["rule"] == "ground_stop_keyword" for f in result["findings"])
        )

    def test_normal_day_fixture(self):
        fixture = load_fixture("normal_day.json")
        result = evaluate_fixture(fixture)
        self.assertEqual(result["verdict"], "OK")
        self.assertEqual(result["verdict"], fixture["expected"])
        self.assertEqual(result["findings"], [])

    def test_watch_fixture(self):
        fixture = load_fixture("watch_multi_delay.json")
        result = evaluate_fixture(fixture)
        self.assertEqual(result["verdict"], "WATCH")
        self.assertEqual(result["verdict"], fixture["expected"])
        self.assertTrue(
            any(f["rule"] == "multi_airport_delays" for f in result["findings"])
        )


class TestRules(unittest.TestCase):
    def _advisory(self, text, kind="advisory", airports=()):
        return {
            "text": text,
            "airports_mentioned": list(airports),
            "centers_mentioned": sorted(parser.find_centers(text)),
            "kind": kind,
        }

    def test_ground_stop_keyword_fires(self):
        adv = self._advisory("all airports are ground stopped")
        finding = rules.rule_ground_stop_keyword([adv])
        self.assertIsNotNone(finding)
        self.assertEqual(finding["rule"], "ground_stop_keyword")
        self.assertEqual(finding["severity"], "critical")

    def test_ground_stop_keyword_ignores_delay(self):
        adv = self._advisory("ground delay program at SFO")
        self.assertIsNone(rules.rule_ground_stop_keyword([adv]))

    def test_multi_airport_delays_threshold(self):
        two = [
            self._advisory("x", "ground_delay_programs", ["SAN", "SFO"]),
        ]
        self.assertIsNone(rules.rule_multi_airport_delays(two))
        three = [
            self._advisory(
                "x", "ground_delay_programs", ["SAN", "SFO", "LGA"]
            ),
        ]
        finding = rules.rule_multi_airport_delays(three)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["rule"], "multi_airport_delays")

    def test_multi_airport_delays_ignores_closures(self):
        adv = self._advisory(
            "x", "airport_closures", ["LAX", "SAN", "FLL"]
        )
        self.assertIsNone(rules.rule_multi_airport_delays([adv]))

    def test_multi_airport_delays_counts_airport_status(self):
        adv = self._advisory("x", "ground_delay_programs", ["SAN", "SFO"])
        statuses = [{"code": "LGA", "delayed": True, "delay_minutes": 45,
                     "reason": "wind"}]
        finding = rules.rule_multi_airport_delays([adv], statuses)
        self.assertIsNotNone(finding)

    def test_center_named(self):
        adv = self._advisory("outage at ZDC")
        finding = rules.rule_center_named([adv])
        self.assertIsNotNone(finding)
        self.assertEqual(finding["rule"], "center_named")
        self.assertIn("ZDC", finding["evidence"])

    def test_center_named_none(self):
        adv = self._advisory("wind at SFO")
        self.assertIsNone(rules.rule_center_named([adv]))

    def test_verdict_precedence(self):
        adv = self._advisory(
            "ground stop at ZTL", "ground_stops", ["ATL", "ORD", "LAX"]
        )
        result = rules.evaluate({"advisories": [adv]})
        self.assertEqual(result["verdict"], "GROUND_STOP_PATTERN")

    def test_empty_input_is_ok(self):
        result = rules.evaluate({"advisories": []})
        self.assertEqual(result["verdict"], "OK")
        self.assertEqual(result["findings"], [])


class TestSafety(unittest.TestCase):
    def test_no_subprocess_anywhere(self):
        for path in glob.glob(os.path.join(ROOT, "*.py")):
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
            self.assertNotIn(
                "subprocess", source, "subprocess found in %s" % path
            )


if __name__ == "__main__":
    unittest.main()
