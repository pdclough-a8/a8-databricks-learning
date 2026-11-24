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
    "8a.1": {
        "task": "Return comment and rows (the number of feedback rows) for each distinct comment that mentions "
                "'stream' or 'audio' in any capitalisation, ordered by rows from highest to lowest, then comment.",
        "hint": "Use lower(comment) LIKE '%stream%' OR lower(comment) LIKE '%audio%', then GROUP BY comment and "
                "count(*). Read from IDENTIFIER(a8_feedback).",
        "solution": """SELECT comment, count(*) AS rows FROM IDENTIFIER(a8_feedback)
WHERE lower(comment) LIKE '%stream%' OR lower(comment) LIKE '%audio%'
GROUP BY comment ORDER BY rows DESC, comment""",
        "explain": "A keyword search finds every comment with the word, including praise such as 'Stream quality was "
                   "excellent'. It cannot tell a complaint from a compliment, and it misses synonyms.",
        "ordered": True,
    },
    "8a.2": {
        "task": "Return event_id and stream_audio_comments, the number of feedback rows mentioning 'stream' or "
                "'audio', for events whose format is 'online'. Only include events with at least one such comment, "
                "ordered by event_id.",
        "hint": "Join IDENTIFIER(a8_feedback) to IDENTIFIER(a8_events) USING (event_id), filter format = 'online' "
                "and the keyword test, then GROUP BY event_id.",
        "solution": """SELECT e.event_id, count(*) AS stream_audio_comments
FROM IDENTIFIER(a8_feedback) f JOIN IDENTIFIER(a8_events) e USING (event_id)
WHERE e.format = 'online' AND (lower(f.comment) LIKE '%stream%' OR lower(f.comment) LIKE '%audio%')
GROUP BY e.event_id ORDER BY e.event_id""",
        "explain": "The grain is one row per event. Filtering before grouping keeps only online events with a match, "
                   "so events with no stream or audio comment do not appear.",
        "ordered": True,
    },
    "8b.1": {
        "task": "Return doc_name and chunks (the number of chunks) for each document in the chunk table, ordered by "
                "chunks from highest to lowest, then doc_name.",
        "hint": "GROUP BY doc_name and count(*). Read from IDENTIFIER(a8_doc_chunks).",
        "solution": """SELECT doc_name, count(*) AS chunks FROM IDENTIFIER(a8_doc_chunks)
GROUP BY doc_name ORDER BY chunks DESC, doc_name""",
        "explain": "The grain of the chunk table is one row per section, so counting rows per document shows how the "
                   "documents were split. A document with many chunks has many headings.",
        "ordered": True,
    },
    "8b.2": {
        "task": "Return doc_name and section for every chunk whose content mentions 'refund' in any capitalisation, "
                "ordered by doc_name, then section.",
        "hint": "Use lower(content) LIKE '%refund%'. Read from IDENTIFIER(a8_doc_chunks).",
        "solution": """SELECT doc_name, section FROM IDENTIFIER(a8_doc_chunks)
WHERE lower(content) LIKE '%refund%' ORDER BY doc_name, section""",
        "explain": "A keyword query finds chunks containing the exact word. A customer asking how to get their money "
                   "back uses different words, which is why retrieval by meaning (embeddings) matters.",
        "ordered": True,
    },
    "8c.1": {
        "task": "Using PySpark rather than SQL, return a DataFrame with doc_name and chunks (the number of chunks) for "
                "the venue documents only (doc_name starting 'venue-') from your chunk table, ordered by doc_name.",
        "hint": "spark.table(A8.t('doc_chunks')), then where(F.col('doc_name').startswith('venue-')), groupBy "
                "('doc_name'), agg(F.count('*').alias('chunks')) and orderBy('doc_name'). Import F with "
                "from pyspark.sql import functions as F.",
        "solution": """SELECT doc_name, count(*) AS chunks FROM IDENTIFIER(a8_doc_chunks)
WHERE doc_name LIKE 'venue-%' GROUP BY doc_name ORDER BY doc_name""",
        "explain": "PySpark and SQL describe the same plan. Filtering before grouping keeps only the venue documents, "
                   "and each venue document has the same number of sections here.",
        "ordered": True,
    },
    "9.1": {
        "task": "Return event_name, city and available for scheduled events in London or Manchester, ordered by "
                "available from highest to lowest, then event_name, then city.",
        "hint": "Filter status = 'scheduled' and city IN ('London', 'Manchester'). Read from "
                "IDENTIFIER(a8_event_availability).",
        "solution": """SELECT event_name, city, available FROM IDENTIFIER(a8_event_availability)
WHERE status = 'scheduled' AND city IN ('London', 'Manchester')
ORDER BY available DESC, event_name, city""",
        "explain": "This is the kind of query a seat tool runs. The view already joins bookings to capacity, so the "
                   "tool only filters and sorts. Keeping it a read of one view is part of what makes it safe.",
        "ordered": True,
    },
    "9.2": {
        "task": "Return city and open_events (the number of scheduled events with available greater than 0) for "
                "each city that has at least one, ordered by open_events from highest to lowest, then city.",
        "hint": "Filter status = 'scheduled' AND available > 0, then GROUP BY city and count(*).",
        "solution": """SELECT city, count(*) AS open_events FROM IDENTIFIER(a8_event_availability)
WHERE status = 'scheduled' AND available > 0 GROUP BY city ORDER BY open_events DESC, city""",
        "explain": "Filtering before grouping counts only events with seats left. An agent asked which city has the "
                   "most open events would need exactly this query, and you can check its answer yourself.",
        "ordered": True,
    },
    "12.1": {
        "task": "Return event_name, city and available for scheduled events with fewer than 40 seats left, ordered by "
                "available from lowest to highest, then event_name, then city.",
        "hint": "Filter status = 'scheduled' AND available < 40. Read from IDENTIFIER(a8_event_availability).",
        "solution": """SELECT event_name, city, available FROM IDENTIFIER(a8_event_availability)
WHERE status = 'scheduled' AND available < 40 ORDER BY available, event_name, city""",
        "explain": "These are the events whose seat numbers matter most to a customer, and the ones a stale snapshot "
                   "would get most wrong: a few late bookings can turn 'some left' into 'full'.",
        "ordered": True,
    },
    "12.2": {
        "task": "Return city and seats_left (the sum of available) for scheduled events in each city, ordered by "
                "seats_left from highest to lowest, then city.",
        "hint": "Filter status = 'scheduled', GROUP BY city and sum(available).",
        "solution": """SELECT city, sum(available) AS seats_left FROM IDENTIFIER(a8_event_availability)
WHERE status = 'scheduled' GROUP BY city ORDER BY seats_left DESC, city""",
        "explain": "Summing seats per city is a question the agent's two tools cannot answer directly. A new tool, or "
                   "a new version of the model, would be needed, which is why releases are numbered.",
        "ordered": True,
    },
    "11.1": {
        "task": "Return one number, low_events: how many scheduled events have fewer than 30 seats left in the "
                "availability view. This is the number the app's second metric shows when the threshold is 30.",
        "hint": "Filter status = 'scheduled' AND available < 30, then count(*). Read from "
                "IDENTIFIER(a8_current_availability), declared by Module 11 setup.",
        "solution": """SELECT count(*) AS low_events FROM IDENTIFIER(a8_current_availability)
WHERE status = 'scheduled' AND available < 30""",
        "explain": "The app runs a query like this one as its service principal, so the principal needs SELECT on "
                   "this view. Without the status filter the count would include cancelled and past events.",
    },
    "14.1": {
        "task": "Return event_name, city and available for the scheduled events called 'Pipelines in Practice' and "
                "'Analytics Breakfast', ordered by event_name then city. These are the true seat counts an "
                "evaluation compares the agent's answers with.",
        "hint": "Filter status = 'scheduled' AND event_name IN (...). Read from IDENTIFIER(a8_current_availability). "
                "The numbers must come from the view, not from the agent.",
        "solution": """SELECT event_name, city, available FROM IDENTIFIER(a8_current_availability)
WHERE status = 'scheduled' AND event_name IN ('Pipelines in Practice', 'Analytics Breakfast')
ORDER BY event_name, city""",
        "explain": "An evaluation is only as honest as its expected values. Reading them straight from the data means "
                   "the agent cannot mark its own work, and when seats change the expected values change with them.",
        "ordered": True,
    },
    "15.1": {
        "task": "Return event_name, city, available and stale_available (available plus 7) for the scheduled events "
                "called 'Pipelines in Practice' and 'Analytics Breakfast', ordered by event_name then city. These "
                "are the true seat counts and the ones a week-old release would report.",
        "hint": "Filter status = 'scheduled' AND event_name IN (...), read from IDENTIFIER(a8_current_availability) "
                "and add a column available + 7 AS stale_available.",
        "solution": """SELECT event_name, city, available, available + 7 AS stale_available
FROM IDENTIFIER(a8_current_availability)
WHERE status = 'scheduled' AND event_name IN ('Pipelines in Practice', 'Analytics Breakfast')
ORDER BY event_name, city""",
        "explain": "The stale column is what customers would be told if the bad version were released. The gate "
                   "catches it because the true column is read from the data, not from either version.",
        "ordered": True,
    },
    "13.1": {
        "task": "Return event_id and new_tickets (the sum of tickets) for confirmed rows in the cleaned bookings, "
                "ordered by new_tickets from highest to lowest, then event_id.",
        "hint": "Filter status = 'confirmed', GROUP BY event_id and sum(tickets). Read from "
                "IDENTIFIER(a8_bookings_clean).",
        "solution": """SELECT event_id, sum(tickets) AS new_tickets FROM IDENTIFIER(a8_bookings_clean)
WHERE status = 'confirmed' GROUP BY event_id ORDER BY new_tickets DESC, event_id""",
        "explain": "The cleaned table has already lost the rows that broke the quality rules, so a plain sum is safe. "
                   "Run the same query on the bronze table and the zero and negative ticket rows would be counted.",
        "ordered": True,
    },
    "13.2": {
        "task": "Return event_name, city and available for scheduled events in the gold table with fewer than 30 "
                "seats left, ordered by available from lowest to highest, then event_name, then city.",
        "hint": "Filter status = 'scheduled' AND available < 30. Read from IDENTIFIER(a8_seats_live).",
        "solution": """SELECT event_name, city, available FROM IDENTIFIER(a8_seats_live)
WHERE status = 'scheduled' AND available < 30 ORDER BY available, event_name, city""",
        "explain": "Gold already combines the history and the new bookings, so the query only filters and sorts. "
                   "Compare it with the same question on Module 1's view to see which events the stale numbers hid.",
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
    "8a.a": {
        "question": "Why does counting words miss comments that mean the same thing?",
        "model": "A word count only sees the exact words used, so 'audio dropped out' and 'the stream kept buffering' "
                 "share nothing. An embedding model places texts with similar meaning close together even when no "
                 "word matches.",
    },
    "8a.b": {
        "question": "Why can two comments with similar vectors still express opposite opinions?",
        "model": "Embeddings mostly capture topic. 'The stream kept buffering' and 'Stream quality was excellent' are "
                 "both about the stream, so they can sit close together. Similarity is not agreement, so check "
                 "sentiment separately.",
    },
    "8b.a": {
        "question": "Why give the model retrieved passages instead of just asking it the question?",
        "model": "The model has never seen A8's policies and may guess. Retrieval puts the relevant passages in the "
                 "prompt, so the answer comes from our documents, can cite them, and updates when the documents do.",
    },
    "8b.b": {
        "question": "Give two reasons retrieval could miss a passage that does contain the answer.",
        "model": "The chunk may be too large or too small, so its meaning is blurred or its context is lost. The "
                 "question may use different words from the document and the search may rank another chunk higher. "
                 "The document may also be missing or out of date.",
    },
    "8c.a": {
        "question": "When does a managed vector index become worthwhile compared with searching by hand?",
        "model": "Searching by hand compares a question with every vector, which is fine for a few dozen chunks. "
                 "Once there are thousands or millions, or you need the index to follow a changing table without "
                 "your own code, a managed index is built for fast nearest-neighbour search and syncing.",
    },
    "8c.b": {
        "question": "Why must you delete the endpoint even though the chunk table and documents are kept?",
        "model": "The endpoint is the compute that hosts the index and it bills for as long as it exists, whether or "
                 "not anyone queries it. The table is only stored data, and the index can be rebuilt from it.",
    },
    "9.a": {
        "question": "Why does the agent call tools through run_tool instead of calling the functions directly?",
        "model": "The decider's choice is untrusted: a model can name a tool that does not exist or send odd inputs. "
                 "run_tool enforces the allow-list and input checks and turns failures into messages, so a wrong "
                 "choice cannot do more than the tools permit.",
    },
    "9.b": {
        "question": "What can an agent do that the RAG answer in 8b cannot, and what extra risk does that bring?",
        "model": "An agent can choose among sources and act on live data, such as checking seat numbers, and combine "
                 "several steps. Because it acts, a wrong choice has consequences, so it needs limits, read-only or "
                 "approved tools, and a trace to review.",
    },
    "12.a": {
        "question": "Why is a registered model with an alias better than the notebook agent for other systems to use?",
        "model": "Other systems can call it by name without your notebook. Each release is a numbered, permissioned "
                 "version with a record of how it was built, the alias says which version is live, and moving the "
                 "alias is a controlled way to roll forward or back.",
    },
    "12.b": {
        "question": "What goes stale in a model that carries a snapshot, and how would you fix it?",
        "model": "The seat numbers and documents are frozen at the time of logging, so answers drift from reality. "
                 "Either log and release a new version on a schedule, or have the served agent read live data "
                 "through a governed connection, which needs its own authentication and access review.",
    },
    "11.a": {
        "question": "The app shows you as the viewer, yet its query runs as the app's service principal. Why does "
                    "the service principal, not you, need the grants?",
        "model": "The app code runs under its own identity and sends the query itself; the viewer's identity is "
                 "only passed along as a header for display. So the data access is whatever the service principal "
                 "holds, and everyone who opens the app sees what it can read, however limited their own access is.",
    },
    "11.b": {
        "question": "You share the app with a colleague who cannot read the bookings table. What do they see, and "
                    "why is that a design decision?",
        "model": "They see the seats-left view, because the app reads it as its own principal. Anything the app "
                 "can read is available to anyone allowed to open it, so grant it only the view it needs and "
                 "decide deliberately who can use the app.",
    },
    "14.a": {
        "question": "The new release passes the old five questions but its seat figures are a week old. Which "
                    "scorer catches it, and why would a judge that only reads the answer's wording miss it?",
        "model": "The grounded scorer, because it compares the number in the answer with the true seat count read "
                 "from the data. A wording judge sees a fluent, confident sentence and has nothing to check the "
                 "number against, so it would pass it.",
    },
    "14.b": {
        "question": "Why compare a candidate with a baseline run instead of setting a fixed pass mark?",
        "model": "A fixed mark hides regressions while the score stays above it, and fails a release for questions "
                 "that were already hard. Comparing with the baseline asks the useful question: did this change make "
                 "anything worse than what is running now?",
    },
    "15.a": {
        "question": "Why write the gate result and the evaluation run id on the model version, when the alias "
                    "already says which version is released?",
        "model": "The alias says what is released, not why. The tags say whether the version passed, what it was "
                 "compared with and which run proves it, so anyone can check or challenge the decision later "
                 "without asking the person who made it.",
    },
    "15.b": {
        "question": "Why is a rollback done by moving the alias instead of editing or deleting a version?",
        "model": "A version never changes, so the earlier one is exactly what was tested and is still there. Moving "
                 "the alias is instant, can be undone, and leaves a record of what was released and withdrawn. "
                 "Editing or deleting would destroy the evidence and the thing you want to return to.",
    },
    "13.a": {
        "question": "Why are bad rows kept in bronze but dropped from silver?",
        "model": "Bronze is the record of what arrived, so nothing is lost and a rule can be fixed and rerun. "
                 "Silver is what the business counts, so rows that should not be there must not be. Keeping both "
                 "also lets you measure how many rows were dropped and why.",
    },
    "13.b": {
        "question": "What does a declarative pipeline give you that rerunning a notebook does not?",
        "model": "It reads only new files, remembers what it has processed, orders the tables itself, records how "
                 "many rows passed each quality rule and can be run on a schedule with a history, so the result "
                 "does not depend on someone pressing run in the right order.",
    },
}


def get_reflection(reflection_id):
    try:
        return REFLECTIONS[reflection_id]
    except KeyError:
        raise KeyError(f"Unknown reflection {reflection_id!r}; choose from {', '.join(REFLECTIONS)}") from None
