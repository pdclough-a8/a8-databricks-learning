# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 1d. Decide what to do: overbooking and catering
# MAGIC **Where this sits:** prescriptive analytics, "what should we do?". It builds on the descriptive view from
# MAGIC Module 1b, the diagnostic work in Module 1c and the attendance predictions from Module 3.
# MAGIC
# MAGIC **Outcome:** turn uncertain attendance predictions into two decisions, how many tickets to sell for one
# MAGIC event (overbooking) and how many meals to order for it (catering). You simulate attendance, price the
# MAGIC mistakes, search for the cheapest choice and test how fragile that choice is. **A recommendation here is a
# MAGIC decision under stated assumptions. It is not a guarantee, and it is not a forecast of real money.**
# MAGIC
# MAGIC **60-75 minutes, an estimate:** orient 5 · assumptions 10 · overbooking 20 · catering 20 · exercises 10 ·
# MAGIC recap 10.
# MAGIC **Before you start:** finish `00_setup`, `01_lakehouse_data` and `03_predictive_ml` (it creates
# MAGIC `attendance_predictions` and `event_forecast`). All data is synthetic, frozen at **20 November 2026**.
# MAGIC
# MAGIC **Free Edition first, no cloud writes:** use Serverless compute. This notebook only reads two existing course
# MAGIC objects and holds results in memory. It creates no table, view, file, dashboard, endpoint or job, makes no
# MAGIC model request and needs no new library. Reads use compute quota. `99_pause_and_cleanup` is unchanged.
# MAGIC
# MAGIC ## 1. Two decisions, one source of uncertainty
# MAGIC Module 3 gives each confirmed booking a probability that it attends. A probability is not an answer: the
# MAGIC kitchen needs a number of meals and the box office needs a ticket limit. Both decisions have two ways to be
# MAGIC wrong.
# MAGIC
# MAGIC | Decision | Too high | Too low |
# MAGIC |---|---|---|
# MAGIC | **Overbooking:** tickets to sell for a fixed capacity | Attendees are turned away | Seats stay empty |
# MAGIC | **Catering:** meals to order for who will turn up | Meals are wasted | Attendees go without |
# MAGIC
# MAGIC The best choice balances the **expected cost** of both mistakes. Expected cost is the average over many
# MAGIC plausible turnouts, which is why we simulate them rather than use one forecast number.
# MAGIC
# MAGIC **Predict:** if turning someone away costs four times as much as an empty seat, will the best ticket limit be
# MAGIC at, above or below the venue capacity?

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the numeric and table libraries used for the simulation.
# LOOK FOR: no output; math, numpy and pandas ship with the Databricks runtime, so nothing is installed.
import math

import numpy as np
import pandas as pd

# COMMAND ----------

# WHAT: Check: stops here if the Module 3 prediction table or forecast view is missing.
# LOOK FOR: no output when both exist; otherwise a card naming the prerequisite notebook.
A8.require("attendance_predictions", "event_forecast")

# COMMAND ----------

# WHAT: resolves your validated names for the prediction table and the forecast view.
# LOOK FOR: no output; SQL copied into the SQL editor will use these real names.
predictions = A8.t("attendance_predictions")
event_forecast = A8.t("event_forecast")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Assumptions, written down first
# MAGIC A decision model is only as honest as its assumptions. These are ours, and each can be wrong.
# MAGIC
# MAGIC - **Costs are assumed teaching parameters.** The course has no payment ledger, so none of these figures is a
# MAGIC   real price, refund or supplier cost. Change them and the answer changes; that is the point of section 5.
# MAGIC - **Independence.** Each booking attends or not independently of every other booking, with the probability
# MAGIC   Module 3 scored. In reality friends and colleagues attend together, which widens the real spread.
# MAGIC - **Calibration.** We treat the model's probabilities as correct. Module 3 evidence is the limit of that trust.
# MAGIC - **Overbooking what-if.** Most scheduled events are far from full. We ask: *if this event sold up to a limit,
# MAGIC   and the extra buyers behaved like the current bookers, what limit is cheapest?* Late bookers may behave
# MAGIC   differently.
# MAGIC - **Catering uses existing bookings only.** Bookings not yet made are not in the prediction table, so re-run
# MAGIC   the decision as bookings arrive.
# MAGIC - **Humans decide.** Turning attendees away is a customer-fairness question that no cost table settles.

