# Tier-0 Implementation Plan — Dense Recall + Score-Scale Fix

**Date:** 2026-05-16
**Status:** PLANNING ONLY. No source code modified. Verified against live code.
**Author:** software-architect synthesis of the 5-agent deep review.
**Scope:** the two coupled Tier-0 items from the deep review —
(1) enable BGE-M3 dense retrieval end-to-end, (2) fix the fusion-mode
score-scale contradiction in sharded mode. Plus the fixture re-backfill +
re-bench exit criterion.

This plan covers the two items, the two design decisions a human must
choose, the reviewable PR sequence, and the risk register. Companion
research reviews (`research-ingest-data-processing.md`,
`research-kv-tagging.md`, `pipeline-01-ingest.md`,
`pipeline-02-retrieval-fusion.md`, `pipeline-03-scoring-conflict.md`) hold
the deeper findings; this document is the actionable Tier-0 slice only.

---

## 1. Claim verification against the live code

Every load-bearing claim from the five review files was re-checked against
the current tree. Verdicts below; line numbers are current as of this
read.

### 1.1 Dense retrieval is dark — VERIFIED (with one nuance)

| Claim | Verdict | Evidence |
|---|---|---|
| `helix.toml` sets `dense_embedding_enabled = false` | **TRUE** | `helix.toml:275` |
| `helix.toml` sets `fusion_mode = "additive"` | **TRUE** | `helix.toml:298` |
| `upsert_doc` never writes `embedding_dense_v2` | **TRUE** | `knowledge_store.py:1079-1113` — the INSERT is exactly 24 columns: `gene_id, content, complement, codons, promoter, epigenetics, chromatin, is_fragment, embedding, source_id, repo_root, source_kind, observed_at, mtime, content_hash, volatility_class, authority_class, support_span, last_verified_at, version, supersedes, key_values, compression_tier, last_seen`. No `embedding_dense` / `embedding_dense_v2`. The `embedding` column carries the 20-D SEMA vector only. |
| `embedding_dense_v2` is written **only** by the backfill script | **TRUE** | `scripts/backfill_bgem3_v2.py:143-146` is the only `UPDATE genes SET embedding_dense_v2`. In `knowledge_store.py` the column is only ever *read* (`:2372`, `:2426-2427`, `:2438`, `:2491`). |
| `build_fixture_matrix.py` never backfills dense vectors | **TRUE** | The builder calls `genome.upsert_doc(...)` (`build_fixture_matrix.py:303`) / `genome.upsert_gene(...)` (`:521`) and never imports `BGEM3Codec` or runs the backfill. Both blob (`build_profile`) and sharded (`build_profile_sharded` → `_build_one_shard`) paths. |
| Dense recall is code-gated on `fusion_mode == "rrf"` | **TRUE** | `knowledge_store.py:1922`: `if self._dense_embedding_enabled and self._fusion_mode == "rrf":` — the `query_docs_dense_recall` call at `:1925` is inside this branch. Comment at `:1918-1921` confirms this is deliberate ("keep byte-identical compatibility with pre-Stage-3 ranking"). |
| Per-shard genomes inherit additive + dense-off | **TRUE** | `sharding.py:196` hard-sets `ShardedGenomeAdapter._dense_embedding_enabled = False`. Per-shard `Genome`s are constructed in `ShardRouter._open_shard` with `**self._genome_kwargs` (the kwargs `HelixContextManager` passed from `context_manager.py:481/491` — `dense_embedding_enabled=False`, `fusion_mode="additive"`). So every shard runs `query_docs` in additive mode → the `:1922` gate is false → per-shard dense recall is skipped. |
| `query_docs_dense_recall` returns `[]` when v2 column empty | **TRUE** | `knowledge_store.py:2487-2495` — `_ensure_dense_matrix()` returns `None` and the method returns `[]` with a one-time WARN. |

**Nuance #1 — the bench corpus path is stale in the prompt.** The task
brief says the 6 bench genome DBs live at
`F:/Projects/helix-context/genomes/bench/matrix*`. On disk *right now*
`genomes/` is **empty** — no `matrix/` and no `matrix-sharded/`.
`build_fixture_matrix.py:1113` confirms the default `--out-dir` is
`F:\Projects\helix-context\genomes\bench\matrix` (blob →
`<out-dir>/<profile>.db`, sharded → `<out-dir>-sharded/<profile>/`). So
the fixtures must be **rebuilt** as part of this effort; there is no
existing matrix to merely backfill. The standing reproduction DBs that *do*
exist are `benchmarks/genome-bench-2026-05-08.db` (and `-frozen`),
`genome-bench-N1000.db`, `genome-bench-2026-04-10.db` — single-blob DBs the
reviews reproduced against. **Treat the fixture step as build-then-embed,
not backfill-in-place** (see §6).

**Nuance #2 — blob RRF mode does NOT have the score-scale bug; only
sharded does.** `pipeline-03` is precise about this, but it is worth
stating plainly: in blob mode under `fusion_mode == "rrf"`,
`knowledge_store.py:2259-2283` publishes `last_query_scores = final_scores`
where `final_scores[gid] = fuser.all_scores()[gid] + rerank_additive[gid]`
— i.e. genuine RRF-scale (~0.02–0.35) plus small re-rank additives. So a
blob genome run with `fusion_mode = "rrf"` feeds RRF-scale numbers to the
gates, and `_fusion_mode = "rrf"` is *true* for it. The contradiction is
**exclusively** the sharded path, where `ShardRouter.query_genes`
publishes IDF-corrected *additive* scores (`shard_router.py:611`) while
`ShardedGenomeAdapter._fusion_mode = "rrf"` (`sharding.py:181`). This
matters for Design Decision 2: fixing the sharded publisher is sufficient;
no blob-mode score-scale change is needed.

### 1.2 The score-scale contradiction — VERIFIED

| Claim | Verdict | Evidence |
|---|---|---|
| `ShardRouter` runs RRF for the cross-shard merge | **PARTLY — RRF is a tiebreaker, not the primary key** | `shard_router.py:559` `rrf_all = fuser.all_scores()`; `:565-572` sorts by `(-corrected, -rrf_all, gid)`. RRF is the **secondary** sort key. The **primary** key is `corrected`, the IDF-corrected additive score. The review's phrasing "runs RRF for the cross-shard merge" is loosely true but the reviews' own detail (pipeline-03 Finding 1) correctly says RRF is "used only as a tertiary sort tiebreaker" — that detail is the accurate one. |
| `ShardRouter` publishes raw BM25-scale `last_query_scores` | **TRUE** | `shard_router.py:610-611`: `self.last_query_scores = {gid: corrected[gid] for gid in ranked_ids}`. `corrected` is built at `:532-538` as `adj = raw * m` (raw = per-shard `Genome.last_query_scores`, additive BM25-scale; `m` = IDF multiplier clipped `[0.5, 3.0]`) and then `:551-557` multiplies by the `1.15` doc-type boost. Net scale: `BM25-additive × [0.5,3.0] × [1.0,1.15]`. **Not** RRF-scale. |
| `ShardedGenomeAdapter._fusion_mode = "rrf"` | **TRUE** | `sharding.py:181`. Docstring `:174-181` explicitly claims "any sharded read is RRF-fused … sharded RRF scores (~0.26-0.40)". That claim is false for `last_query_scores`. |
| `tier_logic.py` disables the abstain absolute-floor when `fusion_mode=="rrf"` | **TRUE** | `pipeline/tier_logic.py:110`: `skip_absolute_floors = (fusion_mode == "rrf")`. Used at `:176` (ABSTAIN gate), `:219` (TIGHT), `:229` (FOCUSED). `fusion_mode` arrives via `context_manager.py:1195` `getattr(self.genome, "_fusion_mode", "additive")` → `"rrf"` for a sharded adapter. |
| `compute_confidence` betas are BM25-calibrated | **TRUE** | `helix.toml:360-363` and `scoring/know_calibration.py:57-65`: `betas = [-2.0, 2.0, 1.5, 0.7, 1.8, 1.5]`, `s_ref = 1.0`, `g_ref = 0.5`, `emit_floor = 0.55`, `calibrated_at` unset. `s_ref = 1.0` saturates `tanh(top_score)` near `top_score ≈ 2–3` — a BM25 scale. |
| `server/helpers.py` feeds `last_query_scores` to `compute_confidence` | **TRUE** | `server/helpers.py:251-255` reads `helix.genome.last_query_scores`, derives `top_score` / `score_gap`; `know_decision.decide_know_or_miss` → `compute_confidence` at `know_decision.py:433-440`. |
| Confidence pins below `emit_floor` under RRF scale | **TRUE (analytic)** | pipeline-03's table re-derives `compute_confidence` with defaults: a genuine-RRF top-1 (`top≈0.40`, `gap≈0.005`) → `confidence ≈ 0.23`, well under `emit_floor = 0.55`. Only landing all three side signals (`lexical_dense_agree` + `coordinate_confidence ≥ 0.5` + `freshness = 1.0`) clears the floor. |

