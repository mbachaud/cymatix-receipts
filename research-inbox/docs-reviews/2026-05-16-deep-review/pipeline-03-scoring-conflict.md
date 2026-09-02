# Deep Review — Scoring / Ranking / Selection: the conflict → neither-selected failure mode

Track 03 of the 2026-05-16 deep review. **Read-only**; no source modified.

Scope: RRF / additive fusion, `scoring/` (cymatics, TCM, blend, ray-trace,
know-calibration, know-decision), `retrieval/` (tie-break, fusion, fusion_plr,
intent_router, lexical_rescue), `pipeline/tier_logic.py` (abstain gate),
`shard_router.py` / `sharding.py`, `context_manager.py`, `context_packet.py`,
`server/helpers.py`.

Ground truth: 50-needle full-matrix bench
`benchmarks/results/claude_matrix_20260515T225605Z/`, **medium-sharded** as
the clean signal (xl-sharded mislabeled, issue #133).

---

## TL;DR — the headline failure

**The "conflict → neither selected" mode is real and is dominated by ONE root
cause: a fusion-mode score-scale contradiction in sharded mode.** Sharded
retrieval publishes *raw additive BM25-scale* scores into `last_query_scores`,
but the downstream selection gates (`tier_logic.py` abstain gate,
`know_decision` confidence) are told via `_fusion_mode = "rrf"` to treat those
same numbers as *RRF-scale* (~0.3). The two halves of the system disagree about
what the numbers mean. The result is not a clean tie — it is a **scale
mismatch that makes the abstain gate and the know/miss confidence fire
semi-randomly**, and when two real candidates are close it lands on
abstain / `miss` instead of picking one.

The bench fingerprint is unmistakable: **medium-sharded delivers gold at
50% (25/50) — the best of any profile — yet scores only 24 correct with 6
abstains, the highest abstain count in the matrix** (`summary.json`). Sharded
retrieval finds the gold doc *more often* and converts it to a right answer
*less often*. That delta is the conflict-loss.

---

## Bench evidence: gold delivered, answer lost

`medium-sharded.jsonl` — 13 needles where `retrieval.gold_delivered = true`
but `score != 1` (gold doc reached the candidate set, answer still failed):

| idx | score | score_reason | query | delivered_count |
|----:|------:|--------------|-------|----------------:|
| 5  | 0  | abstain                | binary size of Rust BigEd build           | 5  |
| 7  | -1 | no-match-and-confident | dimensions in ScoreRift Python preset     | 12 |
| 13 | -1 | no-match-and-confident | current version of BookKeeper package     | 5  |
| 14 | -1 | no-match-and-confident | tests passing in BookKeeper suite         | 12 |
| 16 | 0  | abstain                | SOC 2 templates in CosmicTasha            | 12 |
| 19 | -1 | no-match-and-confident | auth library CosmicTasha uses             | 5  |
| 20 | -1 | no-match-and-confident | PostgreSQL major version CosmicTasha      | 5  |
| 21 | 0  | empty                  | defense layers in ScoreRift               | 12 |
| 22 | -1 | no-match-and-confident | ScoreRift divergence-alert threshold      | 5  |
| 23 | -1 | no-match-and-confident | scorerift pyproject.toml version          | 5  |
| 25 | -1 | no-match-and-confident | minimum Python version of MaxExpressKit   | 5  |
| 26 | -1 | no-match-and-confident | source apps MaxExpressKit distilled from  | 6  |
| 36 | 0  | abstain                | Rust web framework biged-rs uses          | 5  |

`status: "ok"` on every one — **none of these are a retrieval whiff and none
are helix's `ContextHealth.status == "abstain"`**. The gold doc was in the
delivered set of 5–12 docs and the answer still came back abstain (0), empty
(0), or confidently wrong (-1).

### Bench-harness caveat (read before trusting -1 needles)

`bench_claude_matrix.py` does **not** feed `/context` output to the answering
model. `retrieval_probe()` (lines 574–632) calls `/context` with
`decoder_mode: "none"` purely to measure `gold_delivered`. `run_claude()`
(637–685) runs a *separate* `claude -p` subprocess in the helix-context repo
dir with its own tools. The two are decoupled — the answering agent never sees
the retrieved context. So:

- The `score = -1` needles (idx 7,13,14,…) are the model answering from its
  own tools/training and getting it wrong; they are **not** direct proof of a
  helix selection bug. They prove gold was *retrievable*, nothing downstream.
- The `score = 0 / abstain` needles (idx 5,16,36) and `score = 0 / empty`
  (idx 21) are the load-bearing ones for this track: gold delivered, model
  declined to commit. That is the conflict-ambiguity signature.

The honest read of the bench: it measures **retrieval**, not helix's
selection. The conflict-loss must therefore be traced in code, anchored to the
sharded `gold_delivered 25 → correct 24 + abstain 6` aggregate. That trace
follows.

---

## FINDING 1 — [CRITICAL] Fusion-mode score-scale contradiction in sharded mode

**The single highest-impact bug for this track.** Two code paths disagree
about what `last_query_scores` contains, and the disagreement routes correct
retrievals to abstain / `miss`.

### What sharded mode actually publishes

`ShardRouter.query_genes()` — `shard_router.py:606-615`:

```python
with self._last_query_scores_lock:
    self.last_query_scores = {gid: corrected[gid] for gid in ranked_ids}
```

`corrected` is built at `shard_router.py:532-557`:

```python
adj = raw * m                       # raw = shard.last_query_scores (BM25-scale)
...
corrected[gid] *= boost             # doc-type boost 1.15
```

- `raw` = per-shard `Genome.last_query_scores`. Each shard is a plain
  `KnowledgeStore` constructed with the default `fusion_mode = "additive"`
  (`knowledge_store.py:358`) — there is no per-shard RRF. So `raw` is the
  **legacy additive accumulator** (`knowledge_store.py:2294`), BM25-scale:
  FTS5 negative-bm25 + tag-exact 3.0 + filename-anchor 4.0 + harmonic 0–3 …
  routinely 2–15+ for a strong top-1.
- `m` = IDF correction multiplier, clipped to `[0.5, 3.0]` (`IDF_CLIP_LO/HI`,
  `shard_router.py:64-65`).
- `boost` = 1.15 doc-type bump.

**`last_query_scores` in sharded mode = BM25-scale additive score × [0.5,3.0]
× [1.0,1.15]. It is NOT RRF-scale.** The Fuser's `rrf_all` (`all_scores()`,
`shard_router.py:559`) is used *only* as a tertiary sort tiebreaker
(line 569) — it is never published.

