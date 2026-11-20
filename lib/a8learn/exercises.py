"""SQL exercises, checked against the learner's own tables, not memorised numbers.

Solutions use the session variables declared by _config (IDENTIFIER(a8_events) and so on), which is the
same SQL a learner would write in a %sql cell.
"""

EXERCISES = {
    "1.1": {
        "task": "Return city and count of completed events as events, ordered by city.",
        "hint": "Filter status before GROUP BY; COUNT(*) counts events, not bookings. "
                "Read from IDENTIFIER(a8_events).",
        "solution": """SELECT city, count(*) AS events FROM IDENTIFIER(a8_events)
WHERE status = 'completed' GROUP BY city ORDER BY city""",
        "explain": "The grain is one row per city. Filtering before aggregation excludes future events.",
        "ordered": True,
    },
    "1.2": {
        "task": "Return event_id and total confirmed tickets for scheduled events, ordered by event_id.",
        "hint": "Join IDENTIFIER(a8_events) to IDENTIFIER(a8_bookings), filter both statuses and SUM(tickets).",
        "solution": """SELECT e.event_id, sum(b.tickets) AS confirmed_tickets
FROM IDENTIFIER(a8_events) e JOIN IDENTIFIER(a8_bookings) b USING (event_id)
WHERE e.status = 'scheduled' AND b.status = 'confirmed'
GROUP BY e.event_id ORDER BY e.event_id""",
        "explain": "A booking can contain multiple tickets. Counting bookings understates demand.",
        "ordered": True,
    },
    "1b.1": {
        "task": "Return city and confirmed_tickets for scheduled events from event_metrics, "
                "grouped and ordered by city.",
        "hint": "Use IDENTIFIER(a8_event_metrics), filter event_status = 'scheduled', then SUM(confirmed_tickets).",
        "solution": """SELECT city, sum(confirmed_tickets) AS confirmed_tickets
FROM IDENTIFIER(a8_event_metrics)
WHERE event_status = 'scheduled' GROUP BY city ORDER BY city""",
        "explain": "The reporting grain is one row per event. SUM counts tickets; COUNT counts events.",
        "ordered": True,
    },
    "1b.2": {
        "task": "Return topic, feedback_count and average_rating for completed events, ordered by topic. "
                "Round the feedback-weighted average rating to two decimal places.",
        "hint": "SUM(rating_sum) / SUM(feedback_count), not AVG(average_rating). "
                "Use 1.0 for fractional division and NULLIF for an empty denominator.",
        "solution": """SELECT topic, sum(feedback_count) AS feedback_count,
round(1.0 * sum(rating_sum) / nullif(sum(feedback_count), 0), 2) AS average_rating
FROM IDENTIFIER(a8_event_metrics)
WHERE event_status = 'completed' GROUP BY topic ORDER BY topic""",
        "explain": "Weight by responses, not by events. An event with one response must not outweigh one with twenty. "
                   "Missing feedback remains unknown, not a zero-star review.",
        "ordered": True,
    },
    "2.1": {
        "task": "Return city and row count from bookings_governed, grouped and ordered by city.",
        "hint": "Query IDENTIFIER(a8_bookings_governed), not the unrestricted bookings table.",
        "solution": """SELECT city, count(*) FROM IDENTIFIER(a8_bookings_governed)
GROUP BY city ORDER BY city""",
        "explain": "The policy is evaluated at read time. Only Leeds and Online survive this demo filter.",
        "ordered": True,
    },
    "2.2": {
        "task": "Return the count of governed rows whose customer_email does not contain '***'.",
        "hint": "Use NOT LIKE '%***%' on the masked column. The expected count is zero.",
        "solution": """SELECT count(*) FROM IDENTIFIER(a8_bookings_governed)
WHERE customer_email NOT LIKE '%***%'""",
        "explain": "SQL sees the masked value, not the original email. This is not encryption or anonymisation.",
    },
    "3.1": {
        "task": "Using only the latest prediction per booking, return event_id and expected_attendees, "
                "grouped and ordered by event_id.",
        "hint": "Rank rows with row_number() over (partition by booking_id order by scored_at desc), "
                "keep rank 1, then sum tickets * attendance_probability.",
        "solution": """WITH ranked AS (
SELECT p.*, row_number() OVER (
PARTITION BY booking_id ORDER BY scored_at DESC NULLS LAST, CAST(model_version AS INT) DESC
) AS score_rank FROM IDENTIFIER(a8_attendance_predictions) p
)
SELECT event_id, sum(tickets * attendance_probability) AS expected_attendees
FROM ranked WHERE score_rank = 1 GROUP BY event_id ORDER BY event_id""",
        "explain": "Latest-score selection prevents retraining from double-counting a booking. "
                   "Expected attendance remains fractional and uncertain.",
        "ordered": True,
    },
}


def get(exercise_id):
    try:
        return EXERCISES[exercise_id]
    except KeyError:
        raise KeyError(f"Unknown exercise {exercise_id!r}; choose from {', '.join(EXERCISES)}") from None
