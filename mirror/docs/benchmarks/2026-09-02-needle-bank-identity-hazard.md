# The ERB needle banks are misaligned by one from index 25

**Found:** 2026-09-02, while validating a tail-only dense probe.
**Revised the same day** after an adversarial re-check, which corrected an
over-broad first draft. See §"What the first draft got wrong".
**Severity:** invalidates one probe written this session. Does **not**
meaningfully damage any published receipt, and touches no shipped default.

---

## The hazard

The ERB needle banks resolved for different beds reuse the same names
(`erb_000` … `erb_468`) but are **offset by exactly one** from index 25 onward.
`erb_N` in the blob bank is `erb_{N+1}` in the v09x bank.

| | |
|---|---|
| names present in both `needles_resolved_blob.json` and `needles_resolved_v09x_full.json` | 469 |
| identical question wording | 25 (`erb_000` … `erb_024`) |
| shifted by exactly +1 | **444** (offset distribution is a single value: `{+1: 444}`) |

So joining by needle name across banks pairs each question with its neighbour's
data. Because the questions are unrelated in content, the pairing looks like
nonsense rather than like a subtle drift:

| needle | blob bank | v09x bank |
|---|---|---|
| `erb_177` | why a Western Europe tenant was routed to a Southeast Asia edge | the default pass rate in a low-bit-math change |
| `erb_183` | splitting a year-long accelerator commitment across three regions | when the healthcare-client deep dive is scheduled |

The blob bank was committed 2026-08-03 (`4dd71f0`); the v09x bank landed
2026-08-28 (`1114f79`).

**Why the offset exists:** the v09x bank resolves 470 needles and the blob bank
469. Both are positional mirrors of the upstream question file, so a single
dropped or added row near index 25 shifts everything after it.

---

## Labels are recoverable; the pairing is not

This is the distinction that decides how much damage a name join does.

`question_type` is **not** generated in this repo. `scripts/resolve_erb_needles.py`
copies it verbatim from the upstream Onyx EnterpriseRAG-Bench
`questions.jsonl` (`:124`, `:129`). Upstream carries ten classes, and — the
load-bearing detail — they sit in **contiguous blocks**.

Two consequences pull in opposite directions:

- **A class label survives an off-by-one almost everywhere.** Shifting by one
  inside a contiguous block lands on the same label. Only a block boundary
  mislabels.
- **A question-to-gold pairing never survives.** Every shifted needle gets a
  different document set.

So a probe that only needed a *class* is nearly unharmed. A probe that needed a
*pairing* is destroyed.

### Blob-era labelling needs nothing new

All 469 blob question texts appear verbatim in `needles_resolved_v09x_full.json`,
and the text-to-class map there is single-valued (0 ambiguous texts). A pure text
join labels **469 of 469** from a committed file, with no upstream file, no GPU,
no bed access:

```python
v = {x["query"]: x["question_type"] for x in load("needles_resolved_v09x_full.json")["needles"]}
label = v[blob_needle["query"]]      # 469/469, unambiguous
```

The same join labels every other committed ERB bank: erb10k 470/470, erb50k
470/470, carve 141/141, blob_probe30 30/30.

---

## What it invalidated

### `tail_only_dense_2026-09-02.json` — mine, discarded before use

Encoded v09x question text, scored against blob-era gold, joined by name. This
probe needed the **pairing**, so the offset destroys it completely. Renamed to
`tail_only_dense_INVALID_2026-09-02.json`, verdict overwritten to
`DISCARDED_INVALID_NEEDLE_JOIN`. Its output — 0/61 rescues, gold at dense ranks
41,884–766,684 of 809,251 — is near-random by construction and must not be
quoted in either direction.

**Its positive control passed, and that is the lesson.** Twenty control needles
ranked gold at dense positions 1–3 and looked healthy. They were `erb_000`–
`erb_023`, entirely inside the 25-needle aligned prefix, while every target was
`erb_177`+. The control's pass was an artifact of needle numbering.

> **Rule this earns.** Sample controls from the *same index region* as the
> targets, or the control cannot fail the way the targets can.

### `dense_ceiling_probe_829k_2026-08-31.json` — published, and it substantially stands

That probe encoded blob-era questions (correct for its bed) and attached class
labels by name from the v09x bank. Because it only needed the *label*, and
labels are blocky, the damage is small. Recomputed under the correct text join,
over its 200 ranked miss rows:

| | |
|---|---|
| rows whose class changes under the correct join | **2 of 200** (`erb_409`, `erb_449`) |
| classes affected | completeness, conflicting_info, constrained, miscellaneous (n = 2–16 each) |
| **semantic cell** | **bit-identical** |

```
semantic   published  n=86 le12=4 le50=8 median=3020.0
           text join  n=86 le12=4 le50=8 median=3020.0
basic      published  n=70 le12=23 le50=34 median=91.5
           text join  n=70 le12=23 le50=34 median=91.5
```

**So the receipt's headline conclusion holds.** On blob-era semantic questions
that lexical retrieval missed, dense-only exhaustive cosine reaches k≤12 on
**4 of 86**, with a median gold rank of **3,020** out of 829k. The commit
subject "gated-dense KILLED for the semantic crater" is supported by its own
data. Only the four small classes should be re-derived before being quoted.

One unrelated caveat on that receipt remains true and unresolved: the committed
`dense_ceiling_probe.py` reads `question_type` from `needles_resolved_blob.json`,
which carries none, so the script as committed would emit `"unknown"` for every
row. The published receipt has populated classes, so the join that produced it
is not in version control.

---

## What the first draft got wrong

The first version of this note claimed the banks contained "different question
sets", that "every per-class number" in the published receipt was invalid, that
its semantic-crater conclusion was "not established", and that blob-era class
labels were carried by "no committed file". An adversarial re-check refuted all
four:

| first draft | corrected |
|---|---|
| different question sets | an exact +1 offset from index 25 |
| every per-class number invalid | 2 of 200 rows; semantic bit-identical |
| gated-dense conclusion not established | it is established and stands |
| no committed file carries blob-era labels | a text join labels 469/469 |

The error was reasoning from "the join is wrong" to "everything joined is
wrong", without checking how much the join actually moved. A wrong join over a
blocky label sequence is mostly right by luck; a wrong join over per-question
gold is entirely wrong. The mechanism, not the mistake, decides the blast
radius — and that is measurable rather than assumable.

---

## Standing rules

1. **Never join ERB artifacts by needle name across banks.** Join by question
   text, which is proven to resolve 469/469.
2. **Every ERB receipt states its bank**, not just its bed. Bed identity does
   not pin question identity.
3. **A probe reading questions from one file and gold or labels from another is
   asserting an identity.** Assert it in code.
4. **Controls must come from the target's own index region.**
5. **When a join defect is found, measure its blast radius before invalidating
   anything.** Recompute under the correct join and diff.

Guard and pinning tests: `tests/test_erb_needle_bank_identity.py`.

```python
assert bank_a[n]["query"] == bank_b[n]["query"], f"{n}: banks disagree"
```
