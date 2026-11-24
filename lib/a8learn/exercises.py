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
    "7.1": {
        "task": "Prepare the bounded model input: return feedback_id and comment_length (characters in the comment) "
                "for the first five non-empty comments, ordered by feedback_id.",
        "hint": "Use IDENTIFIER(a8_feedback). Filter comment IS NOT NULL AND trim(comment) <> '', ORDER BY "
                "feedback_id, then LIMIT 5. length(comment) gives the character count.",
        "solution": """SELECT feedback_id, length(comment) AS comment_length FROM IDENTIFIER(a8_feedback)
WHERE comment IS NOT NULL AND trim(comment) <> '' ORDER BY feedback_id LIMIT 5""",
        "explain": "Sorting before LIMIT makes the sample repeatable. A five-row cap bounds the input, not the "
                   "bill: retries, token length and compute still matter. No model was called.",
        "ordered": True,
    },
    "7.2": {
        "task": "Use this invented example, not model output: WITH examples(example_id, rating, sentiment) AS "
                "(VALUES (1,5,'positive'),(2,1,'positive'),(3,3,'neutral'),(4,4,'mixed'),(5,2,NULL),"
                "(6,2,'negative')). Return example_id and review_reason, ordered by example_id. Use 'review' for "
                "NULL or 'mixed' sentiment, and 'disagree' where sentiment differs from the rating heuristic "
                "(1-2 negative, 3 neutral, 4-5 positive). Omit agreeing rows.",
        "hint": "Handle NULL and 'mixed' first so they are never scored as agreement. Then compare sentiment with "
                "a CASE on rating. Keep only rows with a reason.",
        "solution": """WITH examples(example_id, rating, sentiment) AS (
VALUES (1,5,'positive'),(2,1,'positive'),(3,3,'neutral'),(4,4,'mixed'),(5,2,NULL),(6,2,'negative')
)
SELECT example_id, CASE WHEN sentiment IS NULL OR sentiment = 'mixed' THEN 'review' ELSE 'disagree' END
AS review_reason FROM examples
WHERE sentiment IS NULL OR sentiment = 'mixed'
OR sentiment <> CASE WHEN rating <= 2 THEN 'negative' WHEN rating = 3 THEN 'neutral' ELSE 'positive' END
ORDER BY example_id""",
        "explain": "NULL comparisons are never true, so a naive mismatch filter silently drops NULL rows. "
                   "Agreement with a rating is a sanity check, not accuracy.",
        "ordered": True,
    },
}


def get(exercise_id):
    try:
        return EXERCISES[exercise_id]
    except KeyError:
        raise KeyError(f"Unknown exercise {exercise_id!r}; choose from {', '.join(EXERCISES)}") from None


# Short "in your own words" prompts. The learner writes first; the model answer is shown afterwards.
REFLECTIONS = {
    "0.1": {
        "question": "What is the difference between an event, a booking and a ticket?",
        "model": "An event is one occasion we run. A booking is one customer order for an event. "
                 "A booking can hold several tickets, so tickets, not bookings, measure seats taken.",
    },
    "0.2": {
        "question": "Which of descriptive, diagnostic, predictive and prescriptive analytics answers "
                    "'how many people should we expect to turn up next week?'",
        "model": "Predictive. Descriptive says what has happened, diagnostic says why, "
                 "predictive says what is likely to happen, and prescriptive says what to do about it.",
    },
    "1.a": {
        "question": "Why can you stop the compute without losing your tables?",
        "model": "Tables and files live in Unity Catalog storage. Compute only reads and writes them, "
                 "so stopping it removes nothing.",
    },
    "1.b": {
        "question": "What would go wrong if an empty attended value (not yet known) were treated as false "
                    "(did not attend)?",
        "model": "Future bookings would count as no-shows. Counts and any model trained on them would be wrong, "
                 "because 'we do not know yet' is not the same as 'they did not come'.",
    },
    "2.a": {
        "question": "Why is a tag not a permission?",
        "model": "A tag only describes an object so people can find and understand it. A privilege is what "
                 "lets or stops someone reading it, so tagging a table protects nothing.",
    },
    "2.b": {
        "question": "Why does masking part of an email address not make a person anonymous?",
        "model": "The name and other columns can still identify them, and the visible part of the email may too. "
                 "Masking limits what is shown; it does not remove the link to a person.",
    },
    "3.a": {
        "question": "Why do we build the metrics view before any chart or Genie question?",
        "model": "So every number has one exact definition. Charts and Genie then read the same agreed metrics "
                 "instead of each choosing their own way to count bookings or tickets.",
    },
    "3.b": {
        "question": "Why is average rating calculated from a sum and a count, not by averaging each event's average?",
        "model": "Events have different numbers of responses. Averaging averages gives a two-response event the "
                 "same weight as a fifty-response event; sum divided by count weights each response equally.",
    },
    "4.a": {
        "question": "What is the difference between a pattern and a cause?",
        "model": "A pattern is two things moving together in the data. A cause means changing one would change "
                 "the other, which needs a designed comparison or evidence the data does not hold.",
    },
    "4.b": {
        "question": "How can a gap between segments be mix, and how can it be rate?",
        "model": "Mix: one segment holds more of a kind of event that behaves differently. Rate: the same kind of "
                 "event behaves differently in the two segments. A gap can be either or both.",
    },
    "5.a": {
        "question": "Why would using the attendance flag or the feedback rating as a feature be leakage?",
        "model": "They are only known after the event. A model using them looks excellent in testing but cannot "
                 "have them when it predicts for a future booking.",
    },
    "5.b": {
        "question": "Why must a model beat a baseline before it is worth using?",
        "model": "The baseline is the simplest honest guess. A model that cannot do better adds cost and "
                 "complexity for no gain.",
    },
    "6.a": {
        "question": "Why does a decision need the spread of outcomes, not only the expected attendance?",
        "model": "Costs are lopsided. Being short by ten people and being over by ten cost different amounts, "
                 "so we need to know how likely each outcome is, not just the average.",
    },
    "6.b": {
        "question": "Why are the cost figures stated as assumptions?",
        "model": "The course has no measured costs for empty seats or turned-away guests. The recommendation is "
                 "only as good as these inputs, so we show how it changes if they are wrong.",
    },
    "7.a": {
        "question": "Why is agreement between a model's sentiment and the star rating not accuracy?",
        "model": "The rating is another noisy signal, not the truth. Agreement shows they are consistent; "
                 "accuracy needs comments checked by a person against a reliable label.",
    },
}


def get_reflection(reflection_id):
    try:
        return REFLECTIONS[reflection_id]
    except KeyError:
        raise KeyError(f"Unknown reflection {reflection_id!r}; choose from {', '.join(REFLECTIONS)}") from None
