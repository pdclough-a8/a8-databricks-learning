"""Generate the synthetic A8 Events data used throughout the course.

Deterministic: the same seed always produces identical CSV files, so expected
exercise answers stay stable. All people, emails and organisations are fictional;
emails use the reserved example.com domain.
"""

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 8
SNAPSHOT = date(2026, 11, 20)
OUT = Path(__file__).resolve().parent / "raw"

VENUES = {
    "Leeds": ("The Engine House", 80),
    "Manchester": ("Mill Yard Studios", 120),
    "London": ("Riverside Hall", 150),
    "Bristol": ("Harbourside Rooms", 60),
    "Online": ("A8 Live (online)", 300),
}
TOPICS = {
    "AI": ["Practical GenAI Clinic", "AI Builders Workshop", "Responsible AI Roundtable"],
    "Data engineering": ["Lakehouse Foundations", "Pipelines in Practice", "Data Quality Lab"],
    "Analytics": ["Analytics Breakfast", "Dashboard Design Studio", "Metrics That Matter"],
    "Leadership": ["Data Leaders Forum", "AI Strategy Briefing", "Value Delivery Masterclass"],
}
FIRST = ["Amira", "Ben", "Chloe", "Dev", "Ella", "Finn", "Grace", "Hamza", "Isla", "Jack",
         "Kiran", "Leah", "Mo", "Nina", "Owen", "Priya", "Quinn", "Rosa", "Sam", "Tara",
         "Usman", "Vera", "Will", "Yasmin", "Zak"]
LAST = ["Ahmed", "Brooks", "Clarke", "Dawson", "Evans", "Fletcher", "Gill", "Hughes", "Iqbal",
        "Jones", "Khan", "Lewis", "Morgan", "Nash", "O'Neill", "Patel", "Reid", "Shaw",
        "Turner", "Walsh", "Young"]
ORG_TYPES = [("corporate", 0.55), ("public_sector", 0.15), ("charity", 0.08),
             ("student", 0.10), ("individual", 0.12)]

COMMENTS = {
    "venue": {
        "pos": ["Great venue, easy to reach from the station.", "Lovely room with plenty of space.",
                "The venue was bright, comfortable and well signposted."],
        "neg": ["The room was too warm and quite cramped.", "Hard to find the entrance, signage was poor.",
                "Seating was uncomfortable for a full day."],
    },
    "content": {
        "pos": ["Really practical content I can use at work tomorrow.", "Excellent worked examples.",
                "Clear explanations and a good pace throughout."],
        "neg": ["Too introductory for the advertised level.", "Content felt rushed at the end.",
                "Would have liked more hands-on exercises."],
    },
    "speakers": {
        "pos": ["Speakers were knowledgeable and engaging.", "Brilliant Q&A session with the speakers."],
        "neg": ["One speaker read straight from the slides.", "The panel ran over and cut the Q&A."],
    },
    "catering": {
        "pos": ["Good coffee and a decent lunch.", "Catering was excellent with good vegetarian options."],
        "neg": ["Lunch ran out before everyone was served.", "No gluten-free options at lunch."],
    },
    "online": {
        "pos": ["Stream quality was excellent.", "The online chat was well moderated."],
        "neg": ["The stream kept buffering.", "Audio dropped out several times online."],
    },
    "booking": {
        "pos": ["Booking was quick and the joining instructions were clear."],
        "neg": ["Confirmation email arrived very late.", "Hard to change my booking to a colleague."],
    },
}


def _weighted(rng, pairs):
    x, acc = rng.random(), 0.0
    for value, weight in pairs:
        acc += weight
        if x <= acc:
            return value
    return pairs[-1][0]


