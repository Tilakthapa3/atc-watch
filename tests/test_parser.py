"""Tests for parser.py."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parser

LIVE_SHAPED_XML = """<AIRPORT_STATUS_INFORMATION>
<Update_Time>Sat Nov 14 03:15:12 2026 GMT</Update_Time>
<Delay_type><Name>Ground Delay Programs</Name>
<Ground_Delay_List>
<Ground_Delay><ARPT>SAN</ARPT><Reason>airport volume</Reason>
<Avg>34 minutes</Avg><Max>1 hour and 21 minutes</Max></Ground_Delay>
<Ground_Delay><ARPT>SFO</ARPT><Reason>wind</Reason>
<Avg>2 hours and 18 minutes</Avg><Max>11 hours and 30 minutes</Max></Ground_Delay>
</Ground_Delay_List></Delay_type>
<Delay_type><Name>Airport Closures</Name>
<Airport_Closure_List>
<Airport><ARPT>LAX</ARPT><Reason>!LAX 05/277 LAX AD AP CLSD</Reason>
<Start>May 27 at 18:26 UTC.</Start><Reopen>May 28 at 16:00 UTC.</Reopen></Airport>
</Airport_Closure_List></Delay_type>
</AIRPORT_STATUS_INFORMATION>"""


class TestParseNasXml(unittest.TestCase):
    def test_live_shaped_xml(self):
        data = parser.parse_nas_xml(LIVE_SHAPED_XML)
        self.assertEqual(data["update_time"], "Sat Nov 14 03:15:12 2026 GMT")
        self.assertEqual(len(data["advisories"]), 2)
        gdp = data["advisories"][0]
        self.assertEqual(gdp["kind"], "ground_delay_programs")
        self.assertEqual(gdp["airports_mentioned"], ["SAN", "SFO"])
        self.assertIn("SAN", gdp["text"])
        self.assertIn("34 minutes", gdp["text"])
        closure = data["advisories"][1]
        self.assertEqual(closure["kind"], "airport_closures")
        self.assertEqual(closure["airports_mentioned"], ["LAX"])

    def test_empty_and_bad_input(self):
        self.assertEqual(
            parser.parse_nas_xml(""),
            {"update_time": None, "advisories": []},
        )
        self.assertEqual(
            parser.parse_nas_xml(None),
            {"update_time": None, "advisories": []},
        )
        self.assertEqual(
            parser.parse_nas_xml("<html><body>not xml"),
            {"update_time": None, "advisories": []},
        )
        self.assertEqual(
            parser.parse_nas_xml("<html>Website Unavailable</html>"),
            {"update_time": None, "advisories": []},
        )


class TestParseMinutes(unittest.TestCase):
    def test_minutes_only(self):
        self.assertEqual(parser.parse_minutes("34 minutes"), 34)

    def test_hours_and_minutes(self):
        self.assertEqual(parser.parse_minutes("2 hours and 18 minutes"), 138)
        self.assertEqual(parser.parse_minutes("1 hour and 21 minutes"), 81)
        self.assertEqual(parser.parse_minutes("11 hours and 30 minutes"), 690)

    def test_no_duration(self):
        self.assertIsNone(parser.parse_minutes(""))
        self.assertIsNone(parser.parse_minutes(None))
        self.assertIsNone(parser.parse_minutes("wind"))


class TestParseAirportStatusJson(unittest.TestCase):
    def test_valid_document(self):
        text = (
            '{"IATA": "ATL", "delay": "true", "status": '
            '{"reason": "due to weather", "avgDelay": "45 minutes"}}'
        )
        parsed = parser.parse_airport_status_json(text)
        self.assertEqual(parsed["code"], "ATL")
        self.assertTrue(parsed["delayed"])
        self.assertEqual(parsed["delay_minutes"], 45)
        self.assertEqual(parsed["reason"], "due to weather")

    def test_no_delay_flag(self):
        text = '{"IATA": "MCI", "delay": "false", "status": {}}'
        parsed = parser.parse_airport_status_json(text)
        self.assertEqual(parsed["code"], "MCI")
        self.assertFalse(parsed["delayed"])
        self.assertIsNone(parsed["delay_minutes"])

    def test_empty_and_invalid(self):
        self.assertIsNone(parser.parse_airport_status_json(""))
        self.assertIsNone(parser.parse_airport_status_json("   "))
        self.assertIsNone(parser.parse_airport_status_json(None))
        self.assertIsNone(parser.parse_airport_status_json("not json"))
        self.assertIsNone(parser.parse_airport_status_json("{}"))
        self.assertIsNone(parser.parse_airport_status_json("[1, 2]"))


class TestFindCenters(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(
            parser.find_centers("outage at ZTL and ZDC"), {"ZTL", "ZDC"}
        )

    def test_names_need_center(self):
        self.assertEqual(
            parser.find_centers("Atlanta Center is degraded"), {"ZTL"}
        )
        self.assertEqual(parser.find_centers("flying to Atlanta"), set())

    def test_none(self):
        self.assertEqual(parser.find_centers("wind at SFO"), set())
        self.assertEqual(parser.find_centers(""), set())


if __name__ == "__main__":
    unittest.main()
