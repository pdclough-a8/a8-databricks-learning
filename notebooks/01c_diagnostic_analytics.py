# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 1c. Diagnose a difference: why did it happen?
# MAGIC **Where this sits:** diagnostic analytics, why a difference exists. It builds on the descriptive view from
# MAGIC Module 1b; prediction is Module 3 and prescriptive analytics is planned separately.
# MAGIC
# MAGIC **Outcome:** explain why turnout or ratings differ between segments of events, say what is a pattern and
# MAGIC what would be a cause, and test whether a gap is bigger than chance. **Nothing in this notebook proves
# MAGIC causation.** Drill-downs, decompositions and tests describe and narrow the possible explanations. A cause needs
# MAGIC a designed comparison (for example a randomised change) or domain evidence this data does not contain.
# MAGIC
# MAGIC **60–75 minutes, an estimate:** orient 5 · drill down 15 · mix versus rate 15 · chance test 15 · Genie 10 ·
# MAGIC recap 10.
# MAGIC **Before you start:** finish `00_setup`, `01_lakehouse_data` and `01b_descriptive_analytics` (it creates
# MAGIC `event_metrics`). All data is synthetic, frozen at **20 November 2026**.
# MAGIC
# MAGIC **Free Edition first, no cloud writes:** use Serverless compute. This notebook only reads your existing
# MAGIC `event_metrics` view and holds results in memory. It creates no table, view, file, dashboard, endpoint or job.
# MAGIC Reads use compute quota. The optional Genie step asks a partner-powered AI to run SQL; do that only with your
# MAGIC workspace owner's approval, and an assisting agent must ask separately before any live work.
# MAGIC
# MAGIC ## 1. The question, and the difference between a pattern and a cause
# MAGIC Our case study: **completed online events have lower attendance than in-person and hybrid events. Why?**
# MAGIC
# MAGIC | Word | Meaning here |
# MAGIC |---|---|
# MAGIC | **Pattern** | Two things move together in the data: online events show lower attendance. |
# MAGIC | **Cause** | Changing one thing would change the other: moving an event online would lower its attendance. |
# MAGIC | **Mix** | The segments contain different kinds of events, for example more Leadership events online. |
# MAGIC | **Rate** | The same kind of event behaves differently in the two segments. |
# MAGIC | **Chance** | A gap this large could appear if segment labels meant nothing. |
# MAGIC
# MAGIC Our tools answer narrower questions: *where* is the gap, is it *mix or rate*, and is it *bigger than chance*?
# MAGIC All three can be true while the cause is still unknown. A lower online turnout might come from reminders,
# MAGIC audience, timing, price, the topics chosen or something we did not record. The data cannot choose between those.
# MAGIC
# MAGIC **Scope and units.** Attendance is the ticket-weighted proxy from Module 1b: attended tickets over tickets
# MAGIC with a
# MAGIC known outcome, completed events only. Ratings come from self-selected feedback. We compare **online** with
# MAGIC **not online** (in-person and hybrid). Scheduled events have no attendance outcome yet and are excluded.
# MAGIC
# MAGIC **Predict:** which topic do you expect to show the largest online gap, and would that be mix or rate?

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports numpy for the seeded permutation test later.
# LOOK FOR: no output; numpy ships with the Databricks runtime, so nothing is installed.
import numpy as np

# COMMAND ----------

# WHAT: Check: stops here if the Module 1b reporting view is missing.
# LOOK FOR: no output when it exists; otherwise a card naming the prerequisite notebook.
A8.require("event_metrics")

# COMMAND ----------

# WHAT: resolves your validated name for the reporting view.
# LOOK FOR: no output; SQL copied into the SQL editor will use this real name.
event_metrics = A8.t("event_metrics")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Drill down: where is the difference?
# MAGIC A drill-down repeats one descriptive question across the values of one dimension. The rule from Module 1b still
# MAGIC applies: add counts and sums, then divide, so a three-ticket event does not outweigh a three-hundred-ticket one.
# MAGIC The helper below holds the SQL for any of four dimensions and shows event counts so you can see how thin a
# MAGIC segment is. Small segments move a lot for no reason; a big gap in two events is a rumour, not a finding.

# COMMAND ----------

