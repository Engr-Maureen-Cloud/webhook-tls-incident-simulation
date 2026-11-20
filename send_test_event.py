"""
Simulates Cal.com delivering booking webhooks to the receiver.
Also records each event it sends to sent_events.csv (stands in for a booking export).

Examples:
  python send_test_event.py --url https://localhost:8443/hooks/cal --cafile certs/ca.pem --count 3
  python send_test_event.py --url https://localhost:8443/hooks/cal --cafile certs/ca.pem --count 5 --duplicate
"""
import argparse
import csv
import hashlib
import hmac
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--cafile", help="CA certificate to trust (omit to use system trust store)")
ap.add_argument("--secret", default=os.environ.get("WEBHOOK_SECRET", ""))
ap.add_argument("--event", default="BOOKING_CREATED")
ap.add_argument("--count", type=int, default=1)
ap.add_argument("--duplicate", action="store_true", help="also send a second booking for the same practitioner and time")
args = ap.parse_args()

CLINICS = ["Riverside", "Northgate", "Eastside", "Harbour"]
verify = args.cafile if args.cafile else True


def make_event(i, base, same_slot_as=None):
    start = same_slot_as["start"] if same_slot_as else base + timedelta(hours=i)
    organizer = same_slot_as["organizer"] if same_slot_as else f"practitioner{i % 3 + 1}@meridian-example.com"
    uid = uuid.uuid4().hex[:12]
    event = {
        "triggerEvent": args.event,
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": {
            "uid": uid,
            "title": f"Consultation ({CLINICS[i % len(CLINICS)]})",
            "startTime": start.isoformat(timespec="minutes"),
            "endTime": (start + timedelta(minutes=30)).isoformat(timespec="minutes"),
            "organizer": {"email": organizer},
            "attendees": [{"email": f"patient{i}@example.com"}],
        },
    }
    return event, {"uid": uid, "start": start, "organizer": organizer}


def send(event):
    body = json.dumps(event).encode()
    headers = {"Content-Type": "application/json"}
    if args.secret:
        headers["X-Cal-Signature-256"] = hmac.new(args.secret.encode(), body, hashlib.sha256).hexdigest()
    return requests.post(args.url, data=body, headers=headers, timeout=10, verify=verify)


base = (datetime.now(timezone.utc) + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
events, failures = [], 0
for i in range(args.count):
    events.append(make_event(i, base))
if args.duplicate and events:
    events.append(make_event(args.count, base, same_slot_as=events[0][1]))

new_file = not os.path.exists("sent_events.csv")
with open("sent_events.csv", "a", newline="") as f:
    w = csv.writer(f)
    if new_file:
        w.writerow(["uid", "title", "organizer_email", "attendee_email", "start_time", "end_time"])
    for event, _ in events:
        p = event["payload"]
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            r = send(event)
            print(f"{stamp} DELIVERED {event['triggerEvent']} uid={p['uid']} -> HTTP {r.status_code}")
        except requests.exceptions.SSLError as e:
            failures += 1
            reason = str(e.args[0].reason) if getattr(e.args[0], "reason", None) else str(e)
            print(f"{stamp} DELIVERY FAILED {event['triggerEvent']} uid={p['uid']} -> TLS error: {reason}")
        except requests.exceptions.RequestException as e:
            failures += 1
            print(f"{stamp} DELIVERY FAILED {event['triggerEvent']} uid={p['uid']} -> {type(e).__name__}")
        w.writerow([p["uid"], p["title"], p["organizer"]["email"], p["attendees"][0]["email"], p["startTime"], p["endTime"]])

print(f"\nSent {len(events)} events, {failures} failed.")
sys.exit(2 if failures else 0)
