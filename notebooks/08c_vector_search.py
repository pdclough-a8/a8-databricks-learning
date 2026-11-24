# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 8c. Vector Search: a managed index for the knowledge base
# MAGIC **Where this sits:** generative AI supporting descriptive questions about the business. It continues Module 8b:
# MAGIC the same documents and questions, with a managed index in place of the hand-built search.
# MAGIC
# MAGIC **Outcome:** create a Databricks **Vector Search** endpoint and a **Delta Sync index** over your chunk table,
# MAGIC query it with plain text, compare its retrieval with the word-overlap baseline on the same eight questions,
# MAGIC use it
# MAGIC to build a grounded answer, and then **delete the endpoint and index** so nothing keeps billing.
# MAGIC
# MAGIC **About 60 minutes of your time, plus waiting, an estimate:** orient 10 · endpoint 5 + wait · index 5 + wait ·
# MAGIC query and evaluate 15 · grounded answer 10 · cleanup 5 · recap 5. In our Free Edition test the endpoint was
# MAGIC online
# MAGIC at once and the index took about **15 to 20 minutes** to become usable, with no error shown while waiting.
# MAGIC **Before you start:** finish `00_setup`, `01_lakehouse_data` and `08b_rag` (it creates the chunk table).
# MAGIC All data and documents are synthetic.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. If creating an endpoint or index is blocked by a quota
# MAGIC or a missing feature, stop that branch and repeat the lesson in your paid workspace after running `00_setup`,
# MAGIC `01_lakehouse_data` and `08b_rag` there. The query and cleanup cells skip safely when nothing exists.
# MAGIC
# MAGIC **Cost boundary:** a Vector Search **endpoint bills for as long as it exists**, even when nobody queries it, and
# MAGIC uses quota on Free. This lesson creates one endpoint and one index, each behind a default-no switch, and ends
# MAGIC with a switch that deletes both. Embedding the chunks and the questions are model requests made by Databricks
# MAGIC for you. Ask before creating anything on a paid workspace. **Do the cleanup section before you leave.**
# MAGIC This lesson was validated live on Free Edition on 24 November 2026.
# MAGIC
# MAGIC ## Vector Search in plain English
# MAGIC In 8b we compared a question with all 32 chunk vectors one by one. That is fine for 32 chunks and hopeless for
# MAGIC 100,000. **Vector Search** is a managed service that stores the vectors in an **index** built for fast
# MAGIC nearest-neighbour search. With a **Delta Sync index and managed embeddings**, you point it at a Delta table and
# MAGIC name the text column. Databricks calls the embedding endpoint for every row, stores the vectors, and can keep
# MAGIC the
# MAGIC index in step with the table when it changes. You then query with plain text and get the closest rows back.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **Vector Search endpoint** | the compute that hosts indexes; it bills while it exists |
# MAGIC | **Index** | the stored vectors, organised for fast similarity search |
# MAGIC | **Delta Sync index** | an index that is built from, and can follow, a Delta table |
# MAGIC | **Managed embeddings** | Databricks embeds the text column for you using an embedding endpoint |
# MAGIC | **Change data feed** | a Delta table feature that records row changes, which lets an index sync from them |
# MAGIC | **Triggered sync** | the index updates when you ask, not continuously, which costs less |
# MAGIC | **Primary key** | the column that identifies each row; here `chunk_id` |
# MAGIC | **Similarity score** | how close a result is to the query; higher is closer |
# MAGIC
# MAGIC **Business question for this lesson:** *what changes when the knowledge base is too big to search by hand, and
# MAGIC what does it cost to run?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Vector Search](https://docs.databricks.com/aws/en/generative-ai/vector-search)
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; the Vector Search classes describe the index, and Counter and math handle the baseline.
import math
import re
import time
from collections import Counter

from a8learn import sql_string
from a8learn.lifecycle import delete_vector_search, vector_search_for_cleanup
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    EndpointStatusState,
    EndpointType,
    PipelineType,
    VectorIndexType,
)

# COMMAND ----------

# WHAT: checks the 8b prerequisite and resolves the names this lesson uses, with one wait setting.
# LOOK FOR: one Ready line with your chunk table, endpoint and index names. These names are yours alone.
A8.require("doc_chunks")
chunks_table = A8.t("doc_chunks")
source_table = f"{A8.cfg.catalog}.{A8.cfg.schema}.{A8.name('doc_chunks')}"
endpoint_name, index_name = A8.vector_endpoint_name, A8.vector_index_name
# The defaults are the endpoints saved by 00_setup. Change them only to endpoints listed in your Serving page.
EMBEDDING_ENDPOINT = A8.cfg.embedding_model or "databricks-gte-large-en"
CHAT_ENDPOINT = A8.cfg.chat_model or "databricks-meta-llama-3-3-70b-instruct"
dbutils.widgets.text("wait_minutes", "10", "Minutes each status check waits")
WAIT_MINUTES = int(dbutils.widgets.get("wait_minutes"))
w = WorkspaceClient()
print(f"Ready | {chunks_table} | endpoint: {endpoint_name} | index: {index_name}")