**Nuance #3 — the bug fires on BOTH score interpretations, asymmetrically.**
- The *abstain gate* (`tier_logic.py`) is *told* "rrf" and so **skips its
  absolute floors** — but the numbers it receives are BM25-scale, where
  those floors *would have been correct*. It then runs the RRF
  normalized-ratio gate (`tier_logic.py:143-153`), whose `1.5` threshold
  was tuned against *genuine* RRF distributions, not the
  `additive × IDF × doc-boost` distribution sharded actually produces.
  The gate is mis-calibrated either way.
- The *know/miss* path (`know_calibration.py`) has **no** fusion-mode
  branch at all — it always applies `s_ref = 1.0` BM25 betas. Fed
  BM25-scale sharded scores it is "mis-tuned for the IDF-corrected
  additive scale"; fed genuine RRF-scale (the blob-RRF future) it is
  "too cold". The two gates that decide conflict→abstain-vs-pick are
  calibrated for two *different* scales, **neither** matching the data.

**Nuance #4 — `last_query_scores` is mutated post-publish by the
refiners.** `scoring/blend.py:apply_candidate_refiners` reads
`genome.last_query_scores`, *adds* cymatics/harmonic/TCM bonuses, and
writes the map back (`blend.py:64-71`, `:113-119`, `:124-137`). So by the
time `server/helpers.py` and `tier_logic.py` read the map, it is
`published_score + refiner_bonus`. Any score-scale fix must account for
this: the refiner bonuses (cymatics `≤ 0.5`, harmonic `0–1.5`) are
*absolute* magnitudes tuned for the BM25 scale. Under genuine RRF scale
(~0.3 max) a `+1.5` harmonic bonus would utterly dominate the fused
signal. **This is a real coupling and is called out in the risk register
(R7).**

### 1.3 Net verified picture

The deep review's Tier-0 conclusion stands. To restate precisely:

1. **Dense recall is dark in every bench profile** — for *three* stacked
   reasons: (a) `dense_embedding_enabled = false` in config; (b) even with
   it on, `knowledge_store.py:1922` only calls dense recall under
   `fusion_mode == "rrf"`; (c) even with both fixed, the fixtures have
   `embedding_dense_v2 = NULL` because neither `upsert_doc` nor the
   fixture builder ever computes it. **All three must be fixed together**
   or dense recall stays dark.
2. **The sharded path lies about its score scale.** `ShardRouter`
   publishes additive-scale scores; `ShardedGenomeAdapter` labels them
   `"rrf"`. This (a) disables the abstain absolute-floor on every sharded
   query and (b) feeds wrong-scale numbers into `compute_confidence`,
   pinning confidence below `emit_floor` → `MissBlock`/abstain on close
   candidates.

The two are coupled through the **fusion-mode decision**: turning dense
recall on requires `fusion_mode = "rrf"` (because of the `:1922` gate),
and `fusion_mode` is *also* the flag that drives the score-scale
contradiction. You cannot light up dense recall without confronting the
sharded score-scale story. Hence one coherent effort.

---

## 2. Design Decision 1 — the fusion-mode story

### 2.1 The problem

`fusion_mode` is overloaded. It currently controls **three** distinct
things:

1. Which ranking math `knowledge_store.query_docs` uses (additive
   accumulator vs RRF rank-fusion).
2. **Whether dense recall runs at all** (`knowledge_store.py:1922` gate).
3. How the downstream gates interpret the score scale
   (`tier_logic.py:110`, transitively `know_calibration`).

Today: `helix.toml` default `additive`; sharded adapter forces `"rrf"` for
the *label* but each shard still runs `additive`; blob runs whatever
`helix.toml` says. The result is an internally inconsistent story where
"hybrid retrieval" is lexical-only and the score-scale meaning of
`last_query_scores` differs by code path.

### 2.2 Option A — RRF everywhere (flip the default; retire additive on the timeline)

