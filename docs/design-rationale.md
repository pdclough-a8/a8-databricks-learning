# Design rationale and review

This page records why the course is designed the way it is, which published guidance supports each choice, where
the design still falls short, and what evidence would be needed to show that it works. It comes from a read-only
instructional-design review on 24 November 2026, followed by two changes described under
[Changes made after the review](#changes-made-after-the-review).

**What this page can and cannot claim.** The guidance cited below supports the *principles* the course uses. It
was tested on other learners and other subjects, mostly school and university students. It does not show that this
Databricks course produces competence in adult professionals; that needs the learner evidence described in
[Evidence still needed](#evidence-still-needed). Offline tests and live runs show that the code works, not that
people learn from it.

## Design rationale in brief

The course teaches Databricks through one continuous, synthetic business case, so learners spend their effort on the
platform rather than on switching contexts. Each lesson states its outcome, pre-teaches vocabulary, asks the learner
to predict before running, shows real platform operations as worked examples, and follows them with a checked
exercise and a self-explanation prompt. This reflects guidance to interleave worked examples with problem solving,
ask deep explanatory questions, connect concrete cases to abstract ideas and give corrective feedback [1], and to
manage cognitive load with small incremental steps and frequent formative checks [3]. The predict-then-run cycle
follows PRIMM, which outperformed a control group in a school study [4]. The SQL and Python routes give learners
different ways to work and to show what they know [7]; they are not "learning styles", which lack supporting
evidence [6]. The course's effectiveness has not yet been tested with learners.

## Where the design is supported

| Design feature | Where it appears | Guidance |
|---|---|---|
| One continuous case, frozen synthetic data, glossary before each lesson | `00_setup`, the "Terms in this lesson" cells | Prior knowledge and cognitive load [3]; connecting concrete and abstract [1, rec. 4] |
| Native platform operations visible; helpers limited to plumbing | [Notebook code standard](code-standard.md) | Worked examples [1, rec. 2] |
| Predict before running; `WHAT` and `LOOK FOR` comments | `00_setup` "How to read these notebooks" | PRIMM [4]; prediction prompts in notebooks [9] |
| Checked exercises with a hint, the first differing row and an explanation | `A8.check` | Quizzing with corrective feedback [1, rec. 5] |
| "In your own words" prompts on concepts such as pattern versus cause and leakage | `A8.reflect` | Deep explanatory questions [1, rec. 7] |
| SQL and Python routes offered as choices | `00_setup`, every exercise | Multiple means of action and expression [7]; not learning styles [6] |
| Safe sandbox, undo steps, cost gates and scoped cleanup | `A8.gate`, `99_pause_and_cleanup` | Lowers the risk barrier to practising (design judgement, not a cited finding) |

The IES guide grades its evidence by recommendation: quizzing to promote learning and asking deep explanatory
questions are rated strong; worked examples, spacing and linking concrete with abstract are rated moderate [1].

## Where the design falls short

In priority order. Items 1 and 3 have been partly addressed; see the next section.

1. **Outcomes and assessment are not fully aligned** [2]. Several modules promise creation or judgement ("build a
   pipeline", "run the gate", "roll back") but their checked exercises retrieve data. See the
   [alignment matrix](#alignment-matrix).
2. **Support does not fade.** Worked examples help novices, but full guidance can become ineffective or harmful as
   expertise grows (the expertise reversal effect) [5]. Later modules still supply every step. PRIMM's "Modify" and
   "Make" stages are mostly absent [4].
3. **Reflections gave a success signal for any answer.** A non-blank reflection used the green "correct" style
   without any marking, and self-judgement is unreliable compared with a targeted check [3].
4. **No spaced or cumulative practice.** Recaps are immediate recall. Spacing and retrieval at every stage are
   recommended [1, recs. 1 and 5]. Reusing one case lowers load but does not show transfer to a new situation.
5. **Readiness and scope are unclear for mixed audiences.** The course assumes some SQL, Python and, in Module 4,
   statistics; it has about 17 hours of estimated content and long dependency chains. Novice objectives should use
   verbs such as "recognise" and "use" rather than "design" and "evaluate" [3]. There is no prerequisite self-check
   or per-role core/extension split.
6. **Accessibility claims must stay narrow.** WCAG 2.2 [8] applies to this documentation site and to the content the
   course writes (cards, charts, HTML); it does not cover the Databricks interface. Charts need a text or table
   equivalent, results must not rely on colour alone, and the site has not been checked at 200% zoom, by keyboard
   only or with a screen reader. Present UDL [7] as a design framework, not as evidence of compliance.

## Changes made after the review

**Item 1, alignment.** The matrix below maps each module's outcome to its activities and evidence. Modules 13 to 15
gained one decision task each, run offline with no cloud calls:

- **13.3** (checked SQL): return the bronze rows the pipeline drops and the first quality rule each breaks.
- **14.2** (checked Python rule, `A8.check_rule`): write `my_gate` for a stricter release policy (no fall in
  grounding, a 0.05 allowance elsewhere, a missing metric fails). It is run against eight named cases.
- **15.2** (checked Python rule): write `choose_champion`, which decides which version holds the alias. It is run
  against six named cases, including "nothing passed" and "a passing version older than Champion".

`A8.check_rule` reports the first case decided wrongly, the arguments, the expected decision and *why* that
decision is right, so the feedback addresses the misconception rather than only the output.

**Item 3, reflections.** Every reflection now has two or three "a strong answer mentions" points. After the learner
writes, the card shows their answer, the points, then a model answer, in the neutral style, and says plainly that it
is not marked. Green is reserved for answers the course has actually checked.

## Alignment matrix

"Checked" means the course compares the learner's work with an expected result. "Self-checked" means the learner
compares their own answer with criteria and a model answer. Setup `A8.expect` checks verify the supplied steps
ran; they are not evidence of the learner's own work and are not listed.

| Module | Outcome, in short | Checked learner evidence | Self-checked | Remaining gap |
|---|---|---|---|---|
| 0 Setup | Settings saved; the business and vocabulary understood | none | 0.1, 0.2 | Vocabulary is not checked |
| 1 Lakehouse data | Load tables and a view; query them | 1.1, 1.2 (queries) | 1.a, 1.b | Loading steps are supplied, not learner-made |
| 2 Governance | Tags, grants and masking | 2.1, 2.2 (queries on the governed view) | 2.a, 2.b | Learner does not write a grant or mask |
| 3 Descriptive | Metrics view and dashboard | 3.1, 3.2 (incl. weighted average) | 3.a, 3.b | Dashboard and Genie work is not assessed |
| 4 Diagnostic | Explain differences; pattern versus cause; chance test | 4.1, 4.2 (gap, mix versus rate) | 4.a, 4.b | Interpretation of the chance test is self-checked only |
| 5 Predictive | Train, compare with a baseline, serve | 5.1 (expected attendees) | 5.a, 5.b | Feature and leakage choices are not checked |
| 6 Prescriptive | Recommend limits under uncertainty | 6.1, 6.2 (probabilities, variance) | 6.a, 6.b | The recommendation itself is not checked |
| 7 GenAI | Bounded model use and honest comparison | 7.1, 7.2 | 7.a | Prompt design is not checked |
| 8a Embeddings | Similarity by meaning | 8a.1, 8a.2 | 8a.a, 8a.b | No checked similarity judgement |
| 8b RAG | Grounded answers with citations and refusal | 8b.1, 8b.2 | 8b.a, 8b.b | Answer quality is self-checked |
| 8c Vector Search | Managed index and retrieval quality | 8c.1 (PySpark) | 8c.a, 8c.b | Retrieval metrics are not interpreted in a task |
| 9 Agents | Tool-using agent with validation | 9.1, 9.2 | 9.a, 9.b | Tool design and validation are not checked |
| 12 Deploy | Register, alias, serve, govern | 12.1, 12.2 | 12.a, 12.b | Release and permission decisions are not checked |
| 11 App | App reading governed data as its own principal | 11.1 | 11.a, 11.b | Grant design is self-checked |
| 13 Pipelines | Pipeline with quality rules, scheduled job | 13.1, 13.2, **13.3 (decision: dropped rows and rule)** | 13.a, 13.b | Learner does not author a new rule in the pipeline file |
| 14 Evaluate | Scoring rules and a release gate | 14.1, **14.2 (decision: own gate)** | 14.a, 14.b | Scorer authoring is not checked |
| 15 Release | Gate, alias move, release record, rollback | 15.1, **15.2 (decision: which version holds Champion)** | 15.a, 15.b | Rollback and canary are not learner decisions |

## Evidence still needed

- **Now available:** offline unit tests and historical live runs, recorded in [Validation evidence](validation.md).
  These show the code works.
- **Next:** observe three to five learners with different backgrounds thinking aloud through one or two modules.
  Record time taken, where they get stuck, hints used and misreadings of outputs. This is usability evidence, not
  proof of effectiveness.
- **Later:** a short task before and after a module that is not copied from the lesson, a delayed task a few weeks
  later, and confidence ratings to compare with performance.
- **Accessibility:** a keyboard, 200% zoom and screen-reader pass of this site and of the notebook cards and charts.

## References

1. Pashler, H., Bain, P., Bottge, B., Graesser, A., Koedinger, K., McDaniel, M. and Metcalfe, J. (2007).
   [*Organizing Instruction and Study to Improve Student Learning*](https://ies.ed.gov/ncee/wwc/PracticeGuide/1).
   IES Practice Guide, NCER 2007-2004. U.S. Department of Education.
2. Eberly Center, Carnegie Mellon University.
   [Align assessments, objectives, instructional strategies](https://www.cmu.edu/teaching/assessment/basics/alignment.html).
3. The Carpentries. Instructor Training:
   [Memory and cognitive load](https://carpentries.github.io/instructor-training/instructor/05-memory.html) and
   [Preparing to teach](https://carpentries.github.io/instructor-training/18-preparation.html).
4. Sentance, S., Waite, J. and Kallia, M. (2019). Teaching computer programming with PRIMM: a sociocultural
   perspective. *Computer Science Education*, 29(2-3), 136-176. [ERIC record](https://eric.ed.gov/?id=EJ1217966).
   Secondary-school learners aged 11 to 14.
5. Kalyuga, S., Ayres, P., Chandler, P. and Sweller, J. (2003). The expertise reversal effect. *Educational
   Psychologist*, 38(1), 23-31.
6. Pashler, H., McDaniel, M., Rohrer, D. and Bjork, R. (2008).
   [Learning styles: concepts and evidence](https://pubmed.ncbi.nlm.nih.gov/26162104/). *Psychological Science in
   the Public Interest*, 9(3), 105-119.
7. CAST (2024). [Universal Design for Learning Guidelines version 3.0](https://udlguidelines.cast.org/).
8. W3C (2023). [Web Content Accessibility Guidelines (WCAG) 2.2](https://www.w3.org/TR/WCAG22/).
9. Jupyter4Edu (2019).
   [Teaching and Learning with Jupyter, chapter 3](https://jupyter4edu.github.io/jupyter-edu-book/notebooks-in-teaching-and-learning.html).
   Practitioner guidance.