# COMMAND ----------

# WHAT: reads the chunks from your table so this lesson can compare retrieval and build prompts.
# LOOK FOR: no output; one dictionary per chunk, the same fields the index will return.
COLUMNS = ["chunk_id", "doc_name", "doc_title", "section", "content"]
chunks = [{c: row[c] for c in COLUMNS} for row in
          spark.sql(f"SELECT {', '.join(COLUMNS)} FROM {chunks_table} ORDER BY chunk_id").collect()]

# COMMAND ----------

# WHAT: Check: the chunk table has rows to index.
# LOOK FOR: a pass message with the number of chunks; zero means rerun the table cells in 08b_rag.
A8.expect(len(chunks) > 0, "The chunk table has rows. If not, run the table cells in 08b_rag first.")
print(len(chunks), "chunks to index.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Create the endpoint (billable while it exists)
# MAGIC An endpoint is created asynchronously: the call returns at once and the endpoint moves from `PROVISIONING` to
# MAGIC `ONLINE`. In our test it was online at once, with the serving compute provisioned when the index is created.
# MAGIC We use a **Standard** endpoint. The name `a8-<your tag>-vs` is yours; the cell refuses to touch an
# MAGIC endpoint of that name that you did not create.
# MAGIC
# MAGIC **I expect:** one endpoint that reaches `ONLINE` after some minutes. **If it differs:** a quota or capability
# MAGIC error means this workspace cannot create the endpoint; stop and repeat the lesson in your paid workspace. Do not
# MAGIC retry quota errors in a loop. **Undo:** the cleanup section, or `99_pause_and_cleanup`, deletes it.

# COMMAND ----------

# WHAT: asks for your approval before creating a billable endpoint.
# LOOK FOR: a create_vs_endpoint widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
create_endpoint_approved = A8.gate("create_vs_endpoint", "Create your Vector Search endpoint (billable)?")
print("Approved." if create_endpoint_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: requests your endpoint if you approved and it does not already exist.
# LOOK FOR: "requested" for a new endpoint, "already exists" on a rerun, or a note that nothing was approved.
if create_endpoint_approved:
    try:
        existing = w.vector_search_endpoints.get_endpoint(endpoint_name)
        A8.expect(existing.creator == A8.cfg.user, "The existing endpoint with this name was created by you.")
        print("Endpoint already exists.")
    except NotFound:
        w.vector_search_endpoints.create_endpoint(endpoint_name, EndpointType.STANDARD)
        print("Endpoint requested.")
else:
    print("Endpoint not created. The steps below skip safely.")

# COMMAND ----------

# WHAT: defines a status check that waits up to your wait_minutes, so a rerun can carry on from where it stopped.
# LOOK FOR: no output; wait_until prints the status every 30 seconds and returns True once the check passes.
def wait_until(check, minutes=WAIT_MINUTES, every=30):
    deadline = time.time() + minutes * 60
    while True:
        done, message = check()
        print(message)
        if done or time.time() >= deadline:
            return done
        time.sleep(every)

# COMMAND ----------

# WHAT: waits for your endpoint to be online, or reports that none exists.
# LOOK FOR: ONLINE, usually straight away; the index is the slow part. Rerun this cell if it is still PROVISIONING.
def endpoint_status():
    try:
        status = w.vector_search_endpoints.get_endpoint(endpoint_name).endpoint_status
    except NotFound:
        return True, "No endpoint exists, so there is nothing to wait for."
    return status.state == EndpointStatusState.ONLINE, f"Endpoint state: {status.state.value} {status.message or ''}"


endpoint_online = wait_until(endpoint_status)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Create the index from your chunk table
# MAGIC The index definition says four things: the **source table** (with change data feed on, which 8b set), the
# MAGIC **primary key**, the **text column to embed** with the embedding endpoint that does it, and a **triggered**
# MAGIC sync. We also list the columns to sync, because only synced columns can be returned by a query. Building the
# MAGIC index embeds every chunk, which uses the embedding endpoint's quota.
# MAGIC
# MAGIC **I expect:** an index that is not ready for several minutes, then ready with one indexed row per chunk.
# MAGIC **If it differs:** an error about change data feed means the chunk table was recreated without it; rerun the
# MAGIC table cells in `08b_rag`. An embedding-endpoint error means choose another endpoint from your Serving page.
# MAGIC **Undo:** the cleanup section, or `99_pause_and_cleanup`, deletes the index. The chunk table stays.

# COMMAND ----------

# WHAT: asks for your approval before creating the index.
# LOOK FOR: a create_vs_index widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
create_index_approved = A8.gate("create_vs_index", "Create your Vector Search index (embeds every chunk)?")
print("Approved." if create_index_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: creates your Delta Sync index over the chunk table if you approved and it does not already exist.
# LOOK FOR: "requested" for a new index, "already exists" on a rerun, or a note that nothing was approved.
if create_index_approved:
    try:
        existing_index = w.vector_search_indexes.get_index(index_name)
        A8.expect(existing_index.creator == A8.cfg.user, "The existing index with this name was created by you.")
        print("Index already exists.")
    except NotFound:
        w.vector_search_indexes.create_index(
            name=index_name, endpoint_name=endpoint_name, primary_key="chunk_id", index_type=VectorIndexType.DELTA_SYNC,
            delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                source_table=source_table, pipeline_type=PipelineType.TRIGGERED, columns_to_sync=COLUMNS,
                embedding_source_columns=[EmbeddingSourceColumn(
                    name="content", embedding_model_endpoint_name=EMBEDDING_ENDPOINT)]))
        print("Index requested.")
else:
    print("Index not created. The steps below skip safely.")

# COMMAND ----------

# WHAT: waits for your index to be ready, or reports that none exists.
# LOOK FOR: not ready for several minutes, then ready with the number of rows indexed. Rerun to keep waiting.
def index_status():
    try:
        status = w.vector_search_indexes.get_index(index_name).status
    except NotFound:
        return True, "No index exists, so there is nothing to wait for."
    detail = f"Index ready: {status.ready}, rows indexed: {status.indexed_row_count}"
    return bool(status.ready), f"{detail} {status.message or ''}"


index_ready = wait_until(index_status)

# COMMAND ----------

# WHAT: Check: if an index exists it is ready and has indexed every chunk.
# LOOK FOR: two pass messages, or a note that no index exists yet. If not ready, rerun the waiting cell above.
try:
    index_info = w.vector_search_indexes.get_index(index_name)
except NotFound:
    index_info = None
if index_info is not None:
    A8.expect(bool(index_info.status.ready), "The index is ready. If not, rerun the waiting cell above.")
    A8.expect(index_info.status.indexed_row_count == len(chunks), "The index holds one row per chunk.")
else:
    print("No index to check.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Query the index with text
# MAGIC The query is plain text. Databricks embeds it with the same endpoint, finds the nearest chunks and returns the
# MAGIC columns you ask for, with the similarity score as the last value of each row.
# MAGIC
# MAGIC **Predict:** for "A colleague wants to take over my seat." the word-overlap search in 8b ranked the
# MAGIC cancellations section first. Which section will the index rank first?

# COMMAND ----------

# WHAT: defines a search function that queries the index and returns (score, chunk) pairs like the 8b retrievers.
# LOOK FOR: no output; with no index it returns an empty list rather than failing.
def index_search(question, k=3):
    try:
        response = w.vector_search_indexes.query_index(
            index_name=index_name, columns=COLUMNS, query_text=question, num_results=k)
    except NotFound:
        return []
    return [(row[-1], dict(zip(COLUMNS, row[:-1], strict=True))) for row in response.result.data_array or []]

# COMMAND ----------

# WHAT: asks the index the question and shows the closest chunks with their similarity scores.
# LOOK FOR: the transfer section of booking-and-transfers.md near the top, or a note that no index exists.
question = "A colleague wants to take over my seat."
index_usable = index_info is not None and bool(index_info.status.ready)
found = index_search(question) if index_usable else []
for score, chunk in found:
    print(f"{score:.3f}  {chunk['doc_title']} / {chunk['section']}")
if not found:
    print("No results: create the endpoint and index above first.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Does it retrieve better than word overlap?
# MAGIC Same eight questions and same hit-at-k score as 8b. The index is a managed search, not a guarantee: it uses
# MAGIC the same kind of embeddings, so it should behave like the hand-built embedding search, only at any scale.
# MAGIC The word-overlap baseline is rebuilt here so this lesson stands alone.

# COMMAND ----------

# WHAT: defines the evaluation questions with the document that should answer each, and the word-overlap baseline.
# LOOK FOR: no output; these are the same eight questions and the same baseline as in 08b_rag.
EVAL = [
    ("Can I give my ticket to a colleague?", "booking-and-transfers.md"),
    ("A colleague wants to take over my seat.", "booking-and-transfers.md"),
    ("Do I get my money back if I pull out ten days before?", "cancellations-and-refunds.md"),
    ("I can't eat wheat. What will I be able to eat?", "catering-and-dietary.md"),
    ("Is there a place to rest if I feel overwhelmed?", "accessibility.md"),
    ("The picture keeps stuttering on the live stream. What should I do?", "online-events.md"),
    ("Nothing arrived in my inbox after I paid.", "booking-and-transfers.md"),
    ("How many people fit in the Bristol room?", "venue-bristol.md"),
]
OUT_OF_SCOPE = "What is the weather forecast for the London event?"
STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "and", "to", "of", "i", "my", "me", "do", "does", "can",
              "how", "what", "when", "where", "if", "it", "in", "on", "at", "for", "or", "you", "we", "our", "this",
              "that", "with", "there", "be", "will", "should", "get", "have", "has", "from", "by", "as"}


def words(text):
    return Counter(word for word in re.findall(r"[a-z']+", text.lower()) if word not in STOP_WORDS)


def word_cosine(a, b):
    length = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return 0.0 if length == 0 else sum(a[x] * b[x] for x in a) / length


def word_search(question, k=3):
    scored = [(word_cosine(words(question), words(c["content"])), c) for c in chunks]
    return sorted(scored, key=lambda s: s[0], reverse=True)[:k]


def hit_rate(search_function, k):
    hits = [any(chunk["doc_name"] == doc for _, chunk in search_function(q, k)) for q, doc in EVAL]
    return sum(hits) / len(EVAL)

# COMMAND ----------

# WHAT: scores the word-overlap baseline and, if your index is ready, the index, on the same questions.
# LOOK FOR: hit at 1 and hit at 3 for each; the index sends eight query requests and should not trail the baseline.
print(f"Word overlap: hit@1 {hit_rate(word_search, 1):.2f}, hit@3 {hit_rate(word_search, 3):.2f}")
if index_usable:
    print(f"Index:        hit@1 {hit_rate(index_search, 1):.2f}, hit@3 {hit_rate(index_search, 3):.2f}")
else:
    print("Index:        skipped (no ready index)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. A grounded answer from the managed index
# MAGIC The prompt is the same as in 8b: an instruction to answer only from numbered sources and to refuse otherwise,
# MAGIC the sources, and the question. Only the retriever changed. This sends **two** chat prompts behind a switch.
# MAGIC
# MAGIC **If it differs:** a message that a `databricks-` endpoint is no longer available means your workspace names
# MAGIC built-in models `system.ai.<model>`; put that name in `CHAT_ENDPOINT`. **Undo:** nothing is created.

# COMMAND ----------

# WHAT: defines the grounded prompt builder from 8b.
# LOOK FOR: no output; sources are numbered so the answer can cite them as [1], [2], [3].
REFUSAL = "I can't find that in the A8 Events documents."


def build_prompt(question, passages):
    sources = "\n\n".join(f"[{i}] ({chunk['doc_title']} / {chunk['section']})\n{chunk['content']}"
                          for i, (_, chunk) in enumerate(passages, start=1))
    return ("You answer questions from A8 Events customers using ONLY the sources below. "
            f"If the sources do not contain the answer, reply exactly: {REFUSAL} "
            "Otherwise answer briefly and cite the source numbers in square brackets, for example [1].\n\n"
            f"Sources:\n{sources}\n\nQuestion: {question}\nAnswer:")

# COMMAND ----------

# WHAT: asks for your approval before any chat request.
# LOOK FOR: an ask_model_vs widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
ask_approved = A8.gate("ask_model_vs", "Send two chat prompts using the index (cost/quota)?")
print("Approved." if ask_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: retrieves from the index, builds two prompts and sends them once if you approved and the index is ready.
# LOOK FOR: each answer with the documents it cited, and whether the weather question was refused.
if ask_approved and found:
    ask = [(q, index_search(q)) for q in (question, OUT_OF_SCOPE)]
    prompts = [build_prompt(q, passages) for q, passages in ask]
    values = ", ".join(f"(:q{i}, :p{i})" for i in range(len(prompts)))
    args = {**{f"q{i}": q for i, (q, _) in enumerate(ask)}, **{f"p{i}": p for i, p in enumerate(prompts)}}
    answers = spark.sql(f"""SELECT question, ai_query({sql_string(CHAT_ENDPOINT)}, prompt, failOnError => false,
modelParameters => named_struct('max_tokens', 300, 'temperature', CAST(0.0 AS DOUBLE))) AS reply
FROM VALUES {values} AS input(question, prompt)""", args=args).collect()
    for row, (_, passages) in zip(answers, ask, strict=True):
        reply = row["reply"]  # a struct with the fields result and errorMessage
        if reply["errorMessage"]:
            print(row["question"], "->", "ERROR:", reply["errorMessage"])
            continue
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", reply["result"])})
        cited_docs = [passages[n - 1][1]["doc_name"] for n in cited if 1 <= n <= len(passages)]
        print(f"Q: {row['question']}\nA: {reply['result'].strip()}\nCited: {cited_docs}\n"
              f"Refused: {REFUSAL.lower() in reply['result'].lower()}\n")
else:
    print("Skipped: approve the chat step and create a ready index first.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Your turn
# MAGIC Exercise 8c.1 uses **PySpark**, not SQL, on your chunk table: return `doc_name` and `chunks` (the number of
# MAGIC chunks) for the **venue** documents only (names starting `venue-`), ordered by `doc_name`. Replace `None` with a
# MAGIC DataFrame. Hint: `from pyspark.sql import functions as F`, then `where`, `groupBy`, `agg` and `orderBy`.
# MAGIC `A8.solution("8c.1")` shows a worked SQL answer.
# MAGIC
# MAGIC **Transfer:** change `question` above to one a customer might ask about parking or recordings, run the query
# MAGIC cell and look at what comes back. Then ask something the documents cannot answer. What score does the best
# MAGIC irrelevant chunk get? A score alone does not tell you the answer is missing, which is why the prompt asks the
# MAGIC model to refuse.

# COMMAND ----------

# WHAT: Check: compares your PySpark exercise 8c.1 result with the course solution.
# LOOK FOR: a hint while the answer is None, otherwise feedback on your result.
answer_8c_1 = None
A8.check("8c.1", answer_8c_1)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Clean up: delete the index and the endpoint
# MAGIC The endpoint bills while it exists, so delete it when you finish. This removes the **index first** (an endpoint
# MAGIC cannot be deleted while it hosts one) and then the endpoint, after checking that you created both and that the
# MAGIC endpoint hosts nothing else. Your chunk table stays, so you can create the index again later.
# MAGIC
# MAGIC **I expect:** both gone within a few minutes. **If it differs:** a "not yours" refusal means you did not create
# MAGIC that resource; leave it alone. **Undo:** none; recreate them from sections 1 and 2.

# COMMAND ----------

# WHAT: asks for your approval before deleting your index and endpoint.
# LOOK FOR: a delete_vector_search widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
delete_approved = A8.gate("delete_vector_search", "Delete your Vector Search index and endpoint?")
print("Approved." if delete_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: deletes your index and then your endpoint, only if you approved and both are yours.
# LOOK FOR: "Deleted" or "Nothing to delete"; an ownership problem stops with an error and deletes nothing.
if delete_approved:
    owned_index, owned_endpoint = vector_search_for_cleanup(A8, w)
    delete_vector_search(A8, w, owned_index, owned_endpoint)
    print("Deleted." if owned_index or owned_endpoint else "Nothing to delete.")
else:
    print("Not deleted. Remember: your endpoint bills while it exists.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: what would you change to keep the index up to date
# MAGIC when a policy document changes? (Update the chunk table, then run a sync on the index. A triggered index does
# MAGIC not
# MAGIC refresh by itself, which keeps cost down.)
# MAGIC
# MAGIC **Completion requires:** the exercise, the checks above, your explanations and a deleted endpoint. If you could
# MAGIC not create an endpoint or index, record that and do not count the managed-retrieval outcome as complete.
# MAGIC
# MAGIC **Pause:** run the cleanup section, or `99_pause_and_cleanup`, before leaving. Both remove the index and
# MAGIC endpoint.
# MAGIC **Next:** Module 9 (an agent that uses this retrieval as one of its tools) is planned.

# COMMAND ----------
# WHAT: asks when a managed index becomes worthwhile compared with the hand-built search.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_8c_a = """"""
A8.reflect("8c.a", my_answer_8c_a)

# COMMAND ----------
# WHAT: asks why the endpoint must be deleted even though the table and documents are kept.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_8c_b = """"""
A8.reflect("8c.b", my_answer_8c_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["A Vector Search endpoint and Delta Sync index over your chunk table",
              "Text queries, scored with hit at k against word overlap",
              "A grounded answer using the managed retriever", "A cleanup that removes the billable endpoint"],
             "09_agents", "Build an agent that chooses its own tools")
