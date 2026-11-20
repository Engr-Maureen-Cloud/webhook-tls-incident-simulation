"""
Reconcile missed bookings: compare sent_events.csv (the booking export) with the
internal database and insert any bookings that never arrived.

Usage: python reconcile.py --csv sent_events.csv [--apply]
Without --apply it only reports what is missing.
"""
import argparse
import csv
import os
import sqlite3
from datetime import datetime, timezone

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="sent_events.csv")
ap.add_argument("--db", default=os.environ.get("DB_PATH", "internal_scheduling.db"))
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()

conn = sqlite3.connect(a.db)
conn.execute("""CREATE TABLE IF NOT EXISTS bookings (uid TEXT PRIMARY KEY, title TEXT, organizer_email TEXT,
                attendee_email TEXT, start_time TEXT, end_time TEXT, status TEXT, received_at TEXT)""")
have = {r[0] for r in conn.execute("SELECT uid FROM bookings")}
missing = [r for r in csv.DictReader(open(a.csv)) if r["uid"] not in have]
print(f"{len(missing)} booking(s) in the export are missing from the internal system.")
for r in missing:
    print(f"  missing: {r['uid']}  {r['organizer_email']}  {r['start_time']}")
    if a.apply:
        conn.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?)",
                     (r["uid"], r["title"], r["organizer_email"], r["attendee_email"], r["start_time"],
                      r["end_time"], "confirmed", datetime.now(timezone.utc).isoformat(timespec="seconds") + " (reconciled)"))
if a.apply:
    conn.commit()
    print(f"Inserted {len(missing)} booking(s).")
else:
    print("Run again with --apply to insert them.")
