# 1. Trust the data

**Outcome:** answer "Which Leeds events have places left?" with evidence you can check.
Start with [readiness](../start.md) complete and the six-row CSV available.
You finish with one marked table, a query and a short explanation.

## Understand the move

A catalog contains schemas; a schema contains tables. A table stores records.
A query selects the records needed for a question. Here `remaining = capacity - booked`.
That arithmetic tells us availability in a fixed snapshot, not future attendance.
We check this before asking a model, because fluent prose cannot repair bad source data.

## Follow the worked example

=== "UI-led, supplied SQL"

    1. In Catalog Explorer, open your assigned schema. Check that your exact table name is absent.
    2. Choose **Create table / Create or modify table > Upload files** (labels vary). Select `events.csv`.
    3. Check the header and six preview rows. Set capacity/booked to integer numeric types,
       the other columns to strings. Use your exact `a8learn_YOUR_TAG_events` name.
    4. Create the table, never replace an existing one. On the newly created table's overview,
       edit its comment to your exact readiness marker. If comments cannot be edited there,
       ask the instructor rather than changing another object's metadata.
    5. Open a SQL editor query attached to your approved warehouse. Replace the full table name below
       with yours and run. Save the query in your personal area.

    ```sql
    SELECT event_id, event_name, city, capacity - booked AS remaining
    FROM YOUR_CATALOG.YOUR_SCHEMA.a8learn_YOUR_TAG_events
    WHERE city = 'Leeds'
    ORDER BY event_id;
    ```

    If you return after an interruption, inspect the existing table's comment, columns and all six rows.
    Reuse only your marked, unchanged fixture. Never upload into it again or choose append.

=== "Code-first, supplied notebook"

    1. Open `notebooks/01_explore_events`. Run setup with the same widget values as readiness.
    2. Inspect the printed table and marker. Read the **Create once, reuse safely** explanation.
    3. Set `CREATE_MY_TABLE = True`, run that cell once, then reset it to `False`.
    4. The helper creates the table and data in one Delta operation. Reruns verify the exact fixture
       and marker; they don't append or overwrite. Existing altered data stops the lesson.
    5. Run **Worked example** and compare the output below.

| Event | Capacity | Booked | Remaining |
|---|---:|---:|---:|
| E101, Analytics Breakfast | 60 | 42 | 18 |
| E104, Analytics Clinic | 40 | 18 | 22 |

**Stop and explain:** why is `remaining` derived rather than copied from an unsupported source?
Which source columns would you inspect if an answer said E101 had 28 places?

## Make one change

Predict first. Duplicate the query and change only Leeds to Manchester.
Expect E102 with 3 places and E106 with 15. Save both versions so you can compare.

## Complete a gap

Add a second condition so the Manchester query returns only events with fewer than ten places:

```sql
WHERE city = 'Manchester' AND ___
```

Hint: compare the same arithmetic expression with 10.

??? note "Show the solution after trying"

    Use `capacity - booked < 10`. Expect **only E102, remaining 3**.
    The complete code route is in `solutions/01_data.py`.

## Transfer without copying

Write a new query for Bristol availability. Check it against the CSV and explain why bookings
do not establish future attendance. Expected fact after your attempt: E105 has 5 places remaining.

**Checkpoint:** keep your changed query, gap result and explanation in your [progress note](../progress.md).
Passing means the numbers match, not merely that the query ran.
The app later reads this same CSV fixture, **not this table**.
Continue to [lesson 2](02-model.md), or [pause](../operations.md).

## If you're stuck

- Missing schema or permission: stop and confirm the assigned destination. Do not create a replacement schema.
- Unexpected counts or values: inspect the file/header/types. Do not overwrite a table to clear an error.
- Ownership mismatch: use a new instructor-approved tag or investigate whose object it is.
- Code route fails after UI upload: verify all five columns, numeric types and marker. Preserve any learner changes.