# WHAT: defines one drill-down query for turnout and ratings over a chosen dimension.
# LOOK FOR: no output; month uses substr because event_date is an ISO date and we want yyyy-MM.
DIMENSIONS = {"city": "city", "topic": "topic", "format": "format", "month": "substr(event_date, 1, 7)"}


def drill_down_sql(dimension):
    A8.expect(dimension in DIMENSIONS, f"Choose one of {sorted(DIMENSIONS)}.")
    expression = DIMENSIONS[dimension]
    return f"""SELECT {expression} AS segment, count(*) AS events,
sum(known_outcome_tickets) AS known_outcome_tickets,
round(100.0 * sum(attended_tickets) / nullif(sum(known_outcome_tickets), 0), 1) AS attendance_pct,
sum(feedback_count) AS feedback_count,
round(1.0 * sum(rating_sum) / nullif(sum(feedback_count), 0), 2) AS average_rating
FROM {event_metrics} WHERE event_status = 'completed'
GROUP BY {expression} ORDER BY {expression}"""

# COMMAND ----------

# WHAT: drills down by format, the dimension behind our question.
# LOOK FOR: online attendance clearly below in-person and hybrid, with 15 online events behind it.
display(spark.sql(drill_down_sql("format")))

# COMMAND ----------

# WHAT: drills down by city, which overlaps with format.
# LOOK FOR: Online is both a city and a format, so these two dimensions cannot be separated in this data.
display(spark.sql(drill_down_sql("city")))

# COMMAND ----------

# WHAT: drills down by topic.
# LOOK FOR: topics differ in attendance and ratings, so topic is a candidate for mix.
display(spark.sql(drill_down_sql("topic")))

# COMMAND ----------

# WHAT: drills down by month.
# LOOK FOR: jagged results from one to three events a month; ask which wiggles you would trust.
display(spark.sql(drill_down_sql("month")))

# COMMAND ----------

# MAGIC %md
# MAGIC **Pause and explain.** Which of these tables describes a pattern you would act on, and which is too thin?
# MAGIC Why can you not compare city with format as separate explanations here? A pattern in one cut can disappear
# MAGIC in another, which is why the next section asks whether the *composition* of each segment explains the gap.
# MAGIC
# MAGIC ## 3. Mix versus rate: is it the kind of events, or how they behave?
# MAGIC The online gap in attendance can arise two ways. If online has a larger share of a low-attendance topic, that
# MAGIC is a
# MAGIC **mix** effect. If the same topic attends worse online than offline, that is a **rate** effect. The split below
# MAGIC compares the segments topic by topic. For each topic, with shares *w* (a topic's part of that segment's
# MAGIC known-outcome tickets) and rates *r* (attendance within that topic and segment):
# MAGIC
# MAGIC - **mix** = (w online − w other) × average of the two rates
# MAGIC - **rate** = (r online − r other) × average of the two shares
# MAGIC
# MAGIC The two effects, summed over topics, add up **exactly** to the total gap. Using the averages of the two
# MAGIC segments removes the arbitrary choice of which segment is the baseline. This is arithmetic about this data. It
# MAGIC does not say that changing a segment's mix would change attendance.

# COMMAND ----------

# WHAT: defines the mix-versus-rate query for a weight column and a total column.
# LOOK FOR: no output; scale 100 gives percentage points, 1 keeps rating points.
def decomposition_sql(weight, total, scale, digits, by_topic):
    cells = f"""WITH cells AS (
  SELECT CASE WHEN format = 'online' THEN 'online' ELSE 'other' END AS segment, topic,
    sum({weight}) AS n, sum({total}) AS s
  FROM {event_metrics} WHERE event_status = 'completed'
  GROUP BY CASE WHEN format = 'online' THEN 'online' ELSE 'other' END, topic
), shares AS (
  SELECT c.topic, c.segment, 1.0 * c.n / t.total AS share, 1.0 * c.s / nullif(c.n, 0) AS rate
  FROM cells c JOIN (SELECT segment, sum(n) AS total FROM cells GROUP BY segment) t
    ON c.segment = t.segment
), paired AS (
  SELECT o.topic, o.share AS o_share, p.share AS p_share, o.rate AS o_rate, p.rate AS p_rate,
    (o.share - p.share) * (o.rate + p.rate) / 2 AS mix,
    (o.rate - p.rate) * (o.share + p.share) / 2 AS rate
  FROM shares o JOIN shares p ON o.topic = p.topic
  WHERE o.segment = 'online' AND p.segment = 'other'
)"""
    if by_topic:
        return cells + f"""
SELECT topic, round({scale} * o_share, {digits}) AS online_share, round({scale} * p_share, {digits}) AS other_share,
round({scale} * o_rate, {digits}) AS online_rate, round({scale} * p_rate, {digits}) AS other_rate,
round({scale} * mix, {digits}) AS mix_effect, round({scale} * rate, {digits}) AS rate_effect
FROM paired ORDER BY topic"""
    return cells + f"""
SELECT round({scale} * sum(mix), {digits}) AS mix_effect, round({scale} * sum(rate), {digits}) AS rate_effect,
round({scale} * sum(mix + rate), {digits}) AS total_gap
FROM paired"""

