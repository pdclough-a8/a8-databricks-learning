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
    "3.1": {
        "task": "Return city and confirmed_tickets for scheduled events from event_metrics, "
                "grouped and ordered by city.",
        "hint": "Use IDENTIFIER(a8_event_metrics), filter event_status = 'scheduled', then SUM(confirmed_tickets).",
        "solution": """SELECT city, sum(confirmed_tickets) AS confirmed_tickets
FROM IDENTIFIER(a8_event_metrics)
WHERE event_status = 'scheduled' GROUP BY city ORDER BY city""",
        "explain": "The reporting grain is one row per event. SUM counts tickets; COUNT counts events.",
        "ordered": True,
    },
    "3.2": {
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
    "4.1": {
        "task": "For completed events, return topic and gap_pp: online ticket-weighted attendance minus "
                "not-online ticket-weighted attendance, in percentage points rounded to 1 decimal place, "
                "ordered by topic.",
        "hint": "Use IDENTIFIER(a8_event_metrics). Two conditional sums per segment: "
                "SUM(CASE WHEN format = 'online' THEN attended_tickets END) over the matching known_outcome_tickets. "
                "Multiply by 1.0 first so the division is fractional.",
        "solution": """SELECT topic,
round(100.0 * (1.0 * sum(CASE WHEN format = 'online' THEN attended_tickets END)
  / nullif(sum(CASE WHEN format = 'online' THEN known_outcome_tickets END), 0)
  - 1.0 * sum(CASE WHEN format <> 'online' THEN attended_tickets END)
  / nullif(sum(CASE WHEN format <> 'online' THEN known_outcome_tickets END), 0)), 1) AS gap_pp
FROM IDENTIFIER(a8_event_metrics)
WHERE event_status = 'completed' GROUP BY topic ORDER BY topic""",
        "explain": "Each segment's rate is its own attended tickets over its own known-outcome tickets. "
                   "Subtracting averages of per-event rates would weight a small event like a large one.",
        "ordered": True,
    },
    "4.2": {
        "task": "Split the gap in average feedback rating between online and not-online completed events "
                "(online minus not online) into a topic-mix effect and a within-topic rate effect. Return one row: "
                "mix_effect, rate_effect, total_gap, each rounded to 2 decimals.",
        "hint": "Same shape as the attendance split in the notebook: weight by feedback_count, rate is "
                "SUM(rating_sum) / SUM(feedback_count) per topic and segment. Mix = (online share - other share) "
                "x average of the two rates; rate = (online rate - other rate) x average of the two shares.",
        "solution": """WITH cells AS (
  SELECT CASE WHEN format = 'online' THEN 'online' ELSE 'other' END AS segment, topic,
    sum(feedback_count) AS n, sum(rating_sum) AS s
  FROM IDENTIFIER(a8_event_metrics) WHERE event_status = 'completed'
  GROUP BY CASE WHEN format = 'online' THEN 'online' ELSE 'other' END, topic
), shares AS (
  SELECT c.topic, c.segment, 1.0 * c.n / t.total AS share, 1.0 * c.s / nullif(c.n, 0) AS rate
  FROM cells c JOIN (SELECT segment, sum(n) AS total FROM cells GROUP BY segment) t
    ON c.segment = t.segment
), paired AS (
  SELECT o.share AS o_share, p.share AS p_share, o.rate AS o_rate, p.rate AS p_rate
  FROM shares o JOIN shares p ON o.topic = p.topic
  WHERE o.segment = 'online' AND p.segment = 'other'
)
SELECT round(sum((o_share - p_share) * (o_rate + p_rate) / 2), 2) AS mix_effect,
  round(sum((o_rate - p_rate) * (o_share + p_share) / 2), 2) AS rate_effect,
  round(sum((o_share - p_share) * (o_rate + p_rate) / 2
    + (o_rate - p_rate) * (o_share + p_share) / 2), 2) AS total_gap
FROM paired""",
        "explain": "The two effects add up exactly to the gap. Mix says the segments contain different topics; "
                   "rate says the same topic is rated differently. Neither says why.",
    },
    "6.1": {
        "task": "For scheduled events with predicted attendance, return event_id, show_probability (expected_attendees "
                "divided by confirmed_tickets, rounded to 3 decimals) and simple_limit (capacity divided by the "
                "unrounded show probability, truncated to a whole number of tickets), ordered by event_id.",
        "hint": "Use IDENTIFIER(a8_event_forecast). Keep rows where expected_attendees > 0 so you never divide by "
                "zero. CAST(... AS INT) truncates. Divide the unrounded probability, then round only the shown one.",
        "solution": """SELECT event_id, round(expected_attendees / confirmed_tickets, 3) AS show_probability,
CAST(capacity / (expected_attendees / confirmed_tickets) AS INT) AS simple_limit
FROM IDENTIFIER(a8_event_forecast) WHERE expected_attendees > 0 ORDER BY event_id""",
        "explain": "Selling capacity / p tickets fills the room on average, but ignores the spread of turnout. "
                   "The simulation prices both the empty seats and the people turned away.",
        "ordered": True,
    },
    "6.2": {
        "task": "Using only the latest prediction per booking, return event_id and attendance_variance: the sum of "
                "tickets squared x probability x (1 - probability), rounded to 2 decimals, ordered by event_id.",
        "hint": "Reuse the row_number() pattern from exercise 5.1 on IDENTIFIER(a8_attendance_predictions), "
                "keep rank 1, then sum tickets * tickets * attendance_probability * (1 - attendance_probability).",
        "solution": """WITH ranked AS (
SELECT p.*, row_number() OVER (
PARTITION BY booking_id ORDER BY scored_at DESC NULLS LAST, CAST(model_version AS INT) DESC
) AS score_rank FROM IDENTIFIER(a8_attendance_predictions) p
)
SELECT event_id,
round(sum(tickets * tickets * attendance_probability * (1 - attendance_probability)), 2) AS attendance_variance
FROM ranked WHERE score_rank = 1 GROUP BY event_id ORDER BY event_id""",
        "explain": "A booking attends together, so its tickets count squared in the variance. Using every score "
                   "instead of the latest would double-count bookings and overstate the uncertainty.",
        "ordered": True,
    },    "2.1": {
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
    "5.1": {
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
