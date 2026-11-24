# Databricks notebook source
# MAGIC %md
# MAGIC # A8 | 8b. RAG: answer customer questions from our own documents
# MAGIC **Where this sits:** generative AI supporting descriptive questions about the business ("what is our policy?").
# MAGIC It builds on the embeddings in Module 8a. RAG adds a language model; it does not predict or explain data.
# MAGIC
# MAGIC **Outcome:** build a small **retrieval-augmented generation (RAG)** pipeline over a fictional A8 Events
# MAGIC knowledge base: split documents into chunks, find the chunks closest to a question, ask a model to answer
# MAGIC **only** from them with citations, refuse when the documents do not say, and measure how well retrieval works.
# MAGIC Everything is built by hand so you can see each part. `08c_vector_search` then swaps the hand-built search
# MAGIC for Databricks
# MAGIC **Vector Search**.
# MAGIC
# MAGIC **About 75 minutes, an estimate:** orient 10 · documents and chunks 20 · retrieval 15 · grounded answer 15 ·
# MAGIC evaluation 10 · exercises and recap 5.
# MAGIC **Before you start:** finish `00_setup` and `01_lakehouse_data` (the course volume is needed).
# MAGIC `08a_embeddings` is
# MAGIC recommended. All data and documents are synthetic. Never substitute real customer documents.
# MAGIC
# MAGIC **Free first:** run this in your Free Edition workspace. The chunking, the word-overlap search, the prompt
# MAGIC and the
# MAGIC exercises need no model. If an embedding or chat request is blocked by a quota or a missing endpoint, finish the
# MAGIC rest, then repeat that step in your paid workspace after running `00_setup` and `01_lakehouse_data` there.
# MAGIC
# MAGIC **Cost boundary:** this lesson writes **nine small files** to your volume and **one small table**. No
# MAGIC endpoint or
# MAGIC index is created. Two model steps sit behind default-no switches: embedding about 40 short texts, then **two**
# MAGIC chat prompts. Inference uses quota on Free and can cost money on a paid workspace, so ask before you approve
# MAGIC it there. This lesson was
# MAGIC validated live on Free Edition on 24 November 2026 (embeddings, one cited answer, one refusal).
# MAGIC
# MAGIC ## RAG in plain English
# MAGIC A customer asks: *can I give my ticket to a colleague?* A language model has never seen A8's policies. Asked
# MAGIC directly, it may guess, and a confident wrong guess about refunds is worse than no answer.
# MAGIC
# MAGIC **RAG** fixes this in three steps. **Retrieve:** find the few passages in our documents closest in meaning to
# MAGIC the question (the embedding search from 8a). **Augment:** put those passages into the prompt, with an
# MAGIC instruction to use only them. **Generate:** the model writes a short answer and cites the passages it used. If
# MAGIC no passage answers the question, it should say so. The documents stay the source of truth, and you can update
# MAGIC them without retraining anything.
# MAGIC
# MAGIC ## Terms in this lesson
# MAGIC | Term | Meaning |
# MAGIC |---|---|
# MAGIC | **RAG** | retrieval-augmented generation: look up passages, then answer from them |
# MAGIC | **Chunk** | a passage of a document small enough to embed and retrieve; here, one section |
# MAGIC | **Retrieval** | finding the chunks most similar to a question |
# MAGIC | **Prompt** | the instructions, sources and question sent to the model |
# MAGIC | **Grounded answer** | an answer supported by the retrieved passages, with citations |
# MAGIC | **Refusal** | saying "I can't find that" when the documents do not answer the question |
# MAGIC | **Hit at k** | the share of test questions whose correct document is among the top k chunks |
# MAGIC | **Context vs RAG** | pasting text into a prompt by hand, versus finding it automatically |
# MAGIC
# MAGIC **Business question for this lesson:** *can a customer-facing assistant answer policy and venue questions
# MAGIC correctly from our own documents, and how would we know?*
# MAGIC
# MAGIC Read more:
# MAGIC - [Retrieval-augmented generation on
# MAGIC Databricks](https://docs.databricks.com/aws/en/generative-ai/retrieval-augmented-generation)
# MAGIC - [ai_query](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_query)
# MAGIC - [Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# WHAT: imports the libraries used in this lesson.
# LOOK FOR: no output; numpy does vector arithmetic, Counter counts words and sql_string quotes text for SQL.
import re
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
from a8learn import COURSE_ID, sql_string