# COMMAND ----------

# WHAT: prepares the attendance split by topic and in total, in percentage points.
# LOOK FOR: no output; weight is known_outcome_tickets and the rate is attended over known tickets.
attendance_by_topic_sql = decomposition_sql("known_outcome_tickets", "attended_tickets", 100, 1, True)
attendance_total_sql = decomposition_sql("known_outcome_tickets", "attended_tickets", 100, 1, False)

# COMMAND ----------

# WHAT: shows each topic's shares, rates and contributions to the online attendance gap.
# LOOK FOR: shares are percentages of each segment's tickets; rates are attendance percentages; effects are points.
display(spark.sql(attendance_by_topic_sql))

# COMMAND ----------

# WHAT: shows the total split of the online attendance gap into mix and rate.
# LOOK FOR: mix_effect + rate_effect equals total_gap; compare the size of each part.
display(spark.sql(attendance_total_sql))

# COMMAND ----------

# WHAT: Check: confirms the two effects add up to the directly computed overall attendance gap.
# LOOK FOR: a pass message; a mismatch means the split dropped or double-counted something.
overall_gap = spark.sql(f"""SELECT round(100.0 * (
  1.0 * sum(CASE WHEN format = 'online' THEN attended_tickets END)
    / sum(CASE WHEN format = 'online' THEN known_outcome_tickets END)
  - 1.0 * sum(CASE WHEN format <> 'online' THEN attended_tickets END)
    / sum(CASE WHEN format <> 'online' THEN known_outcome_tickets END)), 1) AS gap_pp
FROM {event_metrics} WHERE event_status = 'completed'""").first()[0]
split = spark.sql(attendance_total_sql).first()
A8.expect(abs(split["total_gap"] - overall_gap) < 0.05,
          "The mix and rate effects must add up to the overall attendance gap.")
A8.expect(abs(split["mix_effect"] + split["rate_effect"] - split["total_gap"]) < 0.15,
          "Rounded mix and rate effects must match the total gap to rounding.")

# COMMAND ----------

# MAGIC %md
# MAGIC **Read the split.** A large rate effect with a small mix effect says online events attend worse even when
# MAGIC compared topic by topic, so the topic mix does not explain the gap. Look at the by-topic table to see which
# MAGIC topics
# MAGIC carry it. That narrows the search; it does not name the reason. Reasons that could fit a rate effect include
# MAGIC lower commitment to free-to-leave sessions, calendar clashes or joining problems. The data records none of them.
# MAGIC
# MAGIC The same split works for ratings: set the weight to `feedback_count` and the total to `rating_sum`.
# MAGIC That is exercise 1c.2. Ratings come from respondents only, so a ratings gap may reflect who answers.
# MAGIC
# MAGIC ## 4. Is the gap bigger than chance? A permutation test
# MAGIC Each event is one unit: tickets within an event share a venue, topic and date, so we shuffle whole events, not
# MAGIC tickets. The test asks: if the online/not-online label were unrelated to attendance, how often would shuffled
# MAGIC labels give a gap at least as large as the one we saw, in either direction?
# MAGIC
# MAGIC 1. Compute the observed gap: online ticket-weighted attendance minus not-online.
# MAGIC 2. Shuffle which events are labelled online, keeping 15 online and the rest not online.
# MAGIC 3. Recompute the gap for each shuffle. Repeat many times with a **seed** so your result is repeatable.
# MAGIC 4. The **p-value** is the share of shuffles at least as extreme as the observed gap, counting the observed
# MAGIC    arrangement itself as one (count + 1) / (shuffles + 1), so it is never exactly zero.
# MAGIC
# MAGIC A small p-value says the gap is hard to explain by label-shuffling alone. It says nothing about *why*.
# MAGIC It assumes events are comparable units; it does not remove mix, and it is not the probability that online
# MAGIC causes lower attendance. A large p-value would not prove there is no difference, only that this data is
# MAGIC not enough to rule out chance. We use numpy only, with no statistics library.