### What the selection gates are told

`ShardedGenomeAdapter._fusion_mode = "rrf"` — `sharding.py:181`. The docstring
at `sharding.py:174-181` explicitly claims:

> "any sharded read is RRF-fused … sharded RRF scores (~0.26-0.40)…"

**This claim is false for `last_query_scores`.** The router fuses *ranks* for
the tiebreaker but publishes *corrected additive scores*. The comment
describes an intent the code does not implement.

### Downstream consumers trust the false label

`context_manager.py:1195` passes
`fusion_mode = getattr(self.genome, "_fusion_mode", "additive")` → `"rrf"` —
into `apply_budget_tiers()`.

Inside `tier_logic.py`:

- `skip_absolute_floors = (fusion_mode == "rrf")` (line 110) → **True**. The
  absolute TIGHT/FOCUSED/ABSTAIN score floors (2.5 / 5.0 / 2.5) are bypassed
  (lines 176, 219, 229) on the assumption scores are ~0.3. But the scores are
  actually BM25-scale, where those floors would have been *correct and
  informative*. The gate that should distinguish "found it" from "noise" is
  switched off.
- The RRF-normalized ratio gate runs instead (lines 143-153):
  `ratio_for_gate = (top - min) / (mean - min)`, threshold 1.5. This is a
  *scale-invariant* ratio so it does not blow up — but it was tuned (the
  table at lines 130-139) against numbers that came from *true* RRF fusion
  (`helix_port 2.02`, `mostly-tied 1.40`). Sharded `last_query_scores` is a
  *different distribution* (BM25 additive × IDF-correction × doc-boost), so
  the calibration table does not transfer. The `1.5` threshold is now a
  guess.

`server/helpers.py:_compute_know_or_miss_block` (251-262) reads the *same*
`last_query_scores`:

```python
sorted_scores = sorted(raw_scores.values(), reverse=True)
top_score = float(sorted_scores[0])
score_gap = float(sorted_scores[0] - sorted_scores[1]) ...
```

