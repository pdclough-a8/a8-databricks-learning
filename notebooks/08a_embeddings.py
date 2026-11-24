# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 8a. Embeddings: find comments by meaning
# MAGIC **Where this sits:** supports descriptive analytics (what are attendees saying?) and is the foundation for
# MAGIC retrieval-augmented generation (RAG) in `08b_rag`. An embedding does not predict anything or explain why.
# MAGIC
# MAGIC **Outcome:** turn event feedback comments into **vectors** (lists of numbers), measure how close two comments
# MAGIC are, and search for comments by meaning instead of by exact words. You first build vectors **by hand** so you
# MAGIC can see how they work, then use a real **embedding model** and compare the two.
# MAGIC
# MAGIC **About 60 minutes, an estimate:** orient 10 · keyword search 10 · vectors by hand 15 · real embeddings 15 ·
# MAGIC exercises 5 · recap 5.
# MAGIC **Before you start:** finish `00_setup` and `01_lakehouse_data`; only the `feedback` table is needed.
# MAGIC All data is synthetic, frozen at **20 November 2026**. Never substitute personal or customer data.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. Everything except the real-embedding step needs no
# MAGIC model at all. If that step is blocked by a quota or a missing endpoint, finish the rest, then repeat the
# MAGIC step in your paid workspace after running `00_setup` and `01_lakehouse_data` there.
# MAGIC
# MAGIC **Cost boundary:** the real-embedding step sends **30 short synthetic texts** to one embedding endpoint,
# MAGIC behind a default-no switch. It writes nothing. Inference uses quota on Free and can cost money on a paid
# MAGIC workspace, so ask before you approve it there. Nothing here has been live validated yet.
# MAGIC
# MAGIC ## Embeddings in plain English
# MAGIC After each event, attendees leave comments. The events manager asks: *show me everything people said about the
# MAGIC room being uncomfortable.* Searching for the word "uncomfortable" finds one comment. But "The room was too warm
# MAGIC and quite cramped" is the same complaint in different words, and a word search will miss it.
# MAGIC
# MAGIC An **embedding model** reads a piece of text and returns a **vector**: a list of numbers, often about a thousand
# MAGIC of them. The model is trained so that texts with similar meaning get similar vectors. You can then measure how
# MAGIC close two vectors are and search by **meaning**. This is the idea behind **semantic search** and behind the
# MAGIC retrieval step of RAG, where a question is embedded and the closest passages of a document are fetched.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **Vector** | a list of numbers; here, one list per piece of text |
# MAGIC | **Embedding** | the vector an embedding model returns for a piece of text |
# MAGIC | **Dimension** | how many numbers are in the vector, for example 1,024 |
# MAGIC | **Cosine similarity** | how closely two vectors point the same way: 1 is the same direction, 0 is unrelated |
# MAGIC | **Keyword search** | finding text that contains the exact words you typed |
# MAGIC | **Semantic search** | finding text whose meaning is close to your query, even with different words |
# MAGIC | **Bag of words** | a simple vector that just counts which words appear; no model, no meaning |
# MAGIC | **Distinct comment** | one unique sentence; many feedback rows repeat the same sentence |
# MAGIC
# MAGIC **Business question for this lesson:** *which comments are about the stream, the room or the food, even when
# MAGIC they use different words, and how are those rated?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Foundation Model APIs](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/)
# MAGIC - [ai_query](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_query)
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; numpy does the vector arithmetic and sql_string quotes a text safely for SQL.
import re

import numpy as np
from a8learn import sql_string
from databricks.sdk import WorkspaceClient

# COMMAND ----------

