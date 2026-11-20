"""
Meridian Health Network: simulated internal scheduling system (webhook receiver).

Receives Cal.com-style booking webhooks, verifies the signature, and stores bookings
in a small SQLite database that stands in for Meridian's internal scheduling system.
Simulation for a portfolio project. Fictional customer. Not affiliated with Cal.com.

Run (plain HTTP):   python receiver.py --port 8000
Run (HTTPS):        python receiver.py --port 8443 --cert certs/server_valid.pem --key certs/server.key
"""
import argparse
import hashlib
import hmac
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, jsonify, request

DB_PATH = os.environ.get("DB_PATH", "internal_scheduling.db")
SECRET = os.environ.get("WEBHOOK_SECRET", "")
SIGNATURE_HEADER = "X-Cal-Signature-256"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("receiver.log")],
)
log = logging.getLogger("receiver")
app = Flask(__name__)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS bookings (
                uid TEXT PRIMARY KEY,
                title TEXT,
                organizer_email TEXT,
                attendee_email TEXT,
                start_time TEXT,
                end_time TEXT,
                status TEXT,
                received_at TEXT
            )"""
        )


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def signature_ok(raw_body: bytes) -> bool:
    if not SECRET:
        return True  # signing not enabled
    expected = hmac.new(SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    received = request.headers.get(SIGNATURE_HEADER, "")
    return hmac.compare_digest(expected, received)


init_db()  # create the table on import, so it also works under gunicorn


@app.get("/health")
def health():
    return jsonify(status="ok", time=now())


@app.get("/bookings")
def bookings():
    with db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM bookings ORDER BY start_time")]
    return jsonify(count=len(rows), bookings=rows)


@app.post("/hooks/cal")
def hook():
    raw = request.get_data()
    if not signature_ok(raw):
        log.warning("REJECTED: invalid signature from %s", request.remote_addr)
        return jsonify(error="invalid signature"), 401

    event = json.loads(raw)
    trigger = event.get("triggerEvent")
    p = event.get("payload", {})
    uid = p.get("uid")
    organizer = (p.get("organizer") or {}).get("email", "")
    attendees = p.get("attendees") or [{}]
    attendee = attendees[0].get("email", "")
    start, end, title = p.get("startTime"), p.get("endTime"), p.get("title")

    with db() as conn:
        if trigger == "BOOKING_CREATED":
            clash = conn.execute(
                "SELECT uid FROM bookings WHERE organizer_email=? AND start_time=? AND status='confirmed'",
                (organizer, start),
            ).fetchone()
            if clash:
                log.warning("DOUBLE BOOKING: %s already has a booking at %s (existing %s, new %s)",
                            organizer, start, clash["uid"], uid)
            conn.execute(
                "INSERT OR IGNORE INTO bookings VALUES (?,?,?,?,?,?,?,?)",
                (uid, title, organizer, attendee, start, end, "confirmed", now()),
            )
        elif trigger == "BOOKING_RESCHEDULED":
            conn.execute("UPDATE bookings SET start_time=?, end_time=?, received_at=? WHERE uid=?",
                         (start, end, now(), uid))
        elif trigger == "BOOKING_CANCELLED":
            conn.execute("UPDATE bookings SET status='cancelled', received_at=? WHERE uid=?",
                         (now(), uid))
        else:
            log.info("IGNORED event %s", trigger)
            return jsonify(status="ignored"), 200

    log.info("RECEIVED %s uid=%s organizer=%s start=%s", trigger, uid, organizer, start)
    return jsonify(status="ok"), 200


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--cert")
    ap.add_argument("--key")
    a = ap.parse_args()
    ctx = (a.cert, a.key) if a.cert and a.key else None
    log.info("Starting receiver on %s:%s (%s)", a.host, a.port, "HTTPS" if ctx else "HTTP")
    app.run(host=a.host, port=a.port, ssl_context=ctx)
