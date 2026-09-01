# ledger

A normalized, machine-readable index of the Cymatix Context measurement trail,
built from the receipts already present in this clone. One JSON file,
`ledger.json`, plus the script that produced it. It covers both the
master-pinned mirror and the branch mirrors under `mirror-branches/`.

The ledger is an index, not an authority. It does not decide what a number
means; it records where the number came from and what basis it sits on, so that
a reader can go back to the receipt. `mirror/docs/benchmarks/BASELINES.md`
remains the authority on comparability, and the upstream copy of that file wins
on any conflict.

## What is in it

`ledger.json` has five content sections plus bookkeeping.

* `beds` (30) is one row per knowledge store that a measurement ran against:
  `id`, `family`, `genes`, `size_bytes`, `tagger_version`, `ingest_c`,
  `identity`, `notes`. The last three matter for comparability: under the
  BASELINES rules, cross-bed comparisons require matching `ingest_c` and
  matching `tagger_version`, and `unknown` is a legal `ingest_c` meaning not
  comparable across beds. Every bed built before 2026-08-30 is
  `tagger_version` 1.
* `measurements` (291) is one row per arm, per bed, per receipt:
  `date`, `bed_id`, `campaign`, `arm`, `n`, `delivered_gold_rate`,
  `recall_at_12`, `final_recall_at_12`, `median_gold_rank`, `basis`,
  `shipped_default`, `receipt`, `baselines_row`, `pr`, `git_sha`, `notes`.
* `kills` (21) is one row per lever that was measured and did not survive:
  `date`, `lever`, `bed_id`, `kill_criterion` (quoted from the receipt when the
  receipt has one), `result` (one sentence carrying the numbers), `receipt`,
  `verdict` (KILL, NULL, REFUTED or CORRECTED), `notes`.
* `graduations` (9) is one row per default that changed:
  `change`, `bed_id`, `delivered_before`, `delivered_after`, `paired`, `pr`,
  `receipt`, `notes`.
* `missing` (8) names receipts that a source in this clone cites but that are
  not archived here. They are listed rather than invented. Each entry says who
  names it and what, if anything, survives of its numbers.
* `unparsed` is empty. It exists so that a receipt whose schema the builder
  cannot read is reported rather than silently dropped.

`branch_mirrors` lists the six unmerged branches that contribute rows, with
their PR number and exported head sha, read from each mirror's `SOURCE.md`.

`counts` at the end of the file repeats the section sizes so a consumer can
check a load without walking the arrays.

## The basis caveat, which is the whole point of the file

Three different recall-like numbers appear in this project's receipts and they
are not interchangeable. The ledger keeps them in separate fields and records
which one a row is about in `basis`:

* `recall_at_12`, basis `map`. Candidate pool recall: was gold anywhere in the
  score map's top 12.
* `final_recall_at_12`, basis `final`. Final ranked order: was gold in the top
  12 of the order retrieval hands downstream.
* `delivered_gold_rate`, basis `delivered`. The post budget trim delivery
  slice, which is what a consumer actually receives.

These diverge, sometimes by double digits, under levers that move one and not
the others. Two worked examples from the ledger. The W2.1 cover walk arm
delivers exactly the same rate as its comparator (0.6297872340425532 on both)
while its final order recall falls from 0.6830 to 0.6553. The W2.4 seat floor
does the mirror image: pool and final order recall are unchanged at 0.6809 and
0.6830 while delivered climbs from 0.6298 to 0.6681.

There is also a documented case of prose disagreeing with its own receipts.
`mirror/docs/benchmarks/2026-08-14-encoder-isolation-scale-curve.md` originally
published the encoder isolation tables on the final order basis while calling
them delivered. The write-up carries the 2026-08-19 correction inline, and the
delivered figures in this ledger are read from the receipts, not from the
table. Where prose and receipt disagree, the ledger takes the receipt and says
so in `notes`.

## Rules the builder follows

1. Every number is copied out of a receipt file or out of a named BASELINES row.
   Three measurement rows have no receipt file at all; they name
   `baselines_row` instead, and their absent receipts are in `missing`.
2. Nothing is estimated and nothing is back filled from memory. A null field
   means the source does not state that number. Where a receipt carries a count
   but not a rate, the count goes into `notes` and the rate stays null. Older
   ladder receipts that predate the `delivered_gold_rate` field are handled this
   way.
3. One measurement per arm, per bed, per receipt. Repeated runs of the same arm
   (the order reversed pairs, the run1 and run2 confirms) each get their own
   row, because reproduction is part of the evidence.
4. `shipped_default` is computed mechanically for ladder receipts: true only
   when the arm is named `baseline`, runs the repo `cymatix.toml`, and overrides
   no knobs. An arm that merely re-pins the shipped value inside its own config
   TOML reads false. The 2026-08-27 wave-1 receipts run every arm as a full
   config file with the arm still named `baseline`, so the arm label carries the
   config basename after an `@`.
5. `receipt` paths are relative to the clone root. Master-pinned receipts start
   with `mirror/` and BASELINES.md cites the same files without that prefix.
   Receipts that live only on an unmerged branch start with `mirror-branches/`,
   and every such row names the branch, its PR and its exported head sha in
   `notes`, read from that mirror's `SOURCE.md`. Those rows are evidence from
   work that is not on master at `source_commit`, which is a different status
   from a merged receipt and is why the provenance sentence leads the note.
   Where the same path exists both under `mirror/` and under a branch mirror,
   the master copy wins: an identical branch copy is skipped, and a differing
   one is kept as its own row with both copies named. Today exactly one file
   exists in both places, `docs/benchmarks/BASELINES.md`, and the branch copy
   differs by a single added row (the 2026-08-31 floor width curve), which the
   builder reads for campaign attribution.
