# Beta full check on the 947k bed — exact reproduce, and Tier 5 confirmed dark

**Run:** 2026-09-02, branch head `21606a0` (= `origin/beta`), worktree
`website-reconnection-errors-fb70d7`.
**Bed:** `F:/tmp/erb_blob_v09x.db`, 947,531 genes, identity `11a05b91…`.
**Reference:** `ladder_v09x_w24_min_delivered_2026-08-28.json` at `b24a73c`.
**Receipt:** `benchmarks/dogfood/erb/receipts/ladder_v09x_beta_full_2026-09-02.json`.

---

## Result: bit-exact reproduce at n=470

| metric | 2026-08-28 (`b24a73c`) | 2026-09-02 beta (`21606a0`) | delta |
|---|---:|---:|---:|
| `delivered_gold_rate` | 0.6680851063829787 | 0.6680851063829787 | **0.000000** |
| `recall_at_k` | 0.6809 | 0.6809 | 0.000000 |
| `final_recall_at_k` | 0.6830 | 0.6830 | 0.000000 |
| mean rank of gold | 5.25 | 5.25 | 0.000000 |
| median rank of gold | 2.0 | 2.0 | 0.000000 |

Aggregate equality can hide offsetting per-needle moves, so the comparison was
run paired. Across **all 470 needles**, every non-latency field in `per_query` is
identical — `delivered_count`, `delivered_gold`, `delivered_gold_rank`,
`rank_of_first_gold`, `final_rank_of_first_gold`, `recall_hit`,
`final_recall_hit`, `gold_ranks`, `floor_appended`, `gate_kept`, `cover_walk`,
`recall_contribution`, `splice_n_candidates`. **Zero differences.**

This is the third exact-reproduce witness of this stack (after the 2026-08-30
gate sweep and the 2026-08-31 floor curve) and the first from the beta branch.

### Why an exact reproduce was the correct expectation

Against `origin/master` (`2644c3e` = v0.9.1) beta is **104 commits**, and none of
them touch query-time ranking:

- **MOVES RANKING:** none. No default, weight, tier, fusion, combinator, blend or
  assembly value changes.
- **INGEST-ONLY:** `entity_autolink_hub_cutoff` 0→200 (#425/#411), the
  `KnowledgeStore(entity_autolink=…)` kwarg (#424), the `idx_filename_gene` DDL
  (#424). All inert against a prebuilt bed.
- **INERT:** #429, #426, #427 (bench/docs/receipts, zero files under
  `cymatix_context/`), CLI/MCP aliases, wiki, CI, release tooling, tests.

A caution against a stale ref: the *local* `master` in this worktree is `ddfdf96`
= v0.9.0, so "beta is 171 ahead" is measured against the wrong base and sweeps in
the whole wave-1 flip (`rrf_k` 60→20, five-class `eps_band`,
`min_delivered_docs` 12). Those do move ranking, but they shipped in v0.9.1 and
are already inside the 0.6681 reference.

### Caveats that survive a clean result

- **`PYTHONHASHSEED` is unpinned** in this run and in the 2026-08-28 reference,
  and `filename_anchor.py:164` builds its stem set from a `list({…})` then
  truncates at 64, so the seed can decide which stems are queried. Exposure on
  ERB is probably nil, and the exact reproduce is consistent with nil — but it
  was not *controlled*, it was *unmeasured*. Cheapest closure: record
  `PYTHONHASHSEED` and `sys.version` in the receipt env block and pin
  `PYTHONHASHSEED=0`, as `bench_orchestrator.py:491` already does elsewhere.
- **`entity_autolink_hub_cutoff` is absent from the arm TOML**, so it resolves
  from the *code* default — the one shipped default that differs between the
  branches. It is ingest-only and the bed is prebuilt, so it cannot bind here.
  Note that "the arm config is field-identical" does not by itself establish
  this; the inertness argument does.
- **Latency moved and rank did not.** p50 21,102 ms against the reference's
  18,933 ms, mean 24,786, max 214,309. The bed's page cache had been touched by
  several read-only probes earlier in the session and other work shared the
  machine, so the latency axis of this receipt is environment-loaded and should
  not be cited. Rank axes are deterministic and are the citable part.

---

## What the run surfaced: Tier 5 is dark at 947k

PR #432's logging fired once:

```
Harmonic tier skipped: 115993 candidates would bind 231986 parameters,
over SQLITE_LIMIT_VARIABLE_NUMBER=32766 (#431); further skips on this store are silent
```

Three things follow.

**1. The harmonic tier contributes nothing on this bed.** It binds two
parameters per candidate, so it dies above 16,383 candidates. A 947k corpus
clears that easily — the logged query carried 115,993. The ladder's own arm
registry already records that harmonic has no query-time off-switch
(`use_harmonic` defaults True at `context_manager.py:2895` and
`knowledge_store.py:2259`, passed by no call site), so the tier is *on by design
and dead in practice*.

**2. The 0.6681 baseline is therefore a Tier-5-dark measurement.** That is not a
defect in the number; it is a scope fact that belongs next to it. Any change that
actually restores the tier is a ranking change and must be re-baselined, not
compared to this row.

**3. Beta carries only the logging half of the fix.** #432 converts a swallowed
`OperationalError` into one warning and a skip. It does not restore the tier. The
batched fix that would is on `claude/modest-pascal-2b1a9d` and is not in beta.

**A gap in the fix worth closing:** the message says *further skips on this store
are silent*, so a run cannot report how often the tier went dark. One log line
proves the mechanism and measures nothing. A counter — the tier-error counter
already drafted on that branch — would make the frequency visible without log
spam.

---

## Verdict

Beta is **rank-identical to shipped v0.9.1** on the 947k ERB bed at n=470. The
release gate's retrieval axis passes with no delta to explain. The only new
information is the harmonic tier's confirmed darkness, which is a pre-existing
condition now visible rather than a regression.
