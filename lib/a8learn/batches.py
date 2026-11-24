"""Deterministic batches of new A8 Events bookings for Module 13.

The course data stops at 20 November 2026. These batches stand in for bookings that arrive afterwards as CSV files.
Each batch is fixed by its number, so every learner lands identical files and the expected row counts are known.
Every batch holds mostly good rows and a few deliberately bad ones (a zero or negative ticket count, an unknown
status) so that the pipeline's data-quality rules have something to catch. All people are fictional.
"""
import csv
import io
import random
from datetime import date, timedelta

SNAPSHOT = date(2026, 11, 20)
COLUMNS = ["booking_id", "event_id", "customer_name", "customer_email", "organisation_type", "booked_date",
           "ticket_type", "tickets", "status", "attended"]
SCHEMA = ("booking_id STRING, event_id STRING, customer_name STRING, customer_email STRING, "
          "organisation_type STRING, booked_date DATE, ticket_type STRING, tickets INT, status STRING, "
          "attended BOOLEAN")
GOOD_ROWS = 40
BAD_ROWS = 3
FIRST = ["Amira", "Ben", "Chloe", "Dev", "Ella", "Finn", "Grace", "Hamza", "Isla", "Jack", "Kiran", "Leah"]
LAST = ["Ahmed", "Brooks", "Clarke", "Dawson", "Evans", "Fletcher", "Gill", "Hughes", "Iqbal", "Jones", "Khan"]
ORGANISATIONS = ["corporate", "public_sector", "charity", "student", "individual"]
TICKET_TYPES = ["standard", "early_bird", "student", "free"]


def new_batch(number, scheduled_event_ids):
    """Rows for batch ``number`` (1, 2, ...): GOOD_ROWS valid bookings then BAD_ROWS invalid ones."""
    if number < 1 or not scheduled_event_ids:
        raise ValueError("A batch needs a number from 1 and at least one scheduled event.")
    rng = random.Random(8_000 + number)
    events = sorted(scheduled_event_ids)
    booked = (SNAPSHOT + timedelta(days=number)).isoformat()
    rows = []
    for i in range(GOOD_ROWS + BAD_ROWS):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        rows.append({
            "booking_id": f"N{number}-{i + 1:03d}",
            "event_id": rng.choice(events),
            "customer_name": f"{first} {last}",
            "customer_email": f"{first.lower()}.{last.lower()}{rng.randint(100, 999)}@example.com",
            "organisation_type": rng.choice(ORGANISATIONS),
            "booked_date": booked,
            "ticket_type": rng.choice(TICKET_TYPES),
            "tickets": rng.randint(1, 3),
            "status": "confirmed" if rng.random() < 0.9 else "cancelled",
            "attended": "",
        })
    first_bad = GOOD_ROWS
    rows[first_bad]["tickets"] = rng.choice([0, -2])  # no seats: the ticket rule drops it
    rows[first_bad + 1]["status"] = "pending"  # not a status we model: the status rule drops it
    rows[first_bad + 2]["booking_id"] = ""  # no id: the id rule drops it
    return rows


def to_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def is_valid(row):
    """The data-quality rules the pipeline applies: an id, positive tickets and a known status."""
    return bool(row["booking_id"]) and int(row["tickets"]) > 0 and row["status"] in {"confirmed", "cancelled"}
