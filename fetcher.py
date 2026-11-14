"""Fetcher for ATC Watch.

Reads public FAA status feeds only. Plain GET, no login, no credentials,
no cookies. Only two hosts are ever contacted:

- nasstatus.faa.gov (FAA National Airspace System dashboard data)
- services.faa.gov (FAA airport status feed)

Stdlib only. Python 3.9 compatible.
"""

import urllib.error
import urllib.request

USER_AGENT = "ATC-Watch/0.1 (student project; tilakthapa.com)"
TIMEOUT = 15

NAS_STATUS_URL = "https://nasstatus.faa.gov/api/airport-status-information"
AIRPORT_STATUS_URL = "https://services.faa.gov/airport/status/{code}?format=json"

ALLOWED_HOSTS = ("nasstatus.faa.gov", "services.faa.gov")


def _get(url):
    """GET a URL and return the response body as text, or None on any failure.

    Any network error, HTTP error status, timeout, or empty body is a
    silent None: the caller treats it as 'no data from this source'.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not body or not body.strip():
        return None
    return body


def fetch_nas_status():
    """Fetch the FAA airport-status-information feed (XML).

    This is the data feed behind the public NAS dashboard at
    nasstatus.faa.gov. Verified live 2026-11-14: HTTP 200, XML document
    with <Delay_type> sections (Ground Delay Programs, Airport Closures,
    and others when active).
    """
    return _get(NAS_STATUS_URL)


def fetch_airport_status(code):
    """Fetch the per-airport status feed for one 3-letter airport code.

    Returns raw text, or None on any failure. As of 2026-11-13/14 this
    feed answers the TLS handshake and then closes the connection with
    an empty reply, so it is currently unverified; callers must treat
    None as 'no data', never as an error to crash on.
    """
    code = (code or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        return None
    return _get(AIRPORT_STATUS_URL.format(code=code))