6. `campaign` is a BASELINES row name when a row's receipt glob matches the
   file, and otherwise the slug of the dated write-up that names the receipt.
   Where neither holds, the campaign is attributed by date to the only write-up
   from that day, or by date plus name overlap when several exist, and the
   `notes` field says which of those two weaker rules was used. Three rows are
   `uncategorized`: the 2026-07-11 SIKE bedsweep copies, whose write-up cites a
   different run of the same harness.

## Coverage

| family | beds | measurements | kills | graduations |
|---|---:|---:|---:|---:|
| erb | 8 | 152 | 17 | 7 |
| dogfood | 8 | 86 | 1 | 0 |
| enronqa | 5 | 27 | 2 | 1 |
| muloc | 1 | 8 | 1 | 0 |
| locomo | 2 | 7 | 0 | 0 |
| financebench | 1 | 3 | 0 | 0 |
| sike | 4 | 3 | 0 | 0 |
| snow | 1 | 3 | 0 | 0 |
| no bed | 0 | 2 | 0 | 1 |
| total | 30 | 291 | 21 | 9 |

Forty-three measurements and twelve kills come from branch mirrors rather than
from master. The muloc, locomo, locomo_obs and financebench beds are the only
ones in the archive built at `tagger_version` 2, so under the BASELINES tagger
rule none of them is comparable with any ERB or EnronQA row.

Measurement dates run from 2026-04-16 to 2026-09-01.

Receipt families that exist in the mirror but are deliberately not normalized
into `measurements`, because they publish a different metric vocabulary that
would have to be reshaped to fit: the snow harness per query blocks
(oracle tier and miss rate, three summary rows are recorded with null metrics so
the family is not silently absent), the shard recall receipts under
`mirror/docs/research/data` (recall at 1, 3, 5, 10 and MRR by within and cross
type), the 2026-07-16 class-gate and RRF-gate receipts
(`gold_delivered_text_rate`, inversion counts), the SPLADE curve receipts, the
blend serving receipts, the faithfulness pilot results, and the latency,
throughput, storage audit, cold start and server scaling receipts, which measure
time and bytes rather than recall. From the branch mirrors the same applies to the
ingest-decay and hub-cutoff re-probe receipts (milliseconds and edge counts), the
speedscope profile, the entity-autolink equivalence receipt, the two interloper
taxonomy waves and the three hit-slate samples, which carry raw per-needle slates
with no rollup, and the head-lane live inventory. Five of the eight 2026-09-01
Phase-1 probes publish decisions rather than rates and appear in `kills` instead
of `measurements`; the sixth, the bucket ledger, contributes one measurement row
because it independently recomputes the shipped baseline.

## Missing

Fourteen of the nineteen gaps in the first version of this ledger were closed by
the branch mirrors. Eight entries remain, and three of them are new.

Still missing:

* The EnronQA native baseline of 2026-08-29 and the per-arm EnronQA ladders
  behind both the v0.9.1 gate and the entity-hub A/B. The rolled-up receipts are
  mirrored and are what the EnronQA rows are read from; the 2026-08-29 native-bed
  cell still comes from its BASELINES row. The 2026-08-31 interloper mines name
  two of these absent ladders as their own basis receipts.
* The interrupted A1 pool-depth capture: the sqlite file and its 114-record
  checkpoint cache. The tooling and smoke JSONs are in `untracked/`, but the
  handoff warns that those smokes' VERDICT KILL lines are two-to-four-needle
  samples, so no kill is recorded from them and the admission gate is unresolved.
* The two SCBench campaign trees, which have BASELINES rows but no receipts.

New gaps, found while resolving the branch receipts:

* The bootstrap CI and the probability quoted for the phrase lane in the Phase-1
  handoff appear in no archived file, including the phrase probe that now backs
  the kill.
* The three phrase-as-reranking-feature counts over the 156 misses appear in no
  archived file either, so that kill row stays prose-sourced.
* A `tier_hard_floor_frac` ladder. The MULoc budget A/B names the fifteen
  percent of top hard floor as the mechanism behind its unmoved cohort and
  registers the ladder as the next cell, but it has never been run, so the
  hard-floor question is open rather than answered.

## Regenerating

From the clone root:

```
python ledger/build_ledger.py
```

Stdlib only, no arguments, no network, no writes outside `ledger/`. It reads
`mirror/`, `research-inbox/` and `untracked/` and prints the section counts plus
any receipt it could not parse. Re-running regenerates `ledger.json`
byte for byte except the `generated_at` timestamp.

The script is organized as one parser per receipt family, since the schemas vary
by era: the ablation ladder family (arm metrics flat or under `summary`, scanned
across the master receipt directory and every branch mirror's receipt
directories), the label and rollup ablation family, the July dogfood ladders and
baselines, the SIKE bedsweep, the snow harness, and then explicit per receipt
readers for the v0.9.1 gate sweep, the entity hub A/B, the sema ingest A/B, the
tagger v2 delta, the LoCoMo three way, the two budget doubling A/Bs, the floor
width curve, the EnronQA paraphrase crater, the Phase-1 bucket ledger and the
rate-free diagnostics (the dense ceiling probe, the two semantic audits and the
five interloper mines), whose shapes are one of a kind. Curated rows, the kills, the graduations
and the missing list are literal tables in the script, each carrying its source
in `notes` so it can be checked against the file it came from.