and feeds `top_score` / `score_gap` straight into `compute_confidence`. See
Finding 2 for why that destroys the know/miss decision.

### Why this is the conflict-loss

When two strong candidates are genuinely close in sharded mode:

1. The IDF correction and doc-type boost (`shard_router.py:540-557`) are
   explicitly designed to **re-order near-tied candidates** ("only re-orders
   candidates that are already near-tied", line 547). They compress the
   top-1/top-2 gap further — two competing docs end up within a hair.
2. The absolute floors that would have said "top-1 is BM25-strong, this is a
   real hit, send it" are bypassed because `_fusion_mode` lies.
3. The mis-calibrated normalized ratio gate sees `(top-min)/(mean-min)`
   barely above or below `1.5` — a coin flip — and on the wrong side it
   **abstains** (`tier_logic.py:174-193`), dropping *both* candidates and the
   whole candidate set.
4. If the ratio gate passes, `_compute_know_or_miss_block` then runs
   `compute_confidence` on BM25-scale numbers through BM25-but-differently-
   calibrated betas (Finding 2) and frequently returns `MissBlock`.

Either way: gold was retrieved, two candidates were close, **neither was
selected**. This is exactly the sharded `gold 25 → correct 24, abstain 6`
gap.

**Impact:** highest. It silently disables the abstain gate's strongest signal
on every sharded query and feeds wrong-scale numbers to the know/miss
discriminator. Sharded mode is the path with the *best* retrieval and a
*worse* answer rate purely because of this.

**Fix direction (not applied):** make `last_query_scores` and `_fusion_mode`
agree. Either (a) publish `rrf_all` (the genuine RRF fused score) as
`last_query_scores` so `_fusion_mode="rrf"` is true and the RRF-calibrated
gates are correct, or (b) set `_fusion_mode="additive"` so the absolute
BM25-scale floors run on the BM25-scale scores actually published. Today the
code does neither — it publishes additive scores and labels them RRF.

---

## FINDING 2 — [CRITICAL] `compute_confidence` betas are BM25-calibrated; under RRF every retrieval falls below `emit_floor`

`know_calibration.py` ships uncalibrated defaults (`helix.toml:360-363`,
`calibrated_at` unset → never recalibrated):

```
betas = [-2.0, 2.0, 1.5, 0.7, 1.8, 1.5]   s_ref = 1.0   g_ref = 0.5
emit_floor = 0.55
```

`z = b0 + b1·tanh(top_score/s_ref) + b2·tanh(score_gap/g_ref)
     + b3·lex_dense_agree + b4·coord_conf + b5·freshness` (`know_calibration.py:260-271`).

`s_ref = 1.0` means `tanh(top_score)` saturates near `top_score ≈ 2–3`.
That is a **BM25 scale** — a real RRF top-1 score is ~0.26–0.40, where
`tanh(0.4) = 0.38`, nowhere near saturation. The logistic was never
re-tuned for RRF (the module's own `# STAGE-7-EXT` notes and `helix.toml`
comments confirm calibration is a deferred "operator post-merge action").

Numeric demonstration (re-derived from `compute_confidence`, defaults):

| regime | top | gap | lex | coord | fresh | confidence | verdict |
|--------|----:|----:|-----|------:|------:|-----------:|---------|
| RRF, two-close, no side signals | 0.40 | 0.005 | F | 0.0 | — | **0.227** | MISS(sparse) |
| RRF, moderate gap, no signals   | 0.40 | 0.05  | F | 0.0 | — | **0.252** | MISS(sparse) |
| RRF, clearly-separated top      | 0.40 | 0.30  | F | 0.0 | — | **0.393** | MISS(sparse) |
| RRF low end                     | 0.26 | 0.005 | F | 0.0 | — | **0.186** | MISS(sparse) |
| RRF, ALL side signals on        | 0.40 | 0.005 | T | 0.5 | 1.0 | 0.867 | KNOW |
| additive/BM25 strong, no signals| 8.50 | 3.00  | F | 0.0 | — | 0.818 | KNOW |

**Under genuine RRF, confidence sits at 0.19–0.39 — uniformly below
`emit_floor = 0.55` — no matter how clean the retrieval.** Even a perfectly
separated top-1 (`gap = 0.30`, which for RRF is huge) only reaches 0.39. The
*only* way to clear the floor is to land all three side signals
(`lexical_dense_agree` + `coord_conf ≥ 0.5` + `freshness = 1.0`)
simultaneously.

This means: on any sharded query where the published scores *were* RRF-scale
(or any future genuine-RRF deployment), `decide_know_or_miss` falls through
its `confidence < cal.emit_floor` branch (`know_decision.py:441`) and returns
`MissBlock(reason="sparse")` — even with gold at rank 1. Combined with
Finding 1 (sharded mode actually publishes BM25-scale numbers), the betas are
*wrong for both interpretations*: too cold for RRF-scale, mis-tuned for the
IDF-corrected additive scale that is actually fed in.

The "two close candidates" angle: `score_gap = top1 − top2`. Under RRF
adjacent ranks differ by `weight/(k+r) − weight/(k+r+1) ≈ 1/3721 ≈ 0.0003`
per tier. Two genuinely competing docs produce a `score_gap` of effectively
0, so `b2·tanh(gap/0.5) ≈ 0` — the gap feature contributes nothing and
confidence drops further. **Two close candidates actively push the
discriminator toward `miss`.**

**Impact:** critical. The know/miss contract — the headline agent-facing
feature ("every response carries `know{found,confidence}` or `miss{reason}`")
— emits `miss` on correct retrievals whenever scores are RRF-scale or the side
signals are not all lit. The agent is told "I don't know" while holding the
answer.

**Fix direction:** recalibrate `[know]` betas + `s_ref`/`g_ref`/`emit_floor`
against a real RRF-scored bench (`scripts/calibrate_know_confidence.py`
exists for exactly this), OR normalize `top_score`/`score_gap` to a
fusion-mode-independent scale before they enter the logistic.

---

## FINDING 3 — [HIGH] `lexical_dense_agree` is structurally pinned to `False` on the packet path; weak on the `/context` path

`lexical_dense_agree` is feature β3 (weight 0.7) — one of only three signals
that can lift an RRF retrieval over `emit_floor` (Finding 2). It is broken or
near-broken on both routes that compute it.

### Packet route — hard-wired False

`context_packet.py::_attach_know_or_miss`, lines 668-676:

```python
tier_contrib = {}                                   # <-- hard-coded empty
...
lex_dense_agree = _agree_from_tier_contributions(tier_contrib, k=3)
```

`_agree_from_tier_contributions({})` returns `False` immediately
(`know_decision.py:274`). The comment admits it: *"until that's plumbed, we
leave this False."* So **`/context/packet` can never set `lexical_dense_agree
= True`** — β3 is permanently 0 for the packet know/miss block. Per Finding 2's
table, with β3 forced off, the all-signals-on row (0.867 KNOW) is unreachable;
the best a packet retrieval can do is the `lex=False` rows (≤ 0.39) → always
`MissBlock(reason="sparse")` under RRF-scale.

### `/context` route — empty in sharded mode

`server/helpers.py:265-266`:

```python
tier_contrib = getattr(helix.genome, "last_tier_contributions", {}) or {}
lex_dense_agree = _agree_from_tier_contributions(tier_contrib, k=3)
```

In sharded mode `last_tier_contributions` is populated by the router
(`shard_router.py:612-614`) from `merged_tier`, which copies *one shard's*
per-tier breakdown (`shard_router.py:507-510`). `_agree_from_tier_contributions`
(`know_decision.py:258-297`) buckets tiers into `_LEXICAL_TIERS`
{tag_exact, tag_prefix, fts5, pki} vs `_DENSE_TIERS` {splade, sema_boost,
sema_cold} and checks top-3 intersection. But `ShardedGenomeAdapter`
hard-disables dense + entity-graph at the adapter level
(`sharding.py:196-197`: `_dense_embedding_enabled = False`). If the per-shard
`Genome`s do not run SPLADE/SEMA (dense tiers), `_DENSE_TIERS` contributions
are empty → the intersection is empty → `lexical_dense_agree = False`.

**Net effect:** β3 is `False` on essentially every sharded query and on every
packet query. The know/miss confidence is permanently denied one of its three
floor-clearing signals. This compounds Finding 2 directly — it removes the
escape hatch.

**Impact:** high. Quietly zeroes a calibrated feature, biasing the
discriminator toward `miss` on exactly the conflict cases.

---

## FINDING 4 — [HIGH] The RRF normalized-ratio abstain gate collapses to `0.0 → abstain` when the candidate set is internally tied

`tier_logic.py:143-149`:

```python
if fusion_mode == "rrf":
    min_score = min(scores.values())
    denom = mean_score - min_score
    if denom > 1e-9:
        ratio_for_gate = (top_score - min_score) / denom
    else:
        ratio_for_gate = 0.0  # degenerate: all candidates tied → abstain
```

The degenerate `denom ≤ 1e-9` branch sets `ratio_for_gate = 0.0`, which is
below *every* threshold, so the ABSTAIN gate at lines 174-178 fires and
**drops the entire candidate set** (`tier_logic.py:184-193`).

The comment frames this as "all candidates tied → abstain", which is
defensible *if* the candidates are genuinely uniform noise. But `denom` is
`mean − min`, and this collapses to ~0 in a case that is **not** noise:

- A small candidate set (`len(candidates)` just above the `<= 3` early-return
  guard at line 74, e.g. 4–6 docs — exactly what `delivered_count = 5` needles
  5/19/20/23/25/36 show) where **two strong docs conflict and the rest are a
  flat low shelf**. `min ≈ mean` when most of the set sits at the floor; the
  one or two high scores barely move the mean. `denom → small`, `ratio → 0`,
  **abstain** — even though top-1 and top-2 are both strong and one of them is
  gold.
- More acutely: if the IDF correction (`shard_router.py:532`) maps several
  shards' rank-1 docs to *the same* corrected score (the comment at
  `shard_router.py:562-563` explicitly anticipates "6 shards' rank-1 hitting
  the cap"), the top of the distribution is a tie *and* the tail is a shelf →
  `mean ≈ min` → `denom ≈ 0` → abstain.

So a query that retrieves **two equally good answers** can hit the degenerate
branch and lose **both**. That is the literal "conflict → neither selected"
mechanism, in the gate the user named.

This lines up with medium-sharded's 6 abstains being the matrix high
(`summary.json`) and with `score_reason="abstain"` needles 5, 16, 36.

**Impact:** high. A guard meant for "uniform noise" also catches
"two-strong-plus-a-shelf", which is the high-value conflict case.

**Fix direction:** the degenerate branch should distinguish "top-1 strongly
exceeds the shelf" (keep, route to BROAD) from "everything is genuinely flat"
(abstain). Checking `top_score` against an absolute or per-class floor before
collapsing to `ratio = 0.0` would separate the two — but that floor is exactly
what `skip_absolute_floors` disabled (Finding 1).

---

## FINDING 5 — [MEDIUM] Cymatics / harmonic refiners can additively re-order a true tie into a wrong winner — and never abstain

`scoring/blend.py::apply_candidate_refiners` mutates `genome.last_query_scores`
*in place* and re-sorts after each refiner:

- Cymatics (lines 50-72): `bonus = flux_score_dispatch(...) * 0.5`, added to
  the score, then `candidates.sort(...)`.
- Harmonic bin (lines 91-122): `bonus = overtones[gid]` (0–1.5 from
  `ray_trace.harmonic_bin_boost`), added, re-sort.
- TCM (lines 124-137): `bonuses` added, re-sort.

Each refiner is a **purely additive nudge with no tie-aware logic**. When two
candidates are genuinely tied on retrieval score, whichever one happens to
have a marginally higher cymatics flux or harmonic-bin overtone wins
outright — and the loser is pushed down, potentially out of the
classifier/tier cap (`context_manager.py:1227-1253`). There is no
"these two are too close to separate, surface both / widen" path; the refiner
*always* produces a strict order.

Two specific destructive-interference / cancellation risks:

1. **Cymatics frequency hashing collisions** (`cymatics.py:85-94`):
   `term_to_frequency` MD5-hashes each term into one of `N_BINS = 256` bins.
   With several query terms, bin collisions are likely (birthday bound). Two
   *semantically different* docs whose tag sets hash into overlapping bins get
   near-identical `flux_score` — so the cymatics refiner cannot separate them,
   and worse, a doc that is *spectrally close by hash accident* gets the same
   +0.5·flux bonus as the genuinely relevant one. The "constructive vs
   destructive interference" framing (`cymatics.py:274-299`) is real cosine
   math, but the inputs are hash buckets, so "interference" between unrelated
   terms is an artifact, not signal.

2. **`harmonic_bin_boost` seeds only `candidates[:3]`** (`blend.py:94`:
   `seed_ids = [g.gene_id for g in candidates[:3]]`). If two conflicting
   candidates sit at ranks 4 and 5 (very possible after the cymatics re-sort
   on a near-tie), **neither seeds the ray-trace**, so neither receives a
   harmonic boost, while a rank-1–3 doc does. The boost systematically favors
   whatever was already top-3 and cannot rescue a co-equal candidate that
   slipped to rank 4. And `cast_evidence_rays` *multiplies* energy by harmonic
   edge weights (`ray_trace.py:309`) — weights `< 1.0` attenuate energy
   geometrically per bounce, so a candidate reachable only through a weak edge
   gets ~0 boost. This is genuine "destructive" attenuation between competing
   candidates.

These do not by themselves *drop both* candidates (that is Findings 1/4), but
they (a) make the top-1/top-2 ordering on a tie effectively arbitrary
(decided by hash luck + which docs were top-3), and (b) widen or narrow the
`score_gap` that Finding 2's `compute_confidence` then reads — so a refiner
artifact can flip the know/miss decision.

**Impact:** medium. Amplifies and randomizes the conflict cases rather than
originating them; also a correctness risk independent of abstention.

---

## FINDING 6 — [MEDIUM] Additive-mode final ranking has a non-deterministic tie-break; the deterministic walking tie-break is opt-in and off

`knowledge_store.py:2294` — additive mode final sort:

```python
ranked_ids = sorted(gene_scores, key=gene_scores.get, reverse=True)[:limit]
```

No secondary key. Python's `sorted` is stable, so ties resolve to **dict
insertion order** — which is the order tiers happened to first insert each
gene_id, i.e. effectively arbitrary and dependent on tier execution order.
Contrast the RRF path (`knowledge_store.py:2275-2278`) which *does*
tie-break by `gene_id` ascending, and the Fuser itself (`fusion.py:117-119,
148-151`) which is explicitly deterministic.

So in **additive mode**, when two candidates have bitwise-equal accumulated
scores and the `limit` cut falls between them, *which one survives is
non-deterministic across tier-execution orderings*. If the gold doc is the
one on the wrong side of the cut, it is dropped — a silent conflict-loss.

The fix for this already exists — `retrieval/tie_break.py::walking_reorder`,
a deterministic associative-graph ladder (neighborhood size → strong edge
freshness → NLI entailment → freshness → lexical gene_id). But it is
**opt-in via `HELIX_WALKING_TIEBREAK=1`** (`tie_break.py:40-42`,
`knowledge_store.py:2304-2309`) and **off by default**. The bench run did not
set it (no evidence in `run.log` / harness). So the deterministic tie-break
that would fix additive-mode ties is dark-shipped.

Note one subtlety even when it *is* enabled: `_rule_nli_entailment`
(`tie_break.py:177-190`) deliberately **abstains on NLI contradiction**
("contradictions should probably be surfaced explicitly rather than resolved
silently") — it does not pick, it falls through to the freshness/lexical
fallback. That is the *correct* instinct, but nothing downstream actually
"surfaces both": the fallback still emits one strict order. Two contradictory
docs are silently ordered by recency, not flagged. The contradiction signal is
detected and then discarded.

**Impact:** medium. Real non-determinism on additive-mode ties; the fix
exists but is disabled. Lower than Findings 1/2/4 because the matrix's
sharded profiles run RRF-path ranking (which *is* deterministic) — additive
blob profiles (small/medium/large/xl) are where this bites.

---

## FINDING 7 — [LOW] Lagrange pull-back can evict a co-equal winner; freshness gate can demote both

Two smaller "drop a good candidate" mechanisms:

1. **Lagrange pull-back** — `tier_logic.py:264-299`. After tiering, a shadow-
   pool doc with high standalone score but `< 20%` co-activation overlap with
   the winners *replaces the weakest winner* outright
   (`candidates[-1] = g`, line 294). If the weakest winner is a genuine
   co-equal candidate (a near-tie with the rest), it is **silently evicted**
   in favor of a graph-isolated doc. On a conflict set where ranks N-1 and N
   are both plausible, this can drop the gold one. Bounded (only fires in
   non-`broad` tiers, top-3 shadow only) so impact is low, but it is a real
   "candidate retrieved then dropped" path.

2. **Freshness gate / Stage 7** — `know_decision.py:418-427` returns
   `MissBlock(reason="stale")` when `freshness_status in ("stale","missing")`.
   `_compute_health` (`context_manager.py:2644-2647`) sets `status="stale"`
   when `freshness_top1 < 0.4 OR freshness_weighted < 0.5`. If two conflicting
   candidates are *both* slightly stale, the whole window is demoted to
   `stale` and `decide_know_or_miss` returns `miss` — both lost to staleness
   even though one holds the answer. Also `β5` freshness in
   `compute_confidence` (Finding 2): a stale top-K shaves ~0.3 off confidence,
   pushing borderline cases under `emit_floor`. Compounds Finding 2.

**Impact:** low individually; both are conflict-adjacent and worth noting as
secondary drop paths.

---

## Cross-cutting observations

- **`fusion_plr` is not a conflict source.** `StackedPLRFuser`
  (`fusion_plr.py`) is explicitly a *query-level* head — "every candidate in a
  given query has the same feature vector, so the classifier can't order
  them" (docstring §Scope). It cannot create or break a tie. Confirmed not
  implicated.
- **`intent_router` / `lexical_rescue` are not conflict sources.**
  `intent_router.py` is query-decomposition templates. `lexical_rescue.py`
  `merge_source_ids` dedups but never drops a candidate to resolve a tie.
- **The abstain gate was *partially* fixed for RRF and the fix is
  incomplete.** PR #116 bypassed the absolute floor; the #115-follow-up added
  the normalized ratio. But both fixes assume `last_query_scores` is genuine
  RRF-scale — and Finding 1 shows sharded mode does not deliver that. The
  abstain gate was hardened against a scale it never actually receives.
- **The know/miss path got no equivalent RRF treatment at all.**
  `tier_logic.py` has `skip_absolute_floors` + normalized ratio; `know_-
  calibration.py` has *nothing* — same BM25 `s_ref=1.0` betas regardless of
  fusion mode. The two gates that decide "conflict → abstain vs pick" are
  calibrated against two different score scales, neither matching the data.

---

## Priority-ranked summary

| # | Severity | Finding | Conflict→neither mechanism |
|---|----------|---------|----------------------------|
| 1 | CRITICAL | Sharded `last_query_scores` is BM25-scale but `_fusion_mode="rrf"` lies to the gates | Disables abstain absolute floors + feeds wrong-scale numbers to know/miss; near-tied candidates land on abstain/`miss` |
| 2 | CRITICAL | `compute_confidence` betas BM25-calibrated; RRF-scale scores → confidence 0.19–0.39, always `< emit_floor` | Correct retrieval → `MissBlock(sparse)`; tiny `score_gap` of two close docs pushes confidence *down* |
| 3 | HIGH | `lexical_dense_agree` hard-wired `False` on packet path, empty on sharded `/context` | Removes the one floor-clearing side signal; biases discriminator to `miss` on conflict cases |
| 4 | HIGH | RRF normalized-ratio gate's degenerate `denom≈0 → ratio=0 → abstain` | "Two strong + flat shelf" candidate set drops *both* candidates |
| 5 | MEDIUM | Cymatics hash collisions + harmonic boost seeding only top-3 | Randomizes top-1/top-2 on a tie; can't rescue a co-equal at rank 4; refiner artifact flips know/miss |
| 6 | MEDIUM | Additive-mode final sort `sorted(gene_scores, key=.get)` has no tiebreak; deterministic `walking_reorder` is opt-in/off | Non-deterministic which tied candidate survives the `limit` cut; NLI-contradiction signal detected then discarded |
| 7 | LOW | Lagrange pull-back evicts weakest winner; freshness gate demotes both stale candidates | Secondary "retrieved then dropped" paths on conflict sets |

**The conflict → neither-selected failure mode the user is worried about is
real.** It is overwhelmingly Findings 1+2+4 acting together on the sharded
path: the system retrieves two good candidates, the gates that should pick one
are running on a misunderstood score scale, and when the two candidates are
close the decision lands on `abstain` / `miss` and **drops both**. The bench
proves the symptom — medium-sharded retrieves gold best (50%) and answers
worst-but-one (24 correct, 6 abstain) — and the code trace above proves the
cause. None of Findings 1–4 is a cosmetic tie-break nicety; they are a
score-scale contract that two halves of the pipeline disagree on.