# COMMAND ----------

# WHAT: checks the Module 1 prerequisite and resolves the names this lesson uses.
# LOOK FOR: one Ready line naming your volume folder, chunk table and the two model endpoints.
A8.require("raw")
chunks_table = A8.t("doc_chunks")
docs_path = Path(A8.volume_path) / "docs"
# The defaults are the endpoints saved by 00_setup. Change them only to endpoints listed in your Serving page.
EMBEDDING_ENDPOINT = A8.cfg.embedding_model or "databricks-gte-large-en"
CHAT_ENDPOINT = A8.cfg.chat_model or "databricks-meta-llama-3-3-70b-instruct"
print(f"Ready | {docs_path} | {chunks_table} | embeddings: {EMBEDDING_ENDPOINT} | chat: {CHAT_ENDPOINT}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. The knowledge base
# MAGIC A8 Events publishes nine short documents: how to book and transfer tickets, cancellations and refunds, catering,
# MAGIC accessibility, one page for each of the four venues and one for online events. They are written for this course
# MAGIC and some of them answer complaints you saw in the feedback comments (late confirmation emails, changing a
# MAGIC booking
# MAGIC to a colleague, finding the entrance, dietary needs, stream problems).
# MAGIC
# MAGIC The files are in your Git folder under `data/docs`. Real documents would arrive in a **volume**, the governed
# MAGIC file folder from Module 1, so we copy them into a `docs` folder in your course volume first.
# MAGIC
# MAGIC **I expect:** nine Markdown files in your volume. **If it differs:** a permission error means you cannot
# MAGIC write to
# MAGIC the volume; check `01_lakehouse_data` ran in this workspace. **Undo:** `99_pause_and_cleanup` drops the volume.

# COMMAND ----------

# WHAT: copies the nine knowledge-base documents into a docs folder in your course volume.
# LOOK FOR: no output; a rerun overwrites the same nine files.
A8.guard("raw")
docs_path.mkdir(exist_ok=True)
for source in sorted((ROOT / "data" / "docs").glob("*.md")):
    shutil.copyfile(source, docs_path / source.name)

# COMMAND ----------

# WHAT: lists the documents now in your volume.
# LOOK FOR: nine .md files, one per document.
doc_files = sorted(docs_path.glob("*.md"))
print(len(doc_files), "documents:", [p.name for p in doc_files])

# COMMAND ----------

# WHAT: Check: confirms all nine documents are present.
# LOOK FOR: a pass message; a failure means the copy did not complete.
A8.expect(len(doc_files) == 9, "The volume holds nine knowledge-base documents.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Split documents into chunks
# MAGIC A document is too long to embed as one vector: one vector cannot represent a whole page of different topics, and
# MAGIC a prompt has limited room. So we split each document into **chunks**. Chunk size is a trade-off:
# MAGIC - **Too big:** several topics blur into one vector, and the prompt fills with irrelevant text.
# MAGIC - **Too small:** a sentence loses the context that gives it meaning, such as which venue it describes.
# MAGIC
# MAGIC These documents already have `##` headings, so each **section** is one chunk. We put the document title and
# MAGIC section heading at the start of each chunk, so the text says what it is about and which venue it describes.
# MAGIC We also keep the document name and section as separate fields, so an answer can **cite** its source.
# MAGIC
# MAGIC **Predict:** how many chunks will nine documents produce? Run the next cells to find out.

# COMMAND ----------

# WHAT: defines how one document is split into section chunks with their source fields.
# LOOK FOR: no output; each chunk is a dictionary with an id, source fields and the text to embed.
def read_chunks(path):
    text = path.read_text(encoding="utf-8")
    title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    parts = re.split(r"^## (.+)$", text, flags=re.M)  # [preamble, heading, body, heading, body, ...]
    return [{"chunk_id": f"{path.stem}-{n}", "doc_name": path.name, "doc_title": title, "section": heading.strip(),
             "content": f"{title} - {heading.strip()}: {' '.join(body.split())}"}
            for n, (heading, body) in enumerate(zip(parts[1::2], parts[2::2], strict=True), start=1)]

# COMMAND ----------

# WHAT: reads every document from the volume and splits it into chunks.
# LOOK FOR: the number of chunks and the number per document.
chunks = [chunk for path in doc_files for chunk in read_chunks(path)]
per_doc = Counter(chunk["doc_name"] for chunk in chunks)
print(len(chunks), "chunks;", dict(per_doc))

# COMMAND ----------

# WHAT: Check: every chunk has content, an unused id and a length that fits a prompt comfortably.
# LOOK FOR: three pass messages; the longest chunk is well under the 800-character limit set for this lesson.
MAX_CHARS = 800
A8.expect(all(c["content"].strip() for c in chunks), "No chunk is empty.")
A8.expect(len({c["chunk_id"] for c in chunks}) == len(chunks), "Every chunk id is unique.")
A8.expect(max(len(c["content"]) for c in chunks) <= MAX_CHARS, f"No chunk is longer than {MAX_CHARS} characters.")
print("Longest chunk:", max(len(c["content"]) for c in chunks), "characters")

# COMMAND ----------

# WHAT: shows one chunk so you can see exactly what will be embedded and cited.
# LOOK FOR: the title and section at the start of the content, and the source fields beside it.
print(chunks[1])

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Store the chunks in a Delta table
# MAGIC Keeping chunks in a table makes them governed and queryable, and `08c_vector_search` builds a Vector Search
# MAGIC index from
# MAGIC this
# MAGIC table. We turn on **change data feed** so an index can follow changes to the table. We build the table the same
# MAGIC way as in Module 1: a temporary view of the values first, then `CREATE OR REPLACE TABLE ... AS SELECT`.
# MAGIC
# MAGIC **I expect:** one table with one row per chunk. **If it differs:** a guard error means a table with this name
# MAGIC exists and is not yours; choose a different learner tag in `00_setup`. **Undo:** rerunning resets the table;
# MAGIC `99_pause_and_cleanup` drops it.

# COMMAND ----------

# WHAT: prepares the chunk rows as a session-only source view, with the text passed as parameters.
# LOOK FOR: no output; chunk text travels as parameters, never inside the SQL text.
columns = ["chunk_id", "doc_name", "doc_title", "section", "content"]
rows_sql = ", ".join("(" + ", ".join(f":{c}{i}" for c in columns) + ")" for i in range(len(chunks)))
row_args = {f"{c}{i}": chunk[c] for i, chunk in enumerate(chunks) for c in columns}
spark.sql(f"SELECT * FROM VALUES {rows_sql} AS v({', '.join(columns)})",
          args=row_args).createOrReplaceTempView("a8_source_doc_chunks")

# COMMAND ----------

# WHAT: creates your chunk table with change data feed on and your ownership labels.
# LOOK FOR: one CREATE OR REPLACE TABLE statement; a rerun resets the table to the same rows.
A8.guard("doc_chunks")
spark.sql(f"""CREATE OR REPLACE TABLE {chunks_table} USING DELTA
COMMENT 'a8-databricks-learning synthetic knowledge-base chunks'
TBLPROPERTIES ('a8learn.course' = '{COURSE_ID}', 'a8learn.tag' = '{A8.cfg.tag}',
'delta.enableChangeDataFeed' = 'true')
AS SELECT * FROM a8_source_doc_chunks""")

# COMMAND ----------

# WHAT: removes the session-only source view.
# LOOK FOR: no output; the persisted table is unaffected.
spark.catalog.dropTempView("a8_source_doc_chunks")

# COMMAND ----------

# WHAT: Check: the table has one row per chunk.
# LOOK FOR: a pass message with the row count.
A8.expect(spark.table(chunks_table).count() == len(chunks), "The chunk table has one row per chunk.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. A search with no model: word overlap
# MAGIC Retrieval needs a way to score how close a chunk is to a question. The simplest is **word overlap**, the bag of
# MAGIC words from 8a: count shared words and compare with cosine similarity. It needs no model, so it is our baseline.
# MAGIC Any better method has to beat it.

# COMMAND ----------

# WHAT: defines a word-overlap search over the chunks, with a small list of common words ignored.
# LOOK FOR: no output; word_search returns (score, chunk) pairs, best first.
STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "and", "to", "of", "i", "my", "me", "do", "does", "can",
              "how", "what", "when", "where", "if", "it", "in", "on", "at", "for", "or", "you", "we", "our", "this",
              "that", "with", "there", "be", "will", "should", "get", "have", "has", "from", "by", "as"}


def words(text):
    return Counter(w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP_WORDS)


def word_cosine(a, b):
    length = np.sqrt(sum(v * v for v in a.values())) * np.sqrt(sum(v * v for v in b.values()))
    return 0.0 if length == 0 else sum(a[w] * b[w] for w in a) / length


def word_search(question, k=3):
    scored = [(word_cosine(words(question), words(c["content"])), c) for c in chunks]
    return sorted(scored, key=lambda s: s[0], reverse=True)[:k]

# COMMAND ----------

# WHAT: asks the word-overlap search a question that uses different words from the document.
# LOOK FOR: the top chunk and its score; is the transfer section in booking-and-transfers.md ranked first?
question = "A colleague wants to take over my seat."
for score, chunk in word_search(question):
    print(f"{score:.2f}  {chunk['doc_title']} / {chunk['section']}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. A search with embeddings
# MAGIC Now the same search with the embeddings from 8a. We embed every chunk and every question we will ask, in one
# MAGIC query, and compare vectors with cosine similarity. That is about **40 short synthetic texts** sent to one
# MAGIC embedding endpoint, behind a default-no switch. Nothing is written.
# MAGIC
# MAGIC The questions come from an **evaluation set**: eight customer questions, each with the document that should
# MAGIC answer it, plus one question the documents cannot answer. We use the same set later to measure retrieval.
# MAGIC
# MAGIC **If the endpoint is not found:** open **Serving**, find an embeddings endpoint and put its exact name in
# MAGIC `EMBEDDING_ENDPOINT` above. Do not create an endpoint. **Undo:** nothing is created.

# COMMAND ----------

# WHAT: defines the evaluation questions with the document that should answer each, and one unanswerable question.
# LOOK FOR: no output; the expected document is only used to score retrieval, never sent to a model.
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
texts = [c["content"] for c in chunks] + [q for q, _ in EVAL] + [OUT_OF_SCOPE]
print(f"{len(texts)} texts to embed: {len(chunks)} chunks and {len(texts) - len(chunks)} questions.")

# COMMAND ----------

# WHAT: asks for your approval before any embedding request.
# LOOK FOR: an embed_chunks widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
embed_approved = A8.gate("embed_chunks", "Embed about 40 short synthetic texts (cost/quota)?")
print("Approved." if embed_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: sends the approved texts to the embedding endpoint once and keeps the vectors in memory.
# LOOK FOR: no output if approved; otherwise a note that the step was skipped. Do not retry errors in a loop.
embeddings = None
if embed_approved:
    values = ", ".join(f"(:t{i})" for i in range(len(texts)))
    embedded = spark.sql(f"""SELECT text, ai_query({sql_string(EMBEDDING_ENDPOINT)}, text) AS embedding
FROM VALUES {values} AS input(text)""", args={f"t{i}": t for i, t in enumerate(texts)}).collect()
    embeddings = {row["text"]: np.array(row["embedding"], dtype=float) for row in embedded}
else:
    print("Embedding skipped. Retrieval below falls back to word overlap; the exercises still work.")

# COMMAND ----------

# WHAT: Check: every text has a finite vector and all vectors have the same length.
# LOOK FOR: pass messages and the vector length, or a note that the step was skipped.
if embeddings is not None:
    lengths = {len(v) for v in embeddings.values()}
    A8.expect(len(embeddings) == len(set(texts)), "Every text received an embedding.")
    A8.expect(len(lengths) == 1 and lengths != {0}, "All embeddings have the same non-zero length.")
    A8.expect(all(np.isfinite(v).all() for v in embeddings.values()), "Every embedding contains finite numbers.")
    print(f"Each embedding has {lengths.pop()} numbers.")
else:
    print("Skipped: no embeddings to check.")

# COMMAND ----------

# WHAT: defines cosine similarity and the embedding search, falling back to word overlap without embeddings.
# LOOK FOR: no output; search() is the retriever used by the rest of the lesson.
def cosine(a, b):
    length = np.linalg.norm(a) * np.linalg.norm(b)
    return 0.0 if length == 0 else float(a @ b / length)


def embedding_search(question, k=3):
    scored = [(cosine(embeddings[question], embeddings[c["content"]]), c) for c in chunks]
    return sorted(scored, key=lambda s: s[0], reverse=True)[:k]


search = embedding_search if embeddings is not None else word_search
print("Retriever:", "embeddings" if embeddings is not None else "word overlap (no embeddings yet)")

# COMMAND ----------

# WHAT: asks the retriever the same transfer question and shows the closest chunks.
# LOOK FOR: whether the transfer section of booking-and-transfers.md now ranks first; compare with word overlap.
for score, chunk in search(question):
    print(f"{score:.2f}  {chunk['doc_title']} / {chunk['section']}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Ask the model, with the passages in the prompt
# MAGIC The prompt has three parts: an **instruction** (answer only from the sources, cite them, and refuse if the
# MAGIC sources do not say), the **sources** (the retrieved chunks, numbered) and the **question**. Building the prompt
# MAGIC costs nothing, so look at it before any model sees it.
# MAGIC
# MAGIC **Predict:** what should the model answer for "What is the weather forecast for the London event?"

# COMMAND ----------

# WHAT: defines the function that builds the grounded prompt from a question and its retrieved chunks.
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

# WHAT: builds and prints the prompt for the transfer question, without any model request.
# LOOK FOR: the instruction, three numbered sources and the question; check the transfer section is included.
ask = [(question, search(question)), (OUT_OF_SCOPE, search(OUT_OF_SCOPE))]
prompts = [build_prompt(q, passages) for q, passages in ask]
print(prompts[0])

# COMMAND ----------

# WHAT: Check: each prompt stays within a size that fits any chat model and carries three sources.
# LOOK FOR: two pass messages; a failure means chunks or the instruction grew too long.
A8.expect(all(len(p) <= 6000 for p in prompts), "Each prompt is within the bounded teaching size.")
A8.expect(all(p.count("\n[") == 3 for p in prompts), "Each prompt carries exactly three numbered sources.")

# COMMAND ----------
# MAGIC %md
# MAGIC Now two real model requests: the transfer question and the weather question. `failOnError => false` returns
# MAGIC the error text instead of stopping the notebook, and `temperature` 0 makes the answer as repeatable as the
# MAGIC model allows. Set the `ask_model` widget to **yes** only if you accept the quota or cost.
# MAGIC
# MAGIC **If it differs:** a message that a `databricks-` endpoint is no longer available means your workspace now names
# MAGIC built-in models as `system.ai.<model>` (drop `databricks-`); put that name in `CHAT_ENDPOINT`. An
# MAGIC endpoint-not-found
# MAGIC error means choose a chat endpoint from your Serving page. **Undo:** nothing is created.

# COMMAND ----------

# WHAT: asks for your approval before any chat request.
# LOOK FOR: an ask_model widget above the notebook, defaulting to no. Set it to yes, then rerun this cell.
ask_approved = A8.gate("ask_model", "Send two chat prompts (cost/quota)?")
print("Approved." if ask_approved else "Not approved yet: set the widget to yes and rerun this cell.")

# COMMAND ----------

# WHAT: sends the two approved prompts to the chat endpoint once and keeps the replies in memory.
# LOOK FOR: no output if approved; otherwise a note that the step was skipped. Do not retry errors in a loop.
answers = None
if ask_approved:
    values = ", ".join(f"(:q{i}, :p{i})" for i in range(len(prompts)))
    args = {**{f"q{i}": q for i, (q, _) in enumerate(ask)}, **{f"p{i}": p for i, p in enumerate(prompts)}}
    answers = spark.sql(f"""SELECT question, ai_query({sql_string(CHAT_ENDPOINT)}, prompt, failOnError => false,
modelParameters => named_struct('max_tokens', 300, 'temperature', CAST(0.0 AS DOUBLE))) AS reply
FROM VALUES {values} AS input(question, prompt)""", args=args).collect()
else:
    print("Chat requests skipped. You can still read the prompts above and do the evaluation and exercises.")

# COMMAND ----------

# WHAT: shows each answer with the sources it cited, or the error text if a request failed.
# LOOK FOR: the transfer answer cites the booking document; the weather question gets the refusal sentence.
if answers is not None:
    passages_by_question = dict(ask)
    for row in answers:
        passages = passages_by_question[row["question"]]
        reply = row["reply"]  # a struct with the fields result and errorMessage
        if reply["errorMessage"]:
            print(row["question"], "->", "ERROR:", reply["errorMessage"])
            continue
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", reply["result"])})
        sources = [passages[n - 1][1]["doc_name"] for n in cited if 1 <= n <= len(passages)]
        print(f"Q: {row['question']}\nA: {reply['result'].strip()}\nCited: {sources}\n"
              f"Refused: {REFUSAL.lower() in reply['result'].lower()}\n")
else:
    print("Skipped: approve the chat step above to see answers.")

# COMMAND ----------
# MAGIC %md
# MAGIC A model can ignore its instruction. Two things to check each time: **every claim has a citation that really
# MAGIC supports it**, and **an unanswerable question is refused rather than guessed**. Reading two answers is not a
# MAGIC test. The next section measures the retrieval half properly.
# MAGIC
# MAGIC ## 7. Evaluate retrieval
# MAGIC If retrieval misses the right document, the model cannot answer correctly however good it is. We score
# MAGIC retrieval with **hit at k**: for each evaluation question, is the expected document among the top k chunks?
# MAGIC This needs no chat model. We compare the word-overlap baseline with embeddings when you have them.
# MAGIC
# MAGIC **Predict:** which question will the baseline miss, and will embeddings fix it?

# COMMAND ----------

# WHAT: defines hit at k for any search function over the evaluation set.
# LOOK FOR: no output; hit_rate returns the share of questions whose expected document is in the top k chunks.
def hit_rate(search_function, k):
    hits = [any(chunk["doc_name"] == doc for _, chunk in search_function(q, k)) for q, doc in EVAL]
    return sum(hits) / len(EVAL)

# COMMAND ----------

# WHAT: scores the word-overlap baseline and, if you have embeddings, the embedding search.
# LOOK FOR: hit at 1 and hit at 3 for each retriever; embeddings should be at least as good as the baseline.
print(f"Word overlap: hit@1 {hit_rate(word_search, 1):.2f}, hit@3 {hit_rate(word_search, 3):.2f}")
if embeddings is not None:
    print(f"Embeddings:   hit@1 {hit_rate(embedding_search, 1):.2f}, hit@3 {hit_rate(embedding_search, 3):.2f}")
else:
    print("Embeddings:   skipped (approve the embedding step above)")

# COMMAND ----------

# WHAT: lists the questions each retriever misses at k = 3, so you can see why.
# LOOK FOR: questions that share no words with their document for word overlap; compare with embeddings.
retrievers = [("word overlap", word_search)]
if embeddings is not None:
    retrievers.append(("embeddings", embedding_search))
for name, function in retrievers:
    missed = [q for q, doc in EVAL if not any(c["doc_name"] == doc for _, c in function(q, 3))]
    print(name, "missed:", missed or "none")

# COMMAND ----------
# MAGIC %md
# MAGIC Eight questions is a small test, and these documents are short and tidy, so scores look better than real
# MAGIC documents would give. Treat the numbers as a way to compare two retrievers, not as a promise of quality. A real
# MAGIC evaluation uses more questions, includes some that the documents cannot answer and checks the answers as well.
# MAGIC
# MAGIC ## 8. Your turn
# MAGIC These two exercises use SQL on your chunk table and need **no model**.
# MAGIC 1. Exercise 8b.1: how many chunks does each document have?
# MAGIC 2. Exercise 8b.2: which chunks mention a refund? Return the document name and section.
# MAGIC
# MAGIC Use `IDENTIFIER(a8_doc_chunks)` for the table name. A blank answer shows the task and a hint.
# MAGIC `A8.solution("8b.1")` shows a worked answer. For 8b.2, think about the customer who asks "how do I get my money
# MAGIC back?": would your keyword query find the refunds section?

# COMMAND ----------

# WHAT: Check: compares your exercise 8b.1 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_8b_1 = """"""
A8.check("8b.1", answer_8b_1)

# COMMAND ----------

# WHAT: Check: compares your exercise 8b.2 answer with the course solution.
# LOOK FOR: a hint for a blank answer, otherwise feedback on your query.
answer_8b_2 = """"""
A8.check("8b.2", answer_8b_2)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. Recap, explain before you move on
# MAGIC Write your answers in the two cells below. Also think about: what would you change first if the assistant gave
# MAGIC a confident wrong answer about refunds, and how would you find out which step (retrieval or generation)
# MAGIC caused it?
# MAGIC
# MAGIC **Completion requires:** both exercises, the checks above, your explanations and, if you approved them, the
# MAGIC embedding and chat steps. Skipping or being blocked on a model step is fine: record it, and do not count that
# MAGIC outcome as complete.
# MAGIC
# MAGIC **Pause:** this lesson wrote nine files and one table. `99_pause_and_cleanup` removes both with the rest of
# MAGIC your course objects. No endpoint or index exists.
# MAGIC **Next:** `08c_vector_search` replaces the hand-built search with a managed Vector Search index.

# COMMAND ----------
# WHAT: asks why the model is given retrieved passages instead of being asked directly.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_8b_a = """"""
A8.reflect("8b.a", my_answer_8b_a)

# COMMAND ----------
# WHAT: asks why retrieval can miss a passage that does contain the answer.
# LOOK FOR: a prompt while blank; after you write, your answer beside a model answer.
my_answer_8b_b = """"""
A8.reflect("8b.b", my_answer_8b_b)

# COMMAND ----------

# WHAT: summarises the module and names the next notebook.
# LOOK FOR: the outcomes you can explain and the cleanup notebook.
A8.next_step(["Nine knowledge-base documents in your volume", "A chunk table with change data feed",
              "Word-overlap and embedding retrieval, scored with hit at k",
              "A grounded, cited prompt and an optional chat answer"],
             "08c_vector_search", "Replace hand-built retrieval with a managed index")