def build():
    rng = random.Random(SEED)
    events, bookings, feedback = [], [], []
    cities = list(VENUES)
    customers = {}

    for n in range(60):
        # 48 completed events up to the snapshot, then 12 scheduled ones after it.
        if n < 48:
            day = date(2025, 1, 8) + timedelta(days=n * 14 + rng.randint(-3, 3))
        else:
            day = SNAPSHOT + timedelta(days=(n - 47) * 9 + rng.randint(-2, 2))
        city = cities[n % len(cities)] if n % 7 else "Online"
        topic = list(TOPICS)[n % 4]
        fmt = "online" if city == "Online" else ("hybrid" if n % 5 == 0 else "in_person")
        venue, capacity = VENUES[city]
        capacity = int(capacity * rng.choice([0.5, 0.75, 1.0]))
        price = 0 if city == "Online" and n % 2 else rng.choice([45, 95, 95, 195])
        start_hour = rng.choice([9, 9, 13, 18])
        status = "completed" if day < SNAPSHOT else "scheduled"
        quality = rng.gauss(0, 1)
        events.append({
            "event_id": f"E{101 + n}", "event_name": rng.choice(TOPICS[topic]), "topic": topic,
            "format": fmt, "city": city, "venue": venue, "event_date": day.isoformat(),
            "start_hour": start_hour, "capacity": capacity, "price_gbp": price, "status": status,
        })

        demand = min(1.05, max(0.35, rng.gauss(0.8, 0.18) + (0.1 if topic == "AI" else 0)))
        target = int(capacity * demand)
        sold = 0
        while sold < target:
            lead = max(1, int(rng.expovariate(1 / 28)))
            booked = day - timedelta(days=lead)
            if status == "scheduled" and booked > SNAPSHOT:
                sold += 1  # demand that has not arrived yet at the snapshot
                continue
            tickets = _weighted(rng, [(1, 0.8), (2, 0.15), (3, 0.05)])
            if sold + tickets > capacity:
                break
            org = _weighted(rng, ORG_TYPES)
            if price == 0:
                ticket_type = "free"
            elif rng.random() < 0.08:
                ticket_type = "complimentary"
            elif org == "student":
                ticket_type = "student"
            elif lead > 45:
                ticket_type = "early_bird"
            else:
                ticket_type = "standard"
            cid = rng.randint(1, 1400)
            if cid not in customers:
                first, last = rng.choice(FIRST), rng.choice(LAST)
                slug = (first + "." + last).lower().replace("'", "")
                customers[cid] = (f"{first} {last}", f"{slug}{cid}@example.com")
            name, email = customers[cid]
            cancelled = rng.random() < 0.07
            booking_status = "cancelled" if cancelled else "confirmed"
            attended = ""
            if status == "completed" and not cancelled:
                logit = 1.7
                logit -= {"complimentary": 1.3, "free": 1.1, "student": 0.3}.get(ticket_type, 0)
                logit -= {"online": 0.6, "hybrid": 0.2}.get(fmt, 0)
                logit -= 0.6 if day.weekday() == 4 else 0
                logit -= 0.35 if start_hour == 18 else 0
                logit -= 0.5 if lead > 60 else 0
                logit += 0.3 if org == "corporate" else 0
                logit += 0.2 if tickets > 1 else 0
                logit += 0.25 * quality
                attended = "true" if rng.random() < 1 / (1 + math.exp(-logit)) else "false"
            bookings.append({
                "booking_id": f"B{len(bookings) + 10001}", "event_id": f"E{101 + n}",
                "customer_name": name, "customer_email": email, "organisation_type": org,
                "booked_date": booked.isoformat(), "ticket_type": ticket_type, "tickets": tickets,
                "status": booking_status, "attended": attended,
            })
            sold += tickets
            if attended == "true" and rng.random() < 0.16:
                aspects = ["content", "speakers", "booking"]
                aspects += ["online"] if fmt != "in_person" else ["venue", "catering"]
                aspect = rng.choice(aspects)
                score = quality + rng.gauss(0, 1.1)
                rating = max(1, min(5, round(3.6 + score)))
                tone = "pos" if rating >= 4 else "neg" if rating <= 2 else rng.choice(["pos", "neg"])
                feedback.append({
                    "feedback_id": f"F{len(feedback) + 5001}", "event_id": f"E{101 + n}",
                    "booking_id": bookings[-1]["booking_id"],
                    "submitted_date": (day + timedelta(days=rng.randint(0, 6))).isoformat(),
                    "rating": rating, "comment": rng.choice(COMMENTS[aspect][tone]),
                })
    return events, bookings, feedback


def write(rows, name):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    events, bookings, feedback = build()
    write(events, "events.csv")
    write(bookings, "bookings.csv")
    write(feedback, "feedback.csv")
    print(len(events), "events,", len(bookings), "bookings,", len(feedback), "feedback")
