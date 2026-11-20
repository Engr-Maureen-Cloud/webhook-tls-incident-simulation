"""
Beginner-friendly check of the receiver. Works the same on Windows, Mac and Linux.

Examples:
  python check.py --url https://localhost:8443/health   --cafile certs/ca.pem
  python check.py --url https://localhost:8443/bookings --cafile certs/ca.pem
"""
import argparse
import json

import requests

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--cafile")
a = ap.parse_args()

try:
    r = requests.get(a.url, timeout=10, verify=a.cafile if a.cafile else True)
    data = r.json()
    print(f"HTTP {r.status_code}")
    if "count" in data:
        print(f"Bookings in the internal system: {data['count']}")
        for b in data["bookings"]:
            print(f"  {b['uid']}  {b['organizer_email']}  {b['start_time']}  {b['status']}")
    else:
        print(json.dumps(data))
except requests.exceptions.SSLError as e:
    reason = getattr(e.args[0], "reason", None) or e
    print(f"TLS ERROR: {reason}")
    print("The secure connection failed, so the receiver never saw this request.")
except requests.exceptions.RequestException as e:
    print(f"CONNECTION ERROR: {type(e).__name__}. Is the receiver running?")