# COMMAND ----------

# WHAT: reads one row per completed event with a known attendance outcome, as a small pandas frame.
# LOOK FOR: 48 completed events, 15 of them online; toPandas is fine for a frame this small.
events_frame = spark.sql(f"""SELECT event_id, CASE WHEN format = 'online' THEN 1 ELSE 0 END AS is_online,
known_outcome_tickets AS known, coalesce(attended_tickets, 0) AS attended
FROM {event_metrics} WHERE event_status = 'completed' AND known_outcome_tickets > 0
ORDER BY event_id""").toPandas()
print(len(events_frame), "events,", int(events_frame["is_online"].sum()), "online")

# COMMAND ----------

# WHAT: defines the seeded permutation test for a ticket-weighted gap.
# LOOK FOR: no output; the function returns the observed gap and a two-sided p-value.
def permutation_test(known, attended, is_online, permutations=10000, seed=2026):
    known, attended = np.asarray(known, dtype=float), np.asarray(attended, dtype=float)
    labels = np.asarray(is_online, dtype=bool)
    rng = np.random.default_rng(seed)

    def gap(online):
        return attended[online].sum() / known[online].sum() - attended[~online].sum() / known[~online].sum()

    observed = gap(labels)
    # The small tolerance stops floating-point noise from hiding an exact tie.
    as_extreme = sum(abs(gap(rng.permutation(labels))) >= abs(observed) - 1e-12 for _ in range(permutations))
    return observed, (as_extreme + 1) / (permutations + 1)

# COMMAND ----------

# WHAT: Check: tests the function on a case you can count by hand before trusting it on real data.
# LOOK FOR: three online events all attended and three others none attended; 2 of 20 arrangements are this extreme,
# so p is near 0.10.
small_gap, small_p = permutation_test([10] * 6, [10, 10, 10, 0, 0, 0], [1, 1, 1, 0, 0, 0], permutations=4000)
A8.expect(small_gap == 1.0 and 0.05 < small_p < 0.16,
          "A perfectly separated 3 v 3 case must give a gap of 1 and p close to 2/20.")

# COMMAND ----------

# WHAT: runs the test on the real completed events, seeded so every learner gets the same answer.
# LOOK FOR: observed gap in attendance points and a p-value; rerunning gives identical numbers.
observed_gap, p_value = permutation_test(events_frame["known"], events_frame["attended"], events_frame["is_online"])
print(f"Observed gap (online minus not online): {100 * observed_gap:.1f} percentage points")
print(f"Two-sided permutation p-value, 10,000 shuffles, seed 2026: {p_value:.4f}")

# COMMAND ----------

# WHAT: Check: confirms the test's observed gap equals the SQL gap from section 3.
# LOOK FOR: a pass message; two routes to the same number is the point.
A8.expect(abs(100 * observed_gap - overall_gap) < 0.05,
          "The permutation test's observed gap must equal the SQL attendance gap.")

# COMMAND ----------

# MAGIC %md
# MAGIC **Interpret it in one honest sentence.** For example: "Online events attended about N points lower, which
# MAGIC label-shuffling
# MAGIC rarely matches (p ≈ …), and topic mix explains only part of it; we do not know why." Then say what you would
# MAGIC need to learn the cause: for instance, randomly sending reminders to half of an online audience and comparing
# MAGIC turnout.
# MAGIC
# MAGIC ## 5. Ask a "why" question of the dashboard and Genie
# MAGIC Use the Module 1b dashboard and Genie space you already built; do not create new ones here. Both are
# MAGIC learner-triggered. Genie questions consume quota and invoke AI, so ask only with approval, once, in a new chat.
# MAGIC
# MAGIC **Dashboard (no AI):** filter **Event status** to completed and **City** to Online, then to each other city
# MAGIC in turn.
# MAGIC The table shows fill rate and ratings per event. Note what it can show (a pattern) and what it cannot (why).
# MAGIC The dashboard has no attendance widget, so compare with the drill-down above instead of trusting a glance.
# MAGIC
# MAGIC **Genie:** ask the question below. Then open the generated SQL and compare it with the reference result. Genie's
# MAGIC instructions from Module 1b say not to infer causes; instructions guide but do not guarantee behaviour.
# MAGIC Things to check, as likely failure modes rather than observed results:
# MAGIC - Does it average event-level attendance percentages instead of summing tickets first?
# MAGIC - Does it include scheduled events, where attendance is unknown, as if they were zero?
# MAGIC - Does it count bookings rather than tickets, or compare cities as if they were independent of format?
# MAGIC - Does it state a cause ("people forget online events") as fact? Reject that; the data cannot show it.
# MAGIC - Does it report a gap without event counts, or call a handful of events a trend?
# MAGIC - Does it correctly say a difference is **not** shown to be caused by format?

