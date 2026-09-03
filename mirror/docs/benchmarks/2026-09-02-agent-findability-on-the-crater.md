# An agent reaches the semantic crater. The labels are sound.

**Run:** 2026-09-02. Bed `F:/tmp/erb_blob_v09x.db` (947,531 genes), v09x bank
throughout — questions, gold and class labels from one bank, no cross-bank join.
**Receipt:** `benchmarks/dogfood/erb/receipts/agent_findability_2026-09-02.json`.
**Instruments:** `agent_search_cli.py` (read-only surface), `grade_findability.py`.

---

## The question

Every automated producer fails on the semantic crater. Query rewriting cannot
guess the terms (guessable fraction 0.114). Tail-only dense reaches k≤12 on 4 of
86. The cross-encoder converts 1 of 17 rescues. The natural next inference is
that the gold is unreachable, or the labels are wrong.

That inference was never tested. This tests it: give an agent the question, a
read-only search CLI, and an unlimited query budget, and see whether it can find
what no ranker reaches.

## Design

36 agents, one question each, blind to which arm they were in.

| arm | n | definition |
|---|---:|---|
| crater | 24 | semantic AND pool_absent on v09x — no producer reaches these |
| control | 12 | delivered gold at shipped defaults |

Both arms drawn from **needle index band 177–299**. That is not incidental: a
control drawn from a different index region can pass for structural reasons the
targets cannot, which is exactly the trap that invalidated a dense probe earlier
the same day (`2026-09-02-needle-bank-identity-hazard.md`).

Agents saw only the question and the CLI (`search`, `all`, `phrase`, `get`,
`near`, `src`). They never saw gold. Gold was joined afterwards. The grader
greps every agent transcript for access to gold files, receipts or docs, because
forbidding it in a prompt is an honour system rather than a control.

## Result

| arm | n | found gold | at rank 1 | median queries |
|---|---:|---:|---:|---:|
| **crater** | 24 | **14 (58%)** | 14 | 24 |
| control | 12 | 11 (92%) | 11 | 17 |

Leakage check: **clean**, no agent touched the answer key.

Every hit was at rank 1. When an agent finds the document, it knows it has found
it. The crater arm needed about 40% more queries than the control.

**So the information is reachable.** On cases where BM25, dense and the
cross-encoder all reach zero, an agent with an iterative loop reaches it more
than half the time.

## Adjudicating the misses

Nine of the ten crater misses self-reported the same obstacle — distractor
saturation, not vocabulary absence:

> "Not a retrieval failure — a disambiguation failure… I found at least six
> credible ones within the first four queries and could not tell which is
> authoritative."

That suggested the labels might be arbitrary. **They are not.** Three
independent judges per case, one explicitly tasked with *defending* the
benchmark label, read both the gold and the agent's pick:

| majority verdict | n |
|---|---:|
| `candidate_wrong` — the agent simply picked a wrong document | **6** |
| `question_underspecified` — several planted siblings satisfy the question | 2 |
| `duplicate_fact` — same answer, different carrier | 1 |
| `contradictory_fact` — the corpus disagrees with itself | 1 |
| **gold answers the question fully** | **10 of 10** |

Re-scoring generously — crediting the duplicate fact and the underspecified case
where the candidate also answered fully — moves the crater rate from 58% to
**67%**. The strict number is the honest headline; the generous one bounds the
labelling contribution at about 8 percentage points.

### The one clean labelling artifact

`erb_249` asks the default cooldown window. Gold: *"Cooldown semantics: 15m
(default). If you exceed the burst threshold… additional surges within 15m are
treated as the same event."* The agent answered **15 minutes**, correctly, citing
a different document carrying the same fact. All three judges ruled
`duplicate_fact`. One case in ten, not a pattern.

---

## What this corrects

Earlier in the session I read the term-guessability result — 88.6% of the terms
that would rescue gold are absent from what the query already retrieves — as
evidence that those terms are **arbitrary fingerprints separating near-identical
synthetic siblings**, i.e. noise. On that reading no producer could ever help,
cards included, and the right next step was a label audit.

The adjudication refutes it. Gold uniquely and fully answers in 10 of 10 cases.
Those terms are the corpus's **real vocabulary**, not noise. The reason a
question-only rewriter cannot produce them is that the question is written in the
asker's language and the document is written in the corpus's.

That is an argument **for** the document-side producer, and it now comes with a
mechanism rather than an analogy: the agent succeeds by doing manually what a
card precomputes — issuing a query, reading what comes back, learning the
corpus's own naming, and re-querying in that vocabulary. Roughly 24 queries of
iteration is the price of building that bridge at query time. A card pays it once
at ingest.

## What it does not establish

- **An agent is not a retriever.** Unlimited queries, document reading, and no
  latency or token budget. This is an upper bound on findability, not a
  comparison at equal cost. Nothing here says a card will capture the 58%.
- **n = 24** of a 61-needle cohort, single run, no repeat for variance.
- **The corpus is adversarially dense.** Judges repeatedly noted large clusters of
  parallel synthetic siblings. That makes the benchmark hard and, on 2 of 10
  cases, underspecified. It is a property to disclose next to any ERB number, not
  a defect that invalidates the cohort.
- **Two questions are genuinely underspecified** and one has a self-contradictory
  corpus. That is 3 of 24 crater needles worth flagging upstream, not a reason to
  discount the cohort.

## Consequence for the lane

The sequencing does not change, but the reasoning behind step 4 does. The cheap
producers were priced and failed; that stands. What changes is why cards remain
the live candidate: not because the other lanes are exhausted, but because the
one search strategy that demonstrably works on this cohort is *vocabulary
discovery through iteration*, and a document-side producer is the only proposal
in the lane that precomputes it.

The card gate in §5 of the activation contract is unchanged, and this adds one
precondition worth stating: a card must be evaluated on whether it reproduces the
bridge the agent builds, not merely on delivered gold. The agent's transcripts
are the reference for what that bridge looks like.