# COMMAND ----------

# WHAT: sets the event, the assumed costs and the simulation settings in one place.
# LOOK FOR: no output; change EVENT_ID to any scheduled event (E149 to E160) and rerun from here.
EVENT_ID = "E150"
COSTS = {"turned_away": 60.0, "empty_seat": 15.0, "short_meal": 8.0, "wasted_meal": 5.0}  # assumed, in pounds
RUNS, SEED = 10000, 2026  # a seed makes every learner's simulation repeatable

# COMMAND ----------

# WHAT: reads the forecast row for your event; the value goes in as a query parameter.
# LOOK FOR: capacity, confirmed tickets and expected attendees for one scheduled event.
forecast = spark.sql(f"SELECT * FROM {event_forecast} WHERE event_id = :event_id", args={"event_id": EVENT_ID}).first()
A8.expect(forecast is not None, f"{EVENT_ID} is not a scheduled event in your forecast view.")
A8.expect(forecast["confirmed_tickets"] > 0, f"{EVENT_ID} has no confirmed tickets, so there is nothing to predict.")
capacity = int(forecast["capacity"])
show_probability = forecast["expected_attendees"] / forecast["confirmed_tickets"]
print(f"{forecast['event_name']}: capacity {capacity}, {forecast['confirmed_tickets']} confirmed tickets,",
      f"expected attendees {forecast['expected_attendees']:.1f}, ticket show probability {show_probability:.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Overbooking: how many tickets should we sell?
# MAGIC If every ticket is attended with probability *p*, selling *L* tickets gives a random attendance near *L* × *p*.
# MAGIC The simple rule sells *capacity / p* tickets so that **average** attendance fills the room. It ignores the
# MAGIC spread, so on a quiet day seats stay empty and on a busy day people are turned away. A simulation prices both.
# MAGIC
# MAGIC For each candidate limit we draw many attendances and average the cost:
# MAGIC `turned_away x people over capacity + empty_seat x seats unfilled`.
# MAGIC We reuse one set of random draws for every limit (a trick called **common random numbers**), so the
# MAGIC comparison between limits is not blurred by different luck.

# COMMAND ----------

# WHAT: defines the seeded simulation of attendance for every ticket limit at once.
# LOOK FOR: no output; column k-1 holds attendance if k tickets had been sold, via a running total of shows.
def simulate_ticket_attendance(max_tickets, probability, runs, seed):
    rng = np.random.default_rng(seed)
    return (rng.random((runs, max_tickets)) < probability).cumsum(axis=1)

# COMMAND ----------

# WHAT: defines the expected cost of each limit and the cheapest limit.
# LOOK FOR: no output; costs are averages over the simulated attendances, one per candidate limit.
def optimise_overbooking(venue_capacity, probability, turned_away, empty_seat, runs=RUNS, seed=SEED):
    limits = np.arange(venue_capacity, int(1.5 * venue_capacity) + 1)
    attendance = simulate_ticket_attendance(int(limits.max()), probability, runs, seed)[:, limits - 1]
    over = np.maximum(attendance - venue_capacity, 0)
    empty = np.maximum(venue_capacity - attendance, 0)
    costs = (turned_away * over + empty_seat * empty).mean(axis=0)
    return limits, costs, limits[costs.argmin()]

# COMMAND ----------

# WHAT: finds the cheapest ticket limit for your event and compares it with the simple capacity / p rule.
# LOOK FOR: the best limit, its expected cost, and how far the simple rule's cost is from it.
limits, limit_costs, best_limit = optimise_overbooking(capacity, show_probability,
                                                       COSTS["turned_away"], COSTS["empty_seat"])
simple_limit = int(capacity / show_probability)
cost_of = pd.Series(limit_costs, index=limits)
print(f"Cheapest limit {best_limit} tickets, expected cost {cost_of[best_limit]:.1f} (assumed pounds)")
print(f"Simple rule {simple_limit} tickets, expected cost {cost_of.get(simple_limit, float('nan')):.1f}")

# COMMAND ----------

# WHAT: shows the expected cost curve around the best limit.
# LOOK FOR: a shallow bowl; neighbouring limits cost almost the same, so one ticket is not a precise instruction.
nearby = cost_of.loc[max(best_limit - 8, capacity): best_limit + 8]
display(pd.DataFrame({"ticket_limit": nearby.index, "expected_cost": nearby.round(2).values}))

# COMMAND ----------

# WHAT: defines the exact expected cost from the binomial formula, with no simulation.
# LOOK FOR: no output; this is the independent route to the same number the simulation estimates.
def exact_overbooking_cost(limit, venue_capacity, probability, turned_away, empty_seat):
    pmf = [math.comb(limit, k) * probability**k * (1 - probability) ** (limit - k) for k in range(limit + 1)]
    return sum(w * (turned_away * max(k - venue_capacity, 0) + empty_seat * max(venue_capacity - k, 0))
               for k, w in enumerate(pmf))

# COMMAND ----------

# WHAT: Check: the simulated cost at the best limit must be close to the exact binomial cost.
# LOOK FOR: a pass message; 10,000 draws leave a small sampling error, so we allow a few per cent.
exact = exact_overbooking_cost(int(best_limit), capacity, show_probability, COSTS["turned_away"], COSTS["empty_seat"])
A8.expect(abs(cost_of[best_limit] - exact) <= 0.05 * exact + 0.5,
          f"Simulated cost {cost_of[best_limit]:.2f} should be close to the exact cost {exact:.2f}.")

# COMMAND ----------

# MAGIC %md
# MAGIC **Pause and explain.** Why is the best limit above capacity, and why does the simple rule differ from it?
# MAGIC Which cost makes the best limit move closer to capacity?
# MAGIC
# MAGIC ## 4. What if the assumptions are wrong? Sensitivity
# MAGIC A recommendation that flips with small changes is weak. Two things we cannot know are the real cost ratio and
# MAGIC whether the model's probabilities are too hopeful or too cautious. We rerun the search over a small grid.

# COMMAND ----------

# WHAT: reruns the overbooking search over three cost ratios and three probability errors.
# LOOK FOR: the best limit for each pair; rows are the cost of turning someone away relative to an empty seat.
rows = []
for ratio in (1, 4, 8):
    row = {"turned_away_vs_empty": f"{ratio}x"}
    for shift in (-0.05, 0.0, 0.05):
        probability = min(max(show_probability + shift, 0.05), 0.95)
        row[f"p {shift:+.2f}"] = int(optimise_overbooking(capacity, probability, ratio * COSTS["empty_seat"],
                                                          COSTS["empty_seat"])[2])
    rows.append(row)
display(pd.DataFrame(rows))

# COMMAND ----------

# MAGIC %md
# MAGIC **Read the table.** Look at how much the limit moves along a row (probability error) and down a column (cost
# MAGIC ratio). If a five-point probability error moves the limit by many seats, the model is not precise enough to
# MAGIC justify a tight limit. Say which input you trust least and why.
# MAGIC
# MAGIC ## 5. Catering: how many meals should we order?
# MAGIC Catering uses each existing booking separately. A booking of *t* tickets attends together with probability *p*,
# MAGIC bringing *t* meals' worth of demand. Total turnout is the sum over bookings, and its **variance** is
# MAGIC `sum(t^2 x p x (1 - p))`: group bookings make turnout less predictable than the same number of single tickets.
# MAGIC The cheapest order is a quantile of the turnout distribution: with `short_meal` and `wasted_meal` costs, order
# MAGIC enough that turnout is at or below it with probability `short / (short + wasted)`. A simulation finds it by
# MAGIC search.

# COMMAND ----------

# WHAT: reads the latest prediction for each confirmed booking of your event.
# LOOK FOR: one row per booking with tickets and probability; older model versions are ignored, as in exercise 3.1.
bookings_frame = spark.sql(f"""WITH ranked AS (
SELECT p.*, row_number() OVER (
PARTITION BY booking_id ORDER BY scored_at DESC NULLS LAST, CAST(model_version AS INT) DESC
) AS score_rank FROM {predictions} p
)
SELECT booking_id, tickets, attendance_probability FROM ranked
WHERE event_id = :event_id AND score_rank = 1 ORDER BY booking_id""", args={"event_id": EVENT_ID}).toPandas()
print(len(bookings_frame), "bookings,", int(bookings_frame["tickets"].sum()), "tickets")

# COMMAND ----------

# WHAT: defines the seeded turnout simulation and the expected catering cost of each order size.
# LOOK FOR: no output; turnout is tickets times a yes/no draw per booking, summed for each simulated day.
def simulate_turnout(tickets, probabilities, runs, seed):
    rng = np.random.default_rng(seed)
    return (rng.random((runs, len(tickets))) < probabilities) @ tickets


def catering_costs(turnout, meals, short_meal, wasted_meal):
    gap = turnout[:, None] - meals[None, :]
    return (short_meal * np.maximum(gap, 0) + wasted_meal * np.maximum(-gap, 0)).mean(axis=0)

# COMMAND ----------

# WHAT: simulates turnout for your event and summarises it with percentiles, not just the mean.
# LOOK FOR: the 5th to 95th percentile range is the honest message; a single number hides the spread.
tickets = bookings_frame["tickets"].to_numpy(dtype=float)
probabilities = bookings_frame["attendance_probability"].to_numpy(dtype=float)
turnout = simulate_turnout(tickets, probabilities, RUNS, SEED)
low, middle, high = np.percentile(turnout, [5, 50, 95])
print(f"Turnout mean {turnout.mean():.1f}, median {middle:.0f}, 5th-95th percentile {low:.0f} to {high:.0f}")
analytic_sd = math.sqrt((tickets**2 * probabilities * (1 - probabilities)).sum())
print(f"Standard deviation {turnout.std():.2f}, analytic {analytic_sd:.2f}")

# COMMAND ----------

# WHAT: Check: the simulated mean and spread must match the exact mean and variance of the booking model.
# LOOK FOR: a pass message; both values come from the formulas above, not from the simulation.
exact_mean = float((tickets * probabilities).sum())
exact_variance = float((tickets**2 * probabilities * (1 - probabilities)).sum())
A8.expect(abs(turnout.mean() - exact_mean) < 0.5, "Simulated mean turnout must match sum(tickets x probability).")
A8.expect(abs(turnout.var() - exact_variance) < 0.1 * exact_variance + 0.5,
          "Simulated variance must match sum(tickets^2 x p x (1 - p)).")

# COMMAND ----------

# WHAT: searches every order size for the cheapest and compares it with two simple plans.
# LOOK FOR: the best order sits between the expected turnout and everyone attending; costs are assumed pounds.
meals = np.arange(0, int(tickets.sum()) + 1, dtype=float)
meal_costs = catering_costs(turnout, meals, COSTS["short_meal"], COSTS["wasted_meal"])
best_meals = int(meals[meal_costs.argmin()])
plans = {"cheapest": best_meals, "expected turnout": round(exact_mean), "one per ticket": int(tickets.sum())}
display(pd.DataFrame({"plan": list(plans), "meals": list(plans.values()),
                      "expected_cost": [round(float(meal_costs[m]), 2) for m in plans.values()]}))

# COMMAND ----------

# WHAT: Check: the search result must equal the quantile at the critical ratio, within one meal.
# LOOK FOR: a pass message; two routes to the same decision, one by search and one by theory.
ratio = COSTS["short_meal"] / (COSTS["short_meal"] + COSTS["wasted_meal"])
quantile_meals = float(np.quantile(turnout, ratio, method="inverted_cdf"))
A8.expect(abs(best_meals - quantile_meals) <= 1,
          f"Search found {best_meals} but the quantile rule says {quantile_meals}.")

# COMMAND ----------

# WHAT: reruns the catering search for four shortage costs and probabilities that are too high or too low.
# LOOK FOR: the cheapest order for each pair; probability shifts are scaled to stay between 0 and 1.
rows = []
for short in (2.0, 5.0, 8.0, 16.0):
    row = {"short_meal_cost": short}
    for scale in (0.9, 1.0, 1.1):
        shifted = np.clip(probabilities * scale, 0, 1)
        run = simulate_turnout(tickets, shifted, RUNS, SEED)
        row[f"p x {scale}"] = int(meals[catering_costs(run, meals, short, COSTS["wasted_meal"]).argmin()])
    rows.append(row)
display(pd.DataFrame(rows))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Checkpoint H1, human judgement
# MAGIC Write two or three sentences for each, in your own words. Nothing here is marked by a computer.
# MAGIC - **Overbooking:** who is turned away, how would they be told, and what makes a "turned away" cost of this size
# MAGIC   defensible or not? Would you cap the limit below the cheapest one?
# MAGIC - **Catering:** which mistake would your organisation rather make, and does that match the cost ratio above?
# MAGIC - **Evidence:** which assumption (independence, calibration, late bookers, costs) would you test first, and how?
# MAGIC
# MAGIC ## 6. Your turn
# MAGIC Both exercises read your own Module 3 objects and prepare inputs for these decisions in plain SQL.
# MAGIC - **Gap 1d.1:** for each scheduled event with bookings, the show probability and the simple overbooking limit.
# MAGIC - **Gap 1d.2:** for each scheduled event, the variance of turnout from the latest booking predictions.
# MAGIC - **Transfer:** pick another event, change one cost, and say whether the recommendation moves by more than the
# MAGIC   sampling noise (rerun with a different `SEED` to see that noise).
# MAGIC
# MAGIC Exercises use `IDENTIFIER(a8_event_forecast)` and `IDENTIFIER(a8_attendance_predictions)`. Blank answers reveal
# MAGIC hints; use `A8.solution("1d.2")` if stuck. A correct query plus an explanation, not just a green cell,
# MAGIC completes the task.

# COMMAND ----------

# WHAT: Check: compares your simple overbooking limit with the supplied answer.
# LOOK FOR: a hint for a blank answer, otherwise feedback; truncate to a whole number of tickets.
answer_1d_1 = """"""
A8.check("1d.1", answer_1d_1)

# COMMAND ----------

# WHAT: Check: compares your turnout variance with the supplied answer.
# LOOK FOR: a hint or feedback; using every score instead of the latest one per booking is deliberately wrong.
answer_1d_2 = """"""
A8.check("1d.2", answer_1d_2)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Pause, resume and clean up
# MAGIC Nothing was created, so there is nothing to delete. Stop querying and let serverless compute follow its idle
# MAGIC rules. `99_pause_and_cleanup` is unchanged by this module.
# MAGIC
# MAGIC ### Recap, explain before you move on
# MAGIC - Why does a good decision need the spread of outcomes and not only the expected attendance?
# MAGIC - What does the cost ratio decide, and why are the costs here assumed rather than measured?
# MAGIC - Which two checks agreed with the simulation, and why do independent routes matter?
# MAGIC - Which assumption would most change your recommendation if it were wrong?
# MAGIC
# MAGIC **Completion requires:** both exercises, the checks above, checkpoint H1 and your own explanations.
# MAGIC **Not covered:** reinforcement learning, solver libraries, live pricing, scheduled automation (Modules 6 and 8)
# MAGIC and any claim about real revenue or cost. **Next:** `02_governance`, enforce who can see what.