# COMMAND ----------

# WHAT: prints the why question and the reference SQL to compare Genie's generated code against.
# LOOK FOR: the question for a new Genie chat; the table below is the answer to the descriptive half only.
genie_why_question = "Why is attendance lower for online events than for in-person events? Show the evidence."
reference_sql = drill_down_sql("format")
print("Ask Genie once:", genie_why_question)
print(reference_sql)
display(spark.sql(reference_sql))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Checkpoint G2, record what you observed
# MAGIC With approval, record for the one question: whether the SQL read only `event_metrics`, filtered to completed
# MAGIC events,
# MAGIC summed tickets before dividing, matched the reference table, and whether the prose invented a cause or forecast.
# MAGIC Record pass, fail or blocked for each, with a short redacted note. Do not store raw conversations or personal
# MAGIC workspace paths in the repository. A correct table with an invented explanation is still a failure.
# MAGIC If you skipped Genie, label this checkpoint blocked; the SQL work above still stands.
# MAGIC
# MAGIC ## 6. Your turn
# MAGIC - **Gap 1c.1:** for each topic, the online-minus-not-online attendance gap in points. Hint: conditional sums.
# MAGIC - **Gap 1c.2:** split the rating gap into mix and rate effects, as section 3 did for attendance.
# MAGIC - **Transfer:** pick another segment pair (for example Leeds hybrid against the rest, or the first half of
# MAGIC   2025 against the second), drill down, state its event counts, and say whether you would bother to test it.
# MAGIC
# MAGIC Exercises use this notebook's `IDENTIFIER(a8_event_metrics)`. Blank answers reveal hints; use
# MAGIC `A8.solution("1c.2")` if stuck. A correct query plus an explanation, not just a green cell, completes the task.

# COMMAND ----------

# WHAT: Check: compares your per-topic attendance gap with the supplied answer.
# LOOK FOR: a hint for a blank answer, otherwise feedback; averaging per-event rates is deliberately wrong.
answer_1c_1 = """"""
A8.check("1c.1", answer_1c_1)

# COMMAND ----------

# WHAT: Check: compares your rating-gap split with the supplied answer.
# LOOK FOR: a hint or feedback; the two effects and the total must each match to two decimals.
answer_1c_2 = """"""
A8.check("1c.2", answer_1c_2)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Pause, resume and clean up
# MAGIC Nothing was created, so there is nothing to delete. Stop querying and let serverless compute follow its idle
# MAGIC rules.
# MAGIC Any Genie chat you started belongs to your own space; delete it from that space only if you want it gone, by
# MAGIC checking it is yours first. `99_pause_and_cleanup` is unchanged by this module.
# MAGIC
# MAGIC ### Recap, explain before you move on
# MAGIC - What is the difference between a pattern and a cause? What would you need to claim a cause?
# MAGIC - Why can the gap be mostly rate or mostly mix, and what does each tell you to look at next?
# MAGIC - Why shuffle whole events rather than tickets? What does a small p-value not tell you?
# MAGIC - Which Genie answer would you reject, even if its numbers were right?
# MAGIC
# MAGIC **Completion requires:** both exercises, the checks above, checkpoint G2 (or marked blocked), and your own
# MAGIC explanations. **Not covered:** adjusting for several confounders at once and Simpson's paradox are deferred.
# MAGIC **Next:** `02_governance`, enforce who can see what. Prescriptive analytics (`01d`) follows Module 3.