Make `fusion_mode = "rrf"` the global default, applied to blob and to
every per-shard genome. Keep the additive code path for one release per
the deprecation timeline already written into `helix.toml:296-297`
("v(N) ships additive default; v(N+1) flips to rrf default; v(N+2) removes
the additive code path"), then delete it.

**Concrete diffs:**

- `helix.toml:298` — `fusion_mode = "additive"` → `fusion_mode = "rrf"`.
- `helix_context/config.py:308` — the code default `"additive"` →
  `"rrf"` (so a config without the key still gets RRF, and tests that
  build a bare `HelixConfig` match the shipped default).
- Per-shard inheritance: `ShardRouter._open_shard` passes
  `**self._genome_kwargs` to each shard `Genome`. With `helix.toml`
  flipped, `HelixContextManager` already passes `fusion_mode="rrf"` into
  `open_read_source` (`context_manager.py:491`) → into the router kwargs
  → into each shard. **No `shard_router.py` change needed for the flag to
  propagate** — but see §3 PR-3 for the explicit assertion/test that it
  *does*.
- `sharding.py:181` — `ShardedGenomeAdapter._fusion_mode = "rrf"` becomes
  *true* rather than aspirational (the docstring `:174-181` can be
  corrected to describe reality).
- The `knowledge_store.py:1922` dense gate (`and self._fusion_mode ==
  "rrf"`) now passes for blob; dense recall fires. (Per-shard dense is
  handled separately — see Option discussion below and PR-1.)

**Pros:** one mode, one score scale (genuine RRF) across blob and
per-shard; matches the documented deprecation plan; RRF is the
literature-standard fusion for incommensurable retrievers (Cormack 2009;
Bruch 2023) — the right destination once tag + FTS + SPLADE + dense are
all live; removes the "dense only under rrf" surprise by making rrf
universal.

**Cons:** flips the ranking math for **every** existing deployment in one
release — the largest blast radius; the additive→RRF transition was
explicitly designed as a staged A/B and Option A short-circuits the
A/B; per-tier weights (`fts5_weight`, `splade_weight`, …) are RRF
*post-multipliers* under RRF but raw *caps* under additive — they have
never been measured as RRF multipliers on the full matrix; the refiner
bonus scale problem (Nuance #4 / R7) becomes universal, not sharded-only.

### 2.3 Option B — decouple dense participation from `fusion_mode`; keep additive as the default

Stop using `fusion_mode` as the on/off switch for dense recall. Let dense
recall run in **both** modes; in additive mode union the dense hits into
`gene_scores`, in RRF mode add them as a Fuser tier (as today). Keep
`helix.toml` default `additive` for now; flip to RRF later strictly as a
measured A/B per the existing timeline.

**Concrete diffs:**

- `knowledge_store.py:1922` — change
  `if self._dense_embedding_enabled and self._fusion_mode == "rrf":`
  to `if self._dense_embedding_enabled:`. Inside, branch: under RRF feed
  the Fuser tier (existing `:1932-1934`); under additive, merge dense hits
  into `gene_scores` with a scaled contribution. The existing comment at
  `:1911-1917` already notes "this also seeds gene_scores in additive
  mode" — but the *additive merge* needs a real weight, not the `1e-9`
  epsilon currently used (`:1946`). Suggest `gene_scores[gid] +=
  cosine * self._dense_weight` with `dense_weight` raised from `1.0` to a
  BM25-comparable scale (tag-exact is `3.0`) — i.e. add a separate
  `dense_additive_weight` knob (default ~`4.0`) so additive-mode dense is
  not "roughly noise next to the lex weights" (the `:1913-1914` admission).
- No `helix.toml` `fusion_mode` change. `dense_embedding_enabled` still
  flips to `true` (that part is unconditional — see §2.5).
- Sharded: per-shard `Genome`s run additive but now *do* run dense recall
  (the `:1922` gate no longer blocks it). The adapter's
  `_dense_embedding_enabled = False` at `sharding.py:196` stays — that
  flag only governs the *adapter-level* dense pass, which genuinely
  doesn't exist; per-shard dense is what we want and it now happens.

**Pros:** preserves the staged additive→RRF A/B the team explicitly
designed; smallest ranking-behavior blast radius (additive math unchanged
for everyone, dense is *added* as a signal); decouples a confusing
implicit coupling cleanly — dense recall stops being a hidden side effect
of a fusion knob; the additive-mode dense merge is a genuinely new recall
signal that can be measured *independently* of the RRF flip.

**Cons:** additive-mode dense merge needs a hand-tuned `dense_additive_weight`
(additive scores are incommensurable by construction — that is the whole
reason RRF exists; bolting dense onto the additive accumulator inherits
the scale-mismatch disease pipeline-02 F3 documents); leaves *two* live
ranking paths longer; does **not** by itself fix the sharded score-scale
contradiction (that is Decision 2 — but note Option B keeps sharded on
additive scale, which makes Decision 2 Option (a) — publish RRF — a
*bigger* change relative to Option B than relative to Option A).

### 2.4 Recommendation — **Option B for this Tier-0 effort, with a fast follow to Option A**

Rationale:

1. **The Tier-0 goal is "dense recall actually firing", not "ship RRF
   everywhere".** Option B achieves the stated goal (dense vectors at
   ingest, fixtures backfilled, dense recall firing in blob *and*
   sharded) with the *smallest* change to ranking math. The additive
   accumulator stays byte-identical for the lexical tiers; dense is
   purely additive on top.
2. **It preserves the measurement discipline.** The whole point of the
   `additive` default + deprecation timeline is a clean A/B. Option A
   throws the additive baseline away in the same release that introduces
   dense recall — you could never tell whether a bench delta came from
   dense recall or from the additive→RRF flip. Option B isolates the
   variables: PR-1/PR-2 add dense-on-additive (one variable); a *later*
   PR flips `fusion_mode` (second variable, separately measured).
3. **It de-risks the score-scale fix.** Under Option B, sharded stays on
   additive scale, and Decision 2 can fix the *labelling* (set
   `_fusion_mode = "additive"`) — the lower-risk, fully-reversible option
   — rather than re-plumbing the publisher.
4. **The cost is one tunable weight** (`dense_additive_weight`). That is a
   real cost (it inherits the additive scale-mismatch problem) but a
   *bounded* one, and the matrix re-bench will calibrate it.

The fast follow (a post-Tier-0 PR, not in this plan's critical path) is to
flip `fusion_mode = "rrf"` as its own measured A/B and, if it wins,
proceed down the documented v(N+1)/v(N+2) retirement of additive. That
flip is the right *destination*; it should just not ride in the same PR
that lights up dense recall.

**If the human prefers Option A** (one mode, done): it is defensible — RRF
*is* the correct end state and the deprecation plan is already public. The
cost is accepting an un-isolated A/B for one bench cycle and doing the
refiner-scale fix (R7) up front. If Option A is chosen, fold the
`fusion_mode` flip into PR-3 and drop the `dense_additive_weight` knob
from PR-1.

---

## 3. Design Decision 2 — the score-scale fix

Applies to the **sharded path only** (Nuance #2). Two options.

### 3.1 Option (a) — make `ShardRouter` publish RRF-scale scores

Change `ShardRouter.query_genes` so `last_query_scores` carries the
genuine RRF fused score (`rrf_all`, already computed at
`shard_router.py:559`) instead of the IDF-corrected additive `corrected`
map. The `_fusion_mode = "rrf"` label then becomes *true*.

**Concrete diff:**

- `shard_router.py:610-611` — currently
  `self.last_query_scores = {gid: corrected[gid] for gid in ranked_ids}`.
  Change to publish `rrf_all` (the `Fuser.all_scores()` output). Two
  sub-choices: keep `corrected` as the *sort* key (so the IDF-correction
  and doc-type boost still re-order the result list — they were designed
  for that) and only publish `rrf_all` as the *score map*; **or** sort by
  `rrf_all` too. Recommend the former — keep `corrected` as the ranker,
  publish `rrf_all` as the reported scale — so the IDF/doc-boost work is
  not thrown away. This means the published map's *ordering* may not
  exactly match the result-list order; the gates only consume the
  *distribution* (top/mean/min/gap), not the order, so that is acceptable
  — but it must be documented.
- `sharding.py:181` `_fusion_mode = "rrf"` — now correct, no change.
- The refiner coupling (Nuance #4 / R7) bites here: `scoring/blend.py`
  adds absolute-magnitude bonuses (cymatics `≤0.5`, harmonic `0–1.5`) to
  whatever is in `last_query_scores`. If that map is now RRF-scale
  (~0.3), the bonuses dominate. **Option (a) forces an accompanying
  refiner-scale fix** — either scale the refiner bonuses by the RRF score
  range, or apply refiners to a separate map. This is non-trivial.

**Blast radius — every consumer of `last_query_scores`** (enumerated from
the grep; sharded-reachable consumers in **bold**):

| Consumer | File:line | What it does with the scores | Affected by (a)? |
|---|---|---|---|
| **abstain gate** | `pipeline/tier_logic.py:81-193` (via `context_manager.py:1192`) | top/mean/min ratio + (skipped) absolute floor | **Yes** — would finally receive genuine RRF-scale, matching its `skip_absolute_floors`+norm-ratio design. Good. |
| **know/miss block** | `server/helpers.py:251-258` → `know_decision.py:433` → `compute_confidence` | `top_score`, `score_gap` into the logistic | **Yes** — but `compute_confidence` betas are BM25-calibrated; RRF-scale input pins confidence < `emit_floor` (pipeline-03 Finding 2). Option (a) alone makes know/miss *worse* unless betas are also recalibrated. |
| **packet know/miss** | `context_packet.py:431/441` | same `compute_confidence` path | **Yes** — same caveat. |
| **legibility / slate / trim** | `context_manager.py:1324, 2228-2259, 2435, 2590, 2673` | confidence markers, slate ordering, lowest-ranked trim | **Yes** — these read relative ordering and a confidence marker; scale-change is mostly cosmetic but the confidence-marker thresholds (if any absolute) would shift. |
| **refiners** | `scoring/blend.py:64-137` | *adds* absolute bonuses, writes map back | **Yes — and this is R7.** Forces the refiner-scale fix. |
| `/debug` + admin | `routes_admin.py:288`, `routes_context.py:315-323/766-772` | surfaces scores in debug payloads | Cosmetic. |
| blob `query_docs` | `knowledge_store.py:2182/2283` | publishes its own map | **No** — blob already publishes RRF-scale under RRF (Nuance #2). Option (a) only touches the *router*. |

**Calibration risk:** HIGH. Option (a) makes the sharded score scale
*genuinely* RRF — which is correct — but the `compute_confidence` betas
were never calibrated for RRF. So Option (a) **must** be paired with a
beta recalibration (`scripts/calibrate_know_confidence.py` exists for
exactly this) or know/miss regresses from "wrong-scale" to
"uniformly-cold". A prior task explicitly called beta recalibration **"a
separate larger task"** — Option (a) pulls that larger task onto the
Tier-0 critical path.

**Reversibility:** MEDIUM. The publisher change is a one-line revert, but
the accompanying refiner-scale fix and beta recalibration are not — once
betas are recalibrated for RRF, reverting the publisher leaves betas
mis-tuned for additive. Option (a) is a one-way door once its dependencies
land.

### 3.2 Option (b) — make the label honest: `ShardRouter` publishes additive-scale, `_fusion_mode = "additive"`

Stop claiming the sharded path is RRF-fused for `last_query_scores`
purposes. The router *already* publishes additive-scale `corrected`
scores; just relabel. Set `ShardedGenomeAdapter._fusion_mode = "additive"`
so the gates interpret the BM25-scale numbers correctly: the abstain
absolute floors run on the BM25-scale scores they were calibrated for, and
`compute_confidence`'s BM25 betas (`s_ref = 1.0`) match the BM25-scale
input.

**Concrete diff:**

- `sharding.py:181` — `_fusion_mode: str = "rrf"` →
  `_fusion_mode: str = "additive"`. Update the docstring `:174-181` to
  describe reality: the router fuses *ranks* as a tiebreaker but publishes
  IDF-corrected *additive* scores; downstream gates therefore treat the
  sharded path as additive-scale.
- `shard_router.py:606-615` — no code change; the comment at `:606-609`
  ("`last_query_scores` becomes the IDF-corrected score") is already
  accurate. Optionally tighten the comment to note the gates now read it
  as additive-scale.
- `pipeline/tier_logic.py` — no change. With `fusion_mode == "additive"`,
  `skip_absolute_floors` is `False` (`:110`), the absolute TIGHT/FOCUSED/
  ABSTAIN floors run (`:176/219/229`), and the legacy `top/mean` ratio
  with threshold `1.8` is used (`:152-153`) — all calibrated for BM25
  scale, which is what sharded actually produces.
- `know_calibration.py` / `helix.toml [know]` — no change. The BM25 betas
  match the BM25-scale input.
- `scoring/blend.py` — no change. The refiner bonuses are
  absolute-magnitude tuned for BM25 scale, which is preserved.

**One real caveat for Option (b):** the sharded score scale is
`additive × IDF-correction[0.5,3.0] × doc-boost[1.0,1.15]` — not *pure*
additive. The IDF correction (`shard_router.py:147-252`) and the `1.15`
doc-boost shift the distribution somewhat versus a bare blob-additive
genome. The TIGHT/FOCUSED absolute floors (`5.0`/`2.5`) were calibrated on
*blob*-additive. So Option (b) gets the *scale* right (BM25-ish, not
RRF-ish) but the floors may be slightly off because of the IDF/doc-boost
multipliers. This is a *much* smaller miscalibration than the
RRF-vs-BM25 order-of-magnitude gap Option (a)-without-recalibration
leaves, and it is addressable later by the per-classifier floor
calibration (`abstain.mode = "per_classifier"`,
`scripts/calibrate_thresholds.py`) that `helix.toml:471-503` already
scaffolds. It does **not** block Tier-0.

**Calibration risk:** LOW. No betas move. The only residual is the
IDF/doc-boost distribution shift, which the existing per-classifier-floor
machinery can absorb post-Tier-0.

**Reversibility:** HIGH. Option (b) is a **one-line, fully reversible**
change (`_fusion_mode` string). If the matrix re-bench shows it
regressed, revert the single line. No betas, no refiner scale, no
publisher logic touched.

### 3.3 Recommendation — **Option (b)**

1. **It is correct.** The sharded path *does* publish additive-scale
   scores. Option (b) makes the label match the data. Option (a) makes the
   data match the label — also valid, but strictly more work.
2. **It is one line and fully reversible.** Tier-0 already carries a
   re-backfill + re-bench cost (§6, ~$19, ~2h) and an irreversibility
   concern (R4). The score-scale fix should be the *cheap, reversible*
   half. Option (b) is exactly that.
3. **It keeps beta recalibration off the critical path.** A prior task
   already classified beta recalibration as "a separate larger task".
   Option (a) drags it in; Option (b) leaves it where it belongs — a
   follow-up, to be done properly once a genuine-RRF bench JSONL exists
   (the calibration script needs that input, and Tier-0's re-bench will
   produce a clean one if Option B + RRF-fast-follow lands).
4. **It avoids the refiner-scale landmine (R7) entirely.** Option (b)
   keeps `last_query_scores` on the BM25-ish scale the cymatics/harmonic
   bonuses were tuned for. Option (a) would force a simultaneous
   refiner-scale fix.
5. **It composes correctly with Decision 1 Option B.** Decision 1 Option
   B keeps sharded per-shard genomes on additive ranking math; Decision 2
   Option (b) keeps the sharded *adapter* labelled additive. The two
   agree. (If Decision 1 Option A is chosen instead — RRF everywhere —
   then Decision 2 should flip to Option (a), because under RRF-everywhere
   the per-shard genomes genuinely fuse by RRF and the router *should*
   publish RRF-scale. The two decisions are linked: **B+b**, or **A+a**.
   Do not mix.)

**The recommended pairing is B + b.** Smallest blast radius, fully
reversible, isolates every variable for the re-bench, and leaves the
RRF-everywhere migration + beta recalibration as a clean, separately
measured follow-up.

A note on what Option (b) does *not* fix: pipeline-03 Findings 2/3/4 (the
know/miss `emit_floor` coldness, `lexical_dense_agree` pinned False, the
degenerate-ratio abstain) are *not* resolved by Option (b) — they are
genuine bugs but they are **out of Tier-0 scope**. Option (b) makes the
*scale* honest; those findings are about the gate logic on top. They
belong in a follow-up (the deep review's Findings 2/3/4 own them). Tier-0
exit criterion (§6) measures retrieval `gold_delivered`, which Option (b)
+ dense recall move directly; the know/miss-gate findings move the
*answer* rate and are a separate work item.

---

## 4. Sequenced PR plan

Five PRs. PR-1→PR-2→PR-3 are the code; PR-4 is the fixture rebuild; PR-5
is the re-bench + decision gate. Dependencies are strict where stated.

Throughout, assume **Decision 1 = Option B** and **Decision 2 = Option
(b)** (the recommended pairing). Deviations for A+a are noted inline.

### PR-1 — Compute BGE-M3 dense vectors at ingest

**Goal:** `upsert_doc` (and therefore every ingest path — `helix ingest`,
`/ingest`, `context_manager.ingest`, the fixture builder) computes and
persists `embedding_dense_v2` inline. This is review §2.7 / P0-4 / F1's
fix-direction (a).

**Files touched:**
- `helix_context/knowledge_store.py` — `upsert_doc` (~`:1004-1160`):
  add `embedding_dense_v2` to the INSERT column list and VALUES tuple
  (the INSERT at `:1079-1113`). Add an `embedding_dense_v2` parameter to
  `upsert_doc` (mirroring the existing `splade_sparse` parameter pattern
  at `:1131-1134`) so a batched caller can pass a precomputed vector;
  when not supplied, compute it lazily via a codec held on the store.
  Pack to little-endian fp32 BLOB exactly as
  `backfill_bgem3_v2._vec_to_blob` does (`scripts/backfill_bgem3_v2.py:58-63`)
  — reuse that helper or factor it into `backends/bgem3_codec.py` so the
  two paths cannot drift.
- `helix_context/knowledge_store.py` — ensure the `genes` DDL/migration
  declares `embedding_dense_v2` on fresh DBs. `storage/ddl.py:113`
  declares it per the review; confirm `_init_db` / the ALTER path runs so
  a *freshly built* genome has the column without needing the backfill
  script's `_ensure_v2_schema`. (If `_init_db` already adds it — review
  pipeline-01 says `ddl.py:113` declares it — this is a no-op verify.)
- `helix_context/context_manager.py` — `ingest()` (~`:680-794`):
  batch-encode dense vectors for all strands in one codec call (mirror
  the SEMA `encode_batch` at `:698-705`), pass each through to
  `upsert_doc`. The manager already lazy-loads a BGE-M3 codec —
  `self._dense_codec: BGEM3Codec | None` per review §2.7 (`context_manager.py`
  ~`:418`); verify and reuse it. Encode with `task="passage"`, bound to
  2000 chars (the codec contract — `backfill_bgem3_v2.py:134-136`).
- `helix.toml` `[ingestion]` — add `dense_embed_on_ingest = true`
  (new knob; default true). Lets latency-sensitive callers defer to the
  backfill script. Wire into `config.py`.
- `helix_context/config.py` — parse `dense_embed_on_ingest`.

**Not in this PR:** the `helix.toml` `dense_embedding_enabled` flip
(that is PR-3 — retrieval-side). PR-1 is purely the *write* path. A genome
built after PR-1 will *have* dense vectors; retrieval still won't *use*
them until PR-3. This separation keeps PR-1 reviewable in isolation and
means PR-1 alone cannot regress retrieval.

**Test plan:**
- Unit: `upsert_doc` with an explicit `embedding_dense_v2=` arg persists
  the BLOB; round-trips at `dim*4` bytes; `_ensure_dense_matrix` picks it
  up.
- Unit: `upsert_doc` with no dense arg and `dense_embed_on_ingest=true`
  computes a non-NULL vector; with `=false` leaves it NULL.
- Unit: `context_manager.ingest()` of a 3-strand document → all 3 genes
  have non-NULL `embedding_dense_v2` of the right length.
- Integration: ingest a small corpus, assert
  `SELECT COUNT(*) FROM genes WHERE embedding_dense_v2 IS NOT NULL` ==
  total gene count.
- Regression: full `pytest tests/ -m "not live"` — no change to the
  ~1950-test suite (PR-1 only *adds* a column write).
- Idempotency: re-running the backfill script over a PR-1-built genome
  reports `coverage=100%` and `rows to process: 0` (the script's
  `length(blob) != expected_bytes` skip-clause must agree with PR-1's
  encoding).

**Risk:** adds BGE-M3 encode latency to ingest (~tens of ms/chunk CPU,
faster on GPU per `[hardware]` auto-detect). Bench ingest is offline so
this is the correct trade. The `dense_embed_on_ingest` knob is the escape
hatch. See R3.

---

### PR-2 — Backfill dense vectors in the fixture builder

**Goal:** `build_fixture_matrix.py` produces fixtures whose
`embedding_dense_v2` column is populated, in both blob and sharded mode —
so the bench measures the real pipeline, not a dense-dark one. This is
review pipeline-01 P0-4 fix-direction (b) and F1's "backfill the fixtures".

**Depends on:** PR-1 (the builder will get dense vectors for free *if* it
goes through the PR-1 ingest write path; if it bypasses it, PR-2 wires the
backfill explicitly).

**Files touched:**
- `helix_context/genome.py` / `knowledge_store.py` — `Genome` is the
  class the builder uses (`build_fixture_matrix.py:80,569,704`). Once PR-1
  lands, `Genome.upsert_doc` computes dense vectors when
  `dense_embed_on_ingest` is set. The builder constructs `Genome(path=...,
  splade_enabled=True, entity_graph=True)` (`:569`, `:704`) — it does
  **not** pass `dense_embed_on_ingest`. **Decision point:** either (i)
  have the builder pass `dense_embed_on_ingest=True` into the `Genome`
  constructor, or (ii) keep the builder's per-gene path lean and run an
  explicit BGE-M3 backfill pass after each profile/shard is built.
  **Recommend (ii)** — an explicit post-build backfill — because the
  builder's hot path is the batched-SPLADE writer
  (`_drain_with_batched_splade`, `:280-330`) and threading dense encoding
  into that writer is more invasive than a clean post-pass; an explicit
  pass also makes the dense-coverage step *visible* in the build log and
  reusable for the standing reproduction DBs.
- `scripts/build_fixture_matrix.py` — add a `_backfill_dense(db_path)`
  helper that opens the freshly-built `.db` and runs the same encode loop
  as `scripts/backfill_bgem3_v2.py:129-158` (or imports and calls its
  `main()` with the path). Call it:
  - blob mode: at the end of `build_profile` (`:626-660`), after
    `genome.close()`, per `<profile>.db`.
  - sharded mode: in `_build_one_shard` (`:676-813`) after the shard is
    drained, per shard `.db`. The cross-shard `main.genome.db` routing DB
    holds no `genes` rows that need dense vectors (it holds
    `fingerprint_index` / `source_index`), so only the per-shard `.db`
    files get backfilled — which is exactly right, since per-shard dense
    recall reads each shard's own `genes.embedding_dense_v2`.
- Factor the encode-and-pack loop so `backfill_bgem3_v2.py` and
  `build_fixture_matrix.py` share one implementation (avoid the latent
  drift the review flags for FTS5 assembly at pipeline-01 P3).
- `build_fixture_matrix.py` manifest — record per-profile/per-shard dense
  coverage % in `manifest.json` (`update_manifest`, `:1062-1085`) so a
  future reader can confirm the fixture is dense-populated.

**Test plan:**
- Build the **small** profile blob (`--profile small`, fast — 4 roots),
  assert every `genes` row has non-NULL `embedding_dense_v2`; assert
  manifest records `dense_coverage == 1.0`.
- Build **small** sharded (`--profile small --mode sharded`), assert each
  per-shard `.db` is fully dense-populated; assert the routing
  `main.genome.db` has no `embedding_dense_v2` expectation (it has no
  `genes`).
- Time the dense pass on `small` and extrapolate to the matrix (sizing
  input for PR-4 / R5).

**Risk:** lengthens fixture builds. The backfill is ~30–90 min CPU /
~5–15 min GPU for ~19k genes per the script header; the matrix totals are
larger. See R5. Mitigated by GPU (`[hardware]` auto-detect) and by the
builder's existing parallel modes for the *ingest* half (the dense pass
itself is a separate sweep but can also be batched).

---

### PR-3 — Light up dense recall in retrieval + the score-scale relabel

**Goal:** dense recall actually *fires* during `query_docs` in both blob
and sharded mode; the sharded score-scale label is made honest.

**Depends on:** nothing code-wise (it can land before PR-1/PR-2), but it
is **inert until a dense-populated genome exists** — so it is only
*meaningful* after PR-1+PR-2. Sequence it third so the re-bench (PR-5)
runs against all three.

**Files touched — dense participation (Decision 1 = Option B):**
- `helix_context/knowledge_store.py:1922` — change
  `if self._dense_embedding_enabled and self._fusion_mode == "rrf":` to
  `if self._dense_embedding_enabled:`. Inside the branch, keep the
  existing RRF Fuser-tier path (`:1932-1953`) and add an additive-mode
  merge: when `self._fusion_mode != "rrf"`, do
  `gene_scores[gid] = gene_scores.get(gid, 0.0) + cosine *
  self._dense_additive_weight` instead of the `1e-9` epsilon at `:1946`.
- `helix.toml [retrieval]` — `dense_embedding_enabled = false` →
  `dense_embedding_enabled = true` (`:275`). Add
  `dense_additive_weight = 4.0` (new; BM25-comparable, tag-exact is 3.0).
  Keep `fusion_mode = "additive"` (Option B).
- `helix_context/config.py` — flip the `dense_embedding_enabled` default
  to match (`:280` per the review) and parse `dense_additive_weight`.
- `helix_context/knowledge_store.py` — thread `dense_additive_weight`
  through `__init__` / `open_read_source` / the `Genome` constructor
  (mirror the existing `dense_weight` plumbing — `context_manager.py:501`).

  *If Decision 1 = Option A instead:* additionally flip
  `helix.toml:298` `fusion_mode = "rrf"` and `config.py:308` default to
  `"rrf"`; drop `dense_additive_weight` (RRF makes it moot); and the
  `:1922` change can simply be `if self._dense_embedding_enabled:` with
  only the Fuser-tier path inside.

**Files touched — score-scale relabel (Decision 2 = Option (b)):**
- `helix_context/sharding.py:181` — `_fusion_mode: str = "rrf"` →
  `_fusion_mode: str = "additive"`. Rewrite the docstring `:174-181` to
  state the truth: the router publishes IDF-corrected additive-scale
  scores; the sharded path is treated as additive-scale by the gates.
- No change to `shard_router.py`, `tier_logic.py`, `know_calibration.py`,
  `scoring/blend.py` — that is the *point* of Option (b).

  *If Decision 2 = Option (a) instead:* change `shard_router.py:610-611`
  to publish `rrf_all`; keep `sharding.py:181` as `"rrf"`; **and** add a
  refiner-scale fix to `scoring/blend.py` (scale the cymatics/harmonic/TCM
  bonuses to the RRF range, or apply them to a side map); **and** schedule
  the beta recalibration. Option (a) is materially larger — this is why
  the plan recommends (b).

**Test plan:**
- Unit: with `dense_embedding_enabled=true` and a dense-populated
  in-memory genome, `query_docs` in additive mode returns dense-surfaced
  genes in `gene_scores` with a non-epsilon contribution; in RRF mode they
  appear as a Fuser tier. A genome with NULL `embedding_dense_v2` still
  degrades to lexical-only with the one-time WARN (no crash).
- Unit: `ShardedGenomeAdapter._fusion_mode == "additive"`; a sharded
  `build_context` run drives `tier_logic.apply_budget_tiers` with
  `fusion_mode="additive"` → `skip_absolute_floors` is `False` → the
  absolute floors run.
- Integration: against the PR-2-built **small** dense fixture, run a query
  whose gold doc is a semantic-but-not-lexical match; assert the gold doc
  is now in the candidate set (it would have been absent pre-dense).
- Regression: full `pytest tests/ -m "not live"`. Watch the sharded /
  abstain / tier_logic tests specifically — `_fusion_mode` flipping
  additive↔rrf changes which gate branch they exercise. Some sharded
  tests may assert `_fusion_mode == "rrf"`; those assertions must be
  updated to `"additive"` (this is expected and correct, not a
  regression).
- `live`-marked: `pytest tests/ -m live` if a BGE-M3 model is available,
  to exercise the real encode path.

**Risk:** flipping `_fusion_mode` to `"additive"` re-enables the absolute
TIGHT/FOCUSED/ABSTAIN floors on the sharded path. Those floors were
calibrated on *blob*-additive, and sharded scores carry the IDF-correction
+ doc-boost multipliers (Option (b) caveat in §3.2). The matrix re-bench
(PR-5) is the check; the per-classifier-floor calibration is the
follow-up if needed. See R2.

---

### PR-4 — Rebuild the 6-profile bench fixture matrix (dense-populated)

**Goal:** produce the 6 bench genomes — `small`, `medium`, `large`, `xl`
(blob) and `medium-sharded`, `xl-sharded` — at
`genomes/bench/matrix/<profile>.db` and
`genomes/bench/matrix-sharded/<profile>/`, each with
`embedding_dense_v2` fully populated.

**Depends on:** PR-1 and PR-2 merged (the builder must produce dense
vectors). PR-3 should also be merged so the rebuilt fixtures are
re-benched against the final retrieval code in PR-5 — but PR-4 *itself* is
just a build and does not require PR-3.

**This is not "backfill in place" — it is a rebuild.** Per Nuance #1, the
`genomes/` directory is currently empty; there is no existing matrix to
backfill. The 6 fixtures are *generated* by `build_fixture_matrix.py` from
the live `F:\Projects` source tree (and, for `xl`, external Steam roots —
`build_fixture_matrix.py:429-455`).

**Steps:**
1. Snapshot anything currently under `genomes/` (it is empty, but confirm)
   and the existing `benchmarks/genome-bench-2026-05-08*.db` reproduction
   DBs — do **not** overwrite those; the reviews cite them.
2. Build blob profiles:
   `python scripts/build_fixture_matrix.py --profile small,medium,large,xl --parallel`
   → writes `genomes/bench/matrix/{small,medium,large,xl}.db` +
   `manifest.json`.
3. Build sharded profiles:
   `python scripts/build_fixture_matrix.py --profile medium,xl --mode sharded`
   → writes `genomes/bench/matrix-sharded/{medium,xl}/`.
4. With PR-2 merged, each build self-populates `embedding_dense_v2` (the
   post-build dense pass). **Verify** per fixture:
   `SELECT COUNT(*) FROM genes WHERE embedding_dense_v2 IS NOT NULL` ==
   `SELECT COUNT(*) FROM genes` — for every blob `.db` and every per-shard
   `.db`. The `manifest.json` `dense_coverage` field (added in PR-2) is
   the recorded artifact.
5. If PR-2 chose the explicit-pass option and a build predates it, run
   `python scripts/backfill_bgem3_v2.py <each .db>` per fixture and per
   shard `.db` until coverage is 100%.

**Validation gate (must pass before PR-5):**
- All 6 profiles built; all `genes` rows dense-populated; `manifest.json`
  records `dense_coverage == 1.0` for each.
- `helix.toml` at re-bench time has `dense_embedding_enabled = true`
  (PR-3), `dense_embed_on_ingest = true` (PR-1), and the chosen
  `fusion_mode` (Option B → `additive`; Option A → `rrf`).
- A spot `/health` against one mounted fixture reports the dense model
  loaded.

**Cost / time:** dominated by the dense encode pass. Per the
`backfill_bgem3_v2.py` header: ~30–90 min CPU / ~5–15 min GPU per ~19k
genes. `large`/`xl` are bigger than 19k; budget **half a day of
wall-clock on CPU**, an hour or two on GPU. The ingest half (`--parallel`)
is already fast. See R5.

**Risk:** the build walks the *current* `F:\Projects` tree — if that tree
has changed since the 2026-05-15 baseline matrix was built, the new
fixtures are not byte-identical corpora and the gold-doc set may shift.
This is the central baseline-comparison risk — see R6 and §5.

---

### PR-5 — Re-bench the 50-needle full matrix; decision gate

**Goal:** run `benchmarks/bench_claude_matrix.py` over the 6 dense-
populated fixtures and confirm dense recall + the score-scale fix moved
`gold_delivered` without regressing the answer rate. **This is the Tier-0
exit criterion.**

**Depends on:** PR-1, PR-2, PR-3 merged; PR-4 fixtures built and validated.

**Steps:**
1. Confirm `helix.toml` retrieval config is the intended Tier-0 state
   (PR-3 values).
2. Run the full matrix:
   `python benchmarks/bench_claude_matrix.py` (defaults: model `haiku`,
   `max_usd_per_question = 0.3`). Sharded profiles require the server /
   harness started with `HELIX_USE_SHARDS=1` —
   `bench_claude_matrix.py:21,836,879,912` enforce this; follow the
   harness's own instruction.
3. Cost / time: the brief budgets **~$19, ~2h**. The prior run
   (`summary.json`) shows per-profile cost ~$3.0–3.5 × 6 ≈ $19 — consistent.
4. Compare `summary.json` against the 2026-05-15 baseline
   (`benchmarks/results/claude_matrix_20260515T225605Z/summary.json`).

**Baseline (2026-05-15, dense-dark, additive, sharded mislabeled):**

| Profile | gold_delivered_rate | answers correct |
|---|---|---|
| small | 0.30 | 27/50 |
| medium | 0.34 | 27/50 |
| large | 0.34 | 26/50 |
| xl | 0.34 | 27/50 |
| medium-sharded | 0.50 | 24/50 (6 abstain — matrix-high) |
| xl-sharded | 0.36 | 21/50 |

**What confirms SUCCESS:**
- **`gold_delivered_rate` rises on the blob profiles** (`small`/`medium`/
  `large`/`xl`). This is the direct, primary signal that BGE-M3 dense
  recall is now firing — the review predicts the "largest single jump"
  from dense alone (research §3 ranks it #1; pipeline-02 F1 calls it "the
  largest single recall gap"). A blob `gold_delivered` lift of even
  +5–10pp is a clean positive; the review's framing ("every recall point
  is worth ~one answer point") means answers should track up roughly with
  it.
- **`medium-sharded` abstain count drops from 6** toward the blob-profile
  abstain levels (0–5). The score-scale relabel (Option (b)) re-enables
  the abstain absolute floors on the sharded path with the *correct*
  BM25-ish scale; pipeline-03's thesis is that the mislabel was abstaining
  on close-but-good candidates. Fewer sharded abstains, with
  `gold_delivered` holding ≥0.50, is the score-scale-fix success signal.
- **`xl-sharded` does not regress** (it is mislabeled per issue #133 — read
  its numbers with that caveat).
- **No blob profile regresses** `gold_delivered` — dense recall is
  *additive*; under Option B the lexical accumulator is byte-identical, so
  a blob `gold_delivered` *drop* would indicate a real bug (e.g.
  `dense_additive_weight` set so high it crowds out a lexical gold hit)
  and must be investigated, not shipped.

**What indicates REGRESSION (do not ship; investigate):**
- Any blob `gold_delivered_rate` *below* its baseline → dense merge is
  evicting lexical hits; re-tune `dense_additive_weight` down (or, under
  Option A, investigate the RRF weight set).
- `medium-sharded` abstain count *rises* above 6, or its `gold_delivered`
  drops below 0.50 → the `_fusion_mode = "additive"` relabel mis-fired the
  absolute floors against the IDF/doc-boost-shifted sharded distribution;
  the per-classifier-floor calibration follow-up is then required *before*
  ship.
- Answer `score_normalized` falls materially on any profile with
  `gold_delivered` flat or up → a downstream gate (know/miss, tier) is now
  mis-handling the new score distribution; trace to Findings 2/3/4
  (out-of-Tier-0-scope bugs that the score-scale change may have exposed).

**Deliverable:** a short results note alongside this plan
(`benchmarks/results/claude_matrix_<ts>/` is auto-created by the harness)
recording the before/after table and the ship/no-ship call.

---

## 5. Why the baseline comparison needs care

The 2026-05-15 matrix is the comparison anchor, but three things make a
naive before/after unsafe:

1. **The fixtures are rebuilt, not reused.** PR-4 regenerates the 6
   genomes from the *current* `F:\Projects` tree. If that source tree
   drifted since 2026-05-15, the corpora differ and the gold-doc set may
   not be identical. **Mitigation:** if byte-identical comparison is
   required, first rebuild the 6 fixtures from the *same* source state
   with dense-dark code and re-run the bench to establish a "rebuilt-but-
   dense-dark" baseline; then compare dense-on against *that*. This
   doubles the bench cost (~$38, ~4h) — flag it to the human as the
   price of a clean A/B. If an approximate comparison is acceptable, the
   2026-05-15 numbers are a usable reference and the doubling can be
   skipped.
2. **Two variables move at once under Option B+b** — dense recall comes on
   *and* the sharded score-scale label flips. They are separable: dense
   recall affects all 6 profiles' `gold_delivered`; the score-scale
   relabel affects only the 2 sharded profiles' abstain/answer behavior.
   Reading the blob profiles isolates the dense-recall effect; reading
   `medium-sharded`'s abstain count isolates the score-scale effect. The
   plan's success criteria (§4 PR-5) are written to read them
   separately.
3. **`xl-sharded` is mislabeled (issue #133)** — exclude it from the
   headline read; `medium-sharded` is the clean sharded signal (the
   reviews use it as such throughout).

---

## 6. Fixture re-backfill & re-bench — the Tier-0 exit criterion

Consolidated for the human:

**Re-backfill step (PR-4):** the 6 bench genomes do not currently exist on
disk (`genomes/` is empty). They are *built* by `build_fixture_matrix.py`
from `F:\Projects` (+ Steam roots for `xl`), and — with PR-2 merged — each
build self-populates `embedding_dense_v2`. The exit gate for this step:
**every `genes` row in every blob `.db` and every per-shard `.db` has a
non-NULL `embedding_dense_v2` of `dim*4` bytes**, recorded as
`dense_coverage == 1.0` in `manifest.json`. The cross-shard
`main.genome.db` is exempt (no `genes` rows).

**Re-bench step (PR-5):** full 50-needle matrix via
`benchmarks/bench_claude_matrix.py`, ~$19, ~2h, model `haiku`. **Success =
blob `gold_delivered_rate` rises across `small/medium/large/xl` AND
`medium-sharded` abstain count falls from 6 AND no blob profile regresses
`gold_delivered`.** Regression = any blob `gold_delivered` below baseline,
or sharded abstains rising / `gold_delivered` dropping below 0.50.

Until PR-5 passes, Tier-0 is not done — a dense-populated fixture that the
retrieval code does not query, or a score-scale relabel that mis-fires the
floors, would both pass unit tests and still leave the bench measuring the
wrong thing.

---

## 7. Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **Blob-mode regression from the dense merge.** Under Option B, additive-mode dense recall adds `cosine × dense_additive_weight` into `gene_scores`. If the weight is too high it crowds out a lexical gold hit; too low and it is "roughly noise" (the `knowledge_store.py:1913-1914` admission). | MEDIUM | Ship `dense_additive_weight` as a knob (default ~4.0, BM25-comparable); PR-5 measures blob `gold_delivered` directly; re-tune if any blob profile drops. Under Option A this risk moves to the RRF post-multiplier weights instead. |
| R2 | **Sharded floors mis-fire after the `_fusion_mode` relabel.** Option (b) sets `_fusion_mode="additive"`, re-enabling the absolute TIGHT/FOCUSED/ABSTAIN floors (`tier_logic.py:176/219/229`). Those were calibrated on *blob*-additive; sharded scores carry IDF-correction `[0.5,3.0]` + doc-boost `[1.0,1.15]` multipliers, shifting the distribution. | MEDIUM | PR-5 reads `medium-sharded` abstain count as the check. If it regresses, run the per-classifier-floor calibration (`abstain.mode="per_classifier"` + `scripts/calibrate_thresholds.py` — already scaffolded in `helix.toml:471-503`) before ship. |
| R3 | **Ingest latency from inline BGE-M3 encoding** (~tens of ms/chunk CPU). Affects `helix ingest` / `/ingest` for interactive users. | LOW | `dense_embed_on_ingest` knob defers to the backfill script for latency-sensitive callers; GPU path via `[hardware]` auto-detect; bench ingest is offline so unaffected. |
| R4 | **Irreversibility.** Decision 1 Option A (RRF everywhere) and Decision 2 Option (a) (publish RRF + recalibrate betas) are one-way doors once their dependent recalibrations land. | MEDIUM | The recommended pairing **B + b** is fully reversible: Decision 2 Option (b) is a one-line `_fusion_mode` revert; Decision 1 Option B leaves additive math byte-identical. Choosing the recommended path *is* the mitigation. |
| R5 | **Re-backfill cost & time.** The dense encode pass over `large`/`xl` fixtures is hours on CPU (~30–90 min per ~19k genes; the matrix is larger). | MEDIUM | Run on GPU (`[hardware]` auto-detect → ~5–15 min/19k); build profiles in parallel; the dense pass is idempotent/resumable (the backfill script's `length(blob) != expected_bytes` skip-clause) so an interrupted build resumes. Build `small`/`medium` first to unblock early validation. |
| R6 | **Source-tree drift invalidates the baseline.** PR-4 rebuilds fixtures from the *current* `F:\Projects`; if it drifted since 2026-05-15, the gold-doc set shifts and the before/after is not apples-to-apples. | MEDIUM-HIGH | See §5.1: for a clean A/B, build a "rebuilt-but-dense-dark" baseline from the same source state and compare against *that* (doubles bench cost to ~$38/~4h). Flag the cost/cleanliness trade to the human; if approximate comparison is acceptable, skip the doubling. |
| R7 | **Refiner bonus scale.** `scoring/blend.py` adds absolute-magnitude cymatics (`≤0.5`) / harmonic (`0–1.5`) / TCM bonuses to `last_query_scores` *after* it is published. These are tuned for the BM25 scale. | MEDIUM (Option a) / NONE (Option b) | The recommended Decision 2 Option (b) keeps `last_query_scores` on the BM25-ish scale → refiner bonuses stay correctly scaled, R7 does not fire. R7 is *only* a risk if Option (a) is chosen, in which case a simultaneous refiner-scale fix in `blend.py` is mandatory and must be added to PR-3. |
| R8 | **Re-bench cost is a sunk floor.** ~$19/~2h (or ~$38/~4h with the R6 clean-baseline) is spent regardless of outcome; a regression means re-tuning and re-running. | LOW-MEDIUM | Front-load cheap validation: PR-1/PR-2/PR-3 unit + `small`-profile integration tests catch most defects before the full-matrix spend. Only run the full matrix once the `small` integration check is green. |
| R9 | **Out-of-Tier-0 know/miss bugs surface.** pipeline-03 Findings 2/3/4 (`emit_floor` coldness, `lexical_dense_agree` pinned False, degenerate-ratio abstain) are real and the score-scale change may *expose* them in the answer numbers even though Tier-0 does not fix them. | LOW (scope) | Tier-0's exit criterion is `gold_delivered` (retrieval), which dense recall + Option (b) move directly. If `score_normalized` lags `gold_delivered`, attribute it to Findings 2/3/4 and route to the follow-up — do not let it block the Tier-0 ship, but do record it. |
| R10 | **Fresh-genome DDL gap.** PR-1 assumes a freshly built genome's `genes` table has the `embedding_dense_v2` column. The backfill script carries its own `_ensure_v2_schema` ALTER (`backfill_bgem3_v2.py:43-55`) precisely because some genomes lack it. | LOW | PR-1 must verify `_init_db` / the DDL in `storage/ddl.py:113` declares the column on fresh DBs; if not, add the ALTER to the genome init path. Covered by PR-1's "fresh in-memory genome round-trips a dense vector" unit test. |

---

## 8. Summary — sequence at a glance

```
PR-1  ingest dense wiring        upsert_doc + context_manager.ingest write embedding_dense_v2
        │                        (no retrieval change — inert until PR-3)
        ▼
PR-2  fixture-builder backfill   build_fixture_matrix.py dense-populates every built .db
        │                        (depends on PR-1)
        ▼
PR-3  fusion-mode + score-scale  decouple dense from fusion_mode (Decision 1 = B);
        │                        relabel sharded _fusion_mode = "additive" (Decision 2 = b);
        │                        flip dense_embedding_enabled = true
        ▼
PR-4  rebuild 6-profile matrix   genomes/bench/matrix*{,-sharded} — verify dense_coverage=1.0
        │                        (depends on PR-1+PR-2; PR-3 also merged for PR-5)
        ▼
PR-5  re-bench 50-needle matrix  bench_claude_matrix.py — ~$19/~2h — Tier-0 EXIT GATE
                                 SUCCESS: blob gold_delivered ↑, medium-sharded abstain ↓6→lower
```

**Design Decision 1 (fusion-mode story):** recommend **Option B** —
decouple dense participation from `fusion_mode`, keep `additive` default,
flip to RRF later as a separately-measured A/B per the existing
deprecation timeline. (Option A — RRF everywhere now — is a defensible
alternative but un-isolates the bench A/B and pulls the refiner-scale fix
forward.)

**Design Decision 2 (score-scale fix):** recommend **Option (b)** — relabel
`ShardedGenomeAdapter._fusion_mode = "additive"` so the gates interpret the
genuinely-additive sharded scores correctly. One line, fully reversible,
keeps beta recalibration off the critical path (a prior task already
called it "a separate larger task"), avoids the refiner-scale landmine.
(Option (a) — publish RRF-scale + recalibrate betas — is correct long-term
but materially larger and irreversible; pick it only if Decision 1 = A.)

**The two decisions are linked: choose B+b together, or A+a together — do
not mix.**
