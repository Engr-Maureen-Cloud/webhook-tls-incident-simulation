# Webhook failure demo: expired certificate (Meridian Health Network)

A small, working reproduction of a **silent webhook failure** for a customer success and
technical account management portfolio.

> Simulation. Meridian Health Network is fictional. Not affiliated with or endorsed by Cal.com.
> The payload is modelled on Cal.com's webhook format; check Cal.com's current webhook
> documentation before relying on field names or the signature header.

## The scenario
Cal.com sends a booking event to the customer's internal scheduling system when a booking is
created, rescheduled or cancelled. When the TLS certificate on the customer's webhook endpoint
expires, every delivery fails the secure connection. The booking pages keep working, the
receiver logs nothing (it never sees the request), and staff start double-booking slots.

## What is in this repo
| File | Purpose |
|---|---|
| `receiver.py` | The customer's endpoint. Verifies the signature, stores bookings in SQLite, warns on double bookings |
| `send_test_event.py` | Plays the role of Cal.com: signs and delivers booking events, and records them in `sent_events.csv` |
| `make_certs.py` | Creates a demo CA, a valid certificate and an expired one |
| `check.py` | Checks the receiver from the sender's side (same on Windows, Mac and Linux) |
| `reconcile.py` | Finds bookings missing from the internal system and inserts them from the export |

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python make_certs.py --host localhost
export WEBHOOK_SECRET=demo-secret
```

**1. Healthy state**
```bash
python receiver.py --port 8443 --cert certs/server_valid.pem --key certs/server.key
# second terminal
export WEBHOOK_SECRET=demo-secret
python send_test_event.py --url https://localhost:8443/hooks/cal --cafile certs/ca.pem --count 3 --duplicate
curl --cacert certs/ca.pem https://localhost:8443/bookings
```

**2. The incident: swap in the expired certificate**
```bash
# stop the receiver (Ctrl+C), then:
python receiver.py --port 8443 --cert certs/server_expired.pem --key certs/server.key
python send_test_event.py --url https://localhost:8443/hooks/cal --cafile certs/ca.pem --count 4
curl --cacert certs/ca.pem https://localhost:8443/health      # curl: (60) certificate has expired
```

**3. Fix and recover**
```bash
# restart with certs/server_valid.pem, then:
python reconcile.py --csv sent_events.csv          # report what is missing
python reconcile.py --csv sent_events.csv --apply  # insert it
```

## Root cause and prevention
- **Root cause:** the endpoint's TLS certificate expired, so deliveries failed the TLS handshake.
- **Why it was silent:** the failure happens before the receiver handles any request, so the receiver log shows nothing, and the booking pages are unaffected.
- **Prevention:** certificate expiry monitoring, an alert on failed deliveries (or on "no events received for N hours"), and a quarterly technical health check.

## Production note
`receiver.py` uses Flask's development server for the demo. For anything real, run it behind
Nginx with a production server such as gunicorn, and use a real certificate (Let's Encrypt).
