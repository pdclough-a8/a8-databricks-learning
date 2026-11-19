"""SQL exercises, checked against the learner's own tables, not memorised numbers."""

EXERCISES = {
    "1.1": {
        "task": "Return city and count of completed events as events, ordered by city.",
        "hint": "Filter status before GROUP BY; COUNT(*) counts events, not bookings.",
        "solution": """SELECT city, count(*) AS events FROM {events}
WHERE status = 'completed' GROUP BY city ORDER BY city""",
        "explain": "The grain is one row per city. Filtering before aggregation excludes future events.",
        "ordered": True,
    },
    "1.2": {
        "task": "Return event_id and total confirmed tickets for scheduled events, ordered by event_id.",
        "hint": "Join events to bookings, filter both statuses and SUM(tickets), not COUNT(*).",
        "solution": """SELECT e.event_id, sum(b.tickets) AS confirmed_tickets
FROM {events} e JOIN {bookings} b USING (event_id)
WHERE e.status = 'scheduled' AND b.status = 'confirmed'
GROUP BY e.event_id ORDER BY e.event_id""",
        "explain": "A booking can contain multiple tickets. Counting bookings understates demand.",
        "ordered": True,
    },
    "2.1": {
        "task": "Return city and row count from bookings_governed, grouped and ordered by city.",
        "hint": "Query the governed table, not the unrestricted bookings table.",
        "solution": """SELECT city, count(*) FROM {bookings_governed}
GROUP BY city ORDER BY city""",
        "explain": "The policy is evaluated at read time. Only Leeds and Online survive this demo filter.",
        "ordered": True,
    },
    "2.2": {
        "task": "Return the count of governed rows whose customer_email does not contain '***'.",
        "hint": "Use NOT LIKE '%***%' on the masked column. The expected count is zero.",
        "solution": """SELECT count(*) FROM {bookings_governed}
WHERE customer_email NOT LIKE '%***%'""",
        "explain": "SQL sees the masked value, not the original email. This is not encryption or anonymisation.",
    },
    "3.1": {
        "task": "Return event_id and sum(tickets * attendance_probability) as expected_attendees from attendance_predictions, grouped and ordered by event_id.",
        "hint": "Probability applies to a booking; weight by its ticket count. Do not round each booking.",
        "solution": """SELECT event_id, sum(tickets * attendance_probability) AS expected_attendees
FROM {attendance_predictions} GROUP BY event_id ORDER BY event_id""",
        "explain": "Expected attendance is fractional and uncertain, not a guaranteed headcount.",
        "ordered": True,
    },
}


def get(exercise_id):
    try:
        return EXERCISES[exercise_id]
    except KeyError:
        raise KeyError(f"Unknown exercise {exercise_id!r}; choose from {', '.join(EXERCISES)}") from None