# WHAT: checks the Module 1 prerequisite and resolves the names this lesson uses.
# LOOK FOR: one Ready line naming your feedback table and the embedding endpoint.
A8.require("feedback")
feedback = A8.t("feedback")
# The default is the embedding endpoint saved by 00_setup. Change it only to another endpoint in your Serving page.
EMBEDDING_ENDPOINT = A8.cfg.embedding_model or "databricks-gte-large-en"
print(f"Ready | {feedback} | embedding endpoint: {EMBEDDING_ENDPOINT}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. The data: 395 comments, but how many different sentences?
# MAGIC Feedback is a table with one row per comment. Because the data is synthetic, many rows repeat the same
# MAGIC sentence. A model call costs quota, so we embed each **distinct** comment once and look up the rest by text.
# MAGIC That is also good practice with real data: do not pay to embed the same text twice.
# MAGIC
# MAGIC **Predict:** how many distinct comments do you expect among 395 rows? Run the next cell to find out.

# COMMAND ----------

# WHAT: counts each distinct comment, how often it appears and its average rating.
# LOOK FOR: a short table; some sentences appear dozens of times, a few only once.
display(spark.sql(f"""SELECT comment, count(*) AS n, round(avg(rating), 2) AS average_rating
FROM {feedback} GROUP BY comment ORDER BY n DESC, comment"""))

# COMMAND ----------

# WHAT: loads the distinct comments into Python lists for the rest of the lesson.
# LOOK FOR: no output; comments, counts and average ratings line up by position.
comment_rows = spark.sql(f"""SELECT comment, count(*) AS n, avg(rating) AS average_rating
FROM {feedback} GROUP BY comment ORDER BY comment""").collect()
comments = [row["comment"] for row in comment_rows]
counts = [row["n"] for row in comment_rows]
ratings = [float(row["average_rating"]) for row in comment_rows]

# COMMAND ----------

# WHAT: Check: confirms the number of distinct comments and that every feedback row is accounted for.
# LOOK FOR: two pass messages; a failure means the feedback table differs from the course data.
A8.expect(len(comments) == 27, "The course feedback has 27 distinct comments.")
A8.expect(sum(counts) == 395, "The distinct comments account for all 395 feedback rows.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Keyword search, and where it fails
# MAGIC The simplest search is a keyword search: keep the comments that contain the word you typed.
# MAGIC
# MAGIC **Predict:** which of these searches will find nothing? `uncomfortable`, `audio`, `hot`, `video`, `food`.
# MAGIC The comments say things like "Audio dropped out", "The room was too warm" and "Good coffee and a decent lunch".

# COMMAND ----------

# WHAT: defines a keyword search over the distinct comments.
# LOOK FOR: no output; the function returns every comment containing the word, ignoring capital letters.
def keyword_search(term):
    return [c for c in comments if term.lower() in c.lower()]

# COMMAND ----------

# WHAT: runs five keyword searches and shows how many comments each finds.
# LOOK FOR: some words find one comment, others find none, although comments about them exist.
for term in ["uncomfortable", "audio", "hot", "video", "food"]:
    print(f"{term!r}: {len(keyword_search(term))} found", keyword_search(term))

# COMMAND ----------
# MAGIC %md
# MAGIC `hot`, `video` and `food` find nothing, yet "The room was too warm and quite cramped", the stream comments and
# MAGIC the lunch and coffee comments exist. A person would match them at once. A keyword search needs the exact word.
# MAGIC
# MAGIC ## 3. Vectors by hand: counting words
# MAGIC Before any model, here is the simplest possible vector. List every word used across all comments (the
# MAGIC **vocabulary**). Then a comment becomes one number per vocabulary word: how many times that word appears.
# MAGIC This is a **bag of words**. Two comments that share many words get similar vectors.

# COMMAND ----------

# WHAT: splits text into lower-case words and drops very common words that carry little meaning.
# LOOK FOR: no output; try tokenise("The stream kept buffering.") in a new cell to see the words kept.
STOP_WORDS = {"the", "a", "an", "was", "were", "and", "to", "of", "i", "my", "with", "at", "for", "in", "on", "it",
              "is", "that", "than", "before", "from", "by", "very", "kept", "could", "can", "all", "out", "would",
              "have", "liked", "more", "too"}


def tokenise(text):
    return [w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP_WORDS]

# COMMAND ----------

# WHAT: builds the vocabulary and turns every comment into a count vector.
# LOOK FOR: the vocabulary size and the vector length; one number per vocabulary word.
vocabulary = sorted({w for c in comments for w in tokenise(c)})
position = {w: i for i, w in enumerate(vocabulary)}


def count_vector(text):
    vector = np.zeros(len(vocabulary))
    for w in tokenise(text):
        if w in position:
            vector[position[w]] += 1
    return vector

toy_vectors = np.array([count_vector(c) for c in comments])
print(f"{len(vocabulary)} words in the vocabulary; each comment is a vector of length {toy_vectors.shape[1]}.")

# COMMAND ----------
# MAGIC %md
# MAGIC **Cosine similarity** compares two vectors by the angle between them, ignoring how long the comments are.
# MAGIC It is 1 for the same direction and 0 when the vectors share nothing. The formula is the dot product divided
# MAGIC by the product of the lengths.

# COMMAND ----------

# WHAT: defines cosine similarity and a helper that ranks comments by closeness to a query vector.
# LOOK FOR: no output; most_similar returns (score, comment) pairs, best first.
def cosine(a, b):
    length = np.linalg.norm(a) * np.linalg.norm(b)
    return 0.0 if length == 0 else float(a @ b / length)


def most_similar(query_vector, vectors, k=3, skip=None):
    scored = [(cosine(query_vector, v), c) for c, v in zip(comments, vectors, strict=True) if c != skip]
    return sorted(scored, reverse=True)[:k]

# COMMAND ----------

# WHAT: Check: a comment is perfectly similar to itself and a comment with no shared words scores zero.
# LOOK FOR: two pass messages that confirm the cosine function behaves as described.
first = toy_vectors[0]
A8.expect(abs(cosine(first, first) - 1.0) < 1e-9, "A comment has cosine similarity 1 with itself.")
A8.expect(cosine(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == 0.0, "Vectors sharing nothing score 0.")

# COMMAND ----------
# MAGIC %md
# MAGIC **Predict:** which comment is closest to "The stream kept buffering."? Is it about the same problem?

# COMMAND ----------

# WHAT: finds the comments closest to a stream complaint using the bag-of-words vectors.
# LOOK FOR: the top match shares the word "stream" but praises the stream; "Audio dropped out" scores 0.
query = "The stream kept buffering."
for score, comment in most_similar(count_vector(query), toy_vectors, k=3, skip=query):
    print(f"{score:.2f}  {comment}")
print("Audio comment:", round(cosine(count_vector(query), count_vector("Audio dropped out several times online.")), 2))

# COMMAND ----------
# MAGIC %md
# MAGIC The bag of words matched on the shared word **stream** and ranked the *positive* comment first. It scored the
# MAGIC audio complaint, the same kind of problem, at 0 because it shares no word. Counting words cannot see meaning.
# MAGIC An embedding model is trained on huge amounts of text, so it can place "buffering" and "audio dropped out" close
# MAGIC together even with no shared word.
# MAGIC
# MAGIC ## 4. Real embeddings with a Databricks model
# MAGIC Databricks hosts embedding models as **Foundation Model API** endpoints. `ai_query` is a SQL function that sends
# MAGIC text to an endpoint and returns the vector as an array of numbers. We send the 27 distinct comments plus three
# MAGIC search phrases that a manager might type. That is 30 short requests in one query, and nothing is written.
# MAGIC
# MAGIC **If the endpoint is not found:** open **Serving** in your workspace, find an endpoint whose type is embeddings
# MAGIC (for example `databricks-gte-large-en`), and put its exact name in `EMBEDDING_ENDPOINT` above. Do not create an
# MAGIC endpoint. **Undo:** nothing is created, so there is nothing to undo.

# COMMAND ----------

# WHAT: defines the three search phrases and the 30 texts to embed, with parameters so text stays out of the SQL.
# LOOK FOR: no output; the query sends only these texts, never ratings, ids or personal fields.
probes = ["too hot and uncomfortable seating", "audio and video problems online", "food and drink"]
texts = comments + probes
values = ", ".join(f"(:t{i})" for i in range(len(texts)))
embedding_args = {f"t{i}": t for i, t in enumerate(texts)}
print(f"{len(texts)} texts to embed: {len(comments)} comments and {len(probes)} search phrases.")

# COMMAND ----------

# WHAT: asks for your approval before any model request.
# LOOK FOR: an embed_comments widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
embed_approved = A8.gate("embed_comments", "Embed 30 short synthetic texts (cost/quota)?")
print("Approved." if embed_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: sends the approved texts to the embedding endpoint once and keeps the vectors in memory.
# LOOK FOR: no output if approved; otherwise a message that the step was skipped. Do not retry errors in a loop.
embeddings = None
if embed_approved:
    embedded = spark.sql(f"""SELECT text, ai_query({sql_string(EMBEDDING_ENDPOINT)}, text) AS embedding
FROM VALUES {values} AS input(text)""", args=embedding_args).collect()
    embeddings = {row["text"]: np.array(row["embedding"], dtype=float) for row in embedded}
else:
    print("Embedding skipped. The sections that need real vectors will say so; the exercises still work.")

# COMMAND ----------

# WHAT: Check: every text has a vector of the same length with finite numbers.
# LOOK FOR: pass messages and the vector length, or a note that the step was skipped.
if embeddings is not None:
    lengths = {len(v) for v in embeddings.values()}
    A8.expect(len(embeddings) == len(texts), "Every text received an embedding.")
    A8.expect(len(lengths) == 1 and lengths != {0}, "All embeddings have the same non-zero length.")
    A8.expect(all(np.isfinite(v).all() for v in embeddings.values()), "Every embedding contains finite numbers.")
    print(f"Each embedding has {lengths.pop()} numbers.")
else:
    print("Skipped: no embeddings to check.")

# COMMAND ----------
# MAGIC %md
# MAGIC ### Python route: the same call through the Databricks SDK
# MAGIC `ai_query` is SQL. From Python you call the same serving endpoint with the Databricks SDK, which is how you
# MAGIC would embed text inside a pandas or scikit-learn workflow. It sends the same 30 texts again behind its own
# MAGIC default-no switch, so it doubles the quota used: skip it if you only need one route. If you did run the SQL step
# MAGIC above, the cell also checks that both routes return (almost) the same vectors.

# COMMAND ----------
# PYTHON ROUTE
# WHAT: asks for your approval before the second set of embedding requests.
# LOOK FOR: an embed_python widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
embed_python_approved = A8.gate("embed_python", "Embed the same 30 texts through the Python SDK (cost/quota)?")
print("Approved." if embed_python_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------
# PYTHON ROUTE
# WHAT: embeds the same texts with the Databricks SDK and keeps the vectors in memory.
# LOOK FOR: no output if approved; otherwise a note that the step was skipped. Do not retry errors in a loop.
python_vectors = None
if embed_python_approved:
    response = WorkspaceClient().serving_endpoints.query(name=EMBEDDING_ENDPOINT, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    python_vectors = {text: np.array(item.embedding, dtype=float) for text, item in zip(texts, ordered, strict=True)}
else:
    print("Python route skipped. The SQL route above gives the same result.")

# COMMAND ----------
# PYTHON ROUTE
# WHAT: Check: the SDK vectors have the right shape and, if you ran both routes, match the SQL vectors.
# LOOK FOR: pass messages; each text should have cosine similarity close to 1 between the two routes.
if python_vectors is not None:
    A8.expect(len(python_vectors) == len(texts), "Every text received an embedding through the SDK.")
    if embeddings is not None:
        closest = min(cosine(python_vectors[t], embeddings[t]) for t in texts)
        A8.expect(closest > 0.999, "The SQL and SDK routes return the same vectors.")
        print(f"Lowest similarity between the two routes: {closest:.5f}")
else:
    print("Skipped: no SDK vectors to check.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Search by meaning
# MAGIC The search is the same as before: compute the cosine similarity between the query vector and every comment
# MAGIC vector and keep the best. Only the vectors changed. In RAG the query is a question and the items are passages.
# MAGIC
# MAGIC **Predict:** for "food and drink", the keyword search found nothing. Which comments will the embedding rank
# MAGIC first?

# COMMAND ----------

# WHAT: ranks the distinct comments for each of the three search phrases using real embeddings.
# LOOK FOR: lunch, coffee and catering comments for food; stream and audio comments for the online problems.
if embeddings is not None:
    real_vectors = [embeddings[c] for c in comments]
    for phrase in probes:
        print(phrase)
        for score, comment in most_similar(embeddings[phrase], real_vectors, k=3):
            print(f"  {score:.2f}  {comment}")
else:
    print("Skipped: approve the embedding step above to see semantic search.")

# COMMAND ----------
# MAGIC %md
# MAGIC **Compare with the bag of words.** Look at the same stream complaint again, this time with real embeddings.
# MAGIC Is the audio complaint now close? Is the praise for the stream still ranked highly? Embeddings mostly capture
# MAGIC **topic**, so opposite opinions about the same topic can still sit close together. Similarity is not agreement.

# COMMAND ----------

# WHAT: lists the closest comments to the stream complaint with real embeddings beside the bag-of-words result.
# LOOK FOR: real embeddings should rank other stream or audio comments above unrelated ones, including audio.
if embeddings is not None:
    print("Real embeddings:")
    for score, comment in most_similar(embeddings[query], real_vectors, k=4, skip=query):
        print(f"  {score:.2f}  {comment}")
else:
    print("Skipped: approve the embedding step above to compare.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. From similarity to a business answer
# MAGIC A search is only useful if it answers a question. For each search phrase we take the three closest comments,
# MAGIC count how many of the 395 feedback rows they cover and compute their average rating, weighting by how often each
# MAGIC sentence appears. Choosing three is a judgement: a larger number or a minimum similarity would change the
# MAGIC answer.

# COMMAND ----------

# WHAT: summarises the matched comments for each search phrase: feedback rows covered and average rating.
# LOOK FOR: a row count and a rating per phrase; online problems should rate lower than food comments.
if embeddings is not None:
    for phrase in probes:
        matched = [comments.index(c) for _, c in most_similar(embeddings[phrase], real_vectors, k=3)]
        rows_covered = sum(counts[i] for i in matched)
        weighted = sum(counts[i] * ratings[i] for i in matched) / rows_covered
        print(f"{phrase}: {rows_covered} feedback rows, average rating {weighted:.2f}")
else:
    print("Skipped: approve the embedding step above to summarise matches.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Your turn
# MAGIC These two exercises use SQL and need **no model**. They show what the keyword approach can and cannot do.
# MAGIC 1. Exercise 8a.1: count the feedback rows for each comment that mentions `stream` or `audio`.
# MAGIC 2. Exercise 8a.2: for online events, count the comments that mention `stream` or `audio`, per event.
# MAGIC
# MAGIC Use `IDENTIFIER(a8_feedback)` and `IDENTIFIER(a8_events)` for table names. A blank answer shows the task and a
# MAGIC hint. `A8.solution("8a.1")` shows a worked answer. After 8a.1, look at which comments came back: does the
# MAGIC keyword search separate complaints from praise?

# COMMAND ----------

# WHAT: Check: compares your exercise 8a.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_8a_1 = """"""
A8.check("8a.1", answer_8a_1)

# COMMAND ----------

# WHAT: Check: compares your exercise 8a.2 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_8a_2 = """"""
A8.check("8a.2", answer_8a_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: why did we embed 27 comments instead of 395, and
# MAGIC what would change if the corpus were 100,000 comments? (You would store the vectors in an index so a search does
# MAGIC not compare against every vector. That is **Vector Search**, taught in `08c_vector_search`.)
# MAGIC
# MAGIC **Completion requires:** both exercises, the checks above, your explanations and, if you approved it, the real
# MAGIC embedding step. Skipping or being blocked on that step is fine: record it, and do not count the real-embedding
# MAGIC outcome as complete.
# MAGIC
# MAGIC **Pause:** nothing was written, so there is nothing to clean up. `99_pause_and_cleanup` is unchanged.
# MAGIC **Next:** `08b_rag` builds retrieval-augmented generation over a document set, using this search.

# COMMAND ----------
# WHAT: asks why word counting misses comments that mean the same thing.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_8a_a = """"""
A8.reflect("8a.a", my_answer_8a_a)

# COMMAND ----------
# WHAT: asks why similar vectors do not mean the same opinion.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_8a_b = """"""
A8.reflect("8a.b", my_answer_8a_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["Distinct feedback comments", "Bag-of-words vectors and cosine similarity",
              "Keyword search versus similarity search", "Optional real embeddings from a Foundation Model endpoint"],
             "99_pause_and_cleanup", "Pause safely or remove only your course work")
