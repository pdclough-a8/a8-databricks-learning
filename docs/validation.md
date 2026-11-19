# Validation ledger

**Release:** pilot v0.1.0. **Status:** offline checks passed, not live-workspace certified.

No deployment, model inference, cloud provisioning or GitHub publication is authorised as part of this build.
Offline checks use synthetic data and fake clients. Do not interpret them as a working workspace demonstration.

## Maintainer checks

Use Python 3.12 or 3.13 in an isolated environment:

```text
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m mkdocs build --strict
```

Optional local simulation, from the repository root after dependency installation:

```text
cd app/event_assistant
python -m streamlit run app.py
```

Never configure cloud credentials just to run simulation. Direct dependency versions are pinned;
transitive packages are resolver-selected, not a fully locked supply-chain snapshot.
The first validation install on Python 3.14 failed because the pinned Streamlit stack requires
PyArrow below 22, without a suitable 3.14 wheel. Use the supported Python range instead.

## Results, 19 November 2026

Validated on Windows with Python 3.12.13 and a repository-local `.packages` dependency target.
Python 3.13 is allowed by the package range but was not exercised in this build.

| Check | Result and scope |
|---|---|
| `unittest discover -s tests -v` | 30 passed, including five Streamlit AppTest cases |
| SQL reference answers | Supplied UI query executed in independent SQLite; all expected city/availability facts checked |
| Prompt parity | Playground system/user examples match the code's full six-record contract |
| App interaction | Default simulation, unsupported/blank input, explicit mocked live submission, reruns, mode changes and sanitised errors |
| Lifecycle intent | Fake Spark/Apps clients: atomic CTAS intent, rerun, changed data, ownership collision, scoped deployment, partial/repeated cleanup |
| SDK contract | App creation body round-tripped through pinned SDK schema; serving-endpoint OpenAI client exists |
| Notebook contract | All six notebook/solution sources parse; run targets resolve; defaults execute under fake context without writes or cloud-client construction |
| Site | `mkdocs build --strict` passed; internal links/navigation targets checked |
| Visual spot check | Course home and real local Streamlit app inspected in browser; Leeds simulation rendered both IDs and correct values |
| Contrast | Selected ink/accent combinations checked against white and grey, at least 4.5:1; not a full accessibility audit |

The final local app check used the shipped configuration from the app folder, with a loopback-only
port override and no cloud credentials. Preview screenshots are saved as `preview-course.png` and
`preview-app.png` at the repository root. The temporary app server is stopped after validation.
Browser inspection covered one viewport, not a complete keyboard, mobile or screen-reader review.

AppTest emitted a bare-context warning and a CORS/XSRF configuration warning; Streamlit forced CORS
protection on rather than disabling XSRF. The real local server started with the shipped production-mode
configuration. No user-global settings were changed. Fake lifecycle clients verify intent and guard
behaviour, **not** Spark transaction semantics, Databricks auth or real permission enforcement.

## Required live acceptance, not run during build

An instructor must record workspace/cloud, runtime, endpoint/API compatibility, date, observed result
and evidence for every row before advertising this as classroom-verified.

| Scenario | Acceptance evidence | Status |
|---|---|---|
| Fresh UI and code copies | Tree intact; widgets and relative `%run` work | Not run |
| Existing authorised schema, restricted create rights | Clear blocker; no fallback writes | Not run |
| UI upload + code route switch | Same six rows/marker recognised, no append | Not run |
| Code create rerun and interrupted create | Atomic table fixture or clean failure; no duplicates | Not run |
| Ownership conflict | No replacement, deployment or deletion of conflicting objects | Not run |
| Playground vs notebook live calls | Three answers judged against the same rubric | Not run |
| Apps create/source read/deployment | Approved path and least-privilege identity grants | Not run |
| App simulation and live | Distinct labels; correct facts/refusal; no inference on rerun alone | Not run |
| App lacking model query permission | Sanitised error, no raw credential/request leak | Not run |
| Stop/resume and source edit | Same artefacts; restart/redeploy behaviour observed | Not run |
| Final and partial teardown rerun | Only exact marked objects removed, absence verified | Not run |
| Brand/accessibility review | Official assets/tokens approved; keyboard/mobile/browser checks | Not run |

Never relax the expected answer to make a model pass. A missing capability is a recorded blocker,
not a reason to add shared privileges or create unapproved infrastructure.
