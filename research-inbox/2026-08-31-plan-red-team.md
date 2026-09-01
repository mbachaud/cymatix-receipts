# Red team: Sol's deterministic-representation plan vs. the receipt corpus (2026-08-31)

Reviewing `research-inbox/2026-08-31-sol-deterministic-representation-plan.md`
against `docs/benchmarks/BASELINES.md`, the 2026-08-30 EnronQA paraphrase-crater
doc, the three 2026-08-31 ERB receipts (`semantic_vocab_gap`,
`semantic_above_gold`, `floor_width_curve`), the wave-2 synthesis
(`docs/research/2026-08-28-wave2-semantic-ranking-graph-research.md`), the W2.1
COVER-walk kill (`docs/superpowers/plans/2026-08-28-w2.1-cover-walk.md`), the
semantic-portfolio-lane doc (LoCoMo/MULoc, in worktree `vigilant-wu-5416d6`),
and one **uncommitted** receipt not yet written up anywhere
(`benchmarks/dogfood/muloc/receipts/ladder_muloc_budget14000_2026-08-31.json`,
also in `vigilant-wu-5416d6`) that directly bears on the plan and that the plan
could not have seen.

Verdict up front: the plan's central architecture claim (flattened FTS field)
checks out against `storage/ddl.py`'s `FTS_SOURCE_VIEW` — `source_id + tags +
content` really is one `content` column today. The plan is broadly
well-grounded and explicitly cites the two hardest kills (COVER-walk, entity
overlap unbanded) correctly. But it has one live dead-bet repeat, one
cross-corpus evidence-scoping error, one falsified assumption it never had a
chance to see, one gate defined on the wrong basis, and a holdout-discipline
gap that opens it to needle-set overfitting well before the headline number is
reached.

---

## 1. Contradictions

### 1a. Gated PRF (ladder item 6) contradicts the wave-2 Lane-3 kill, and the "gating" doesn't distinguish itself from what was already tested

Wave-2 synthesis §5, lane 3: **"PRF/RM3 through the synonyms seam — KILLED.
Feedback set is gold-free by definition on every target needle (gold rank
13+/49k+) → guaranteed drift; RM3 is head-negative on head metrics; **no
winning cell even know-gated**."** That "even know-gated" is exactly the shape
of the Sol plan's mitigation: item 6 reads "Gated query-time expansion only
(RM3/Bo1 PRF, contained experiment, only on confident first pass; cannot fix
gold-free blackouts; drift risk)." The plan's own text concedes the
gold-free-blackout failure mode (matching the wave-2 deciding fact) but
proposes running PRF anyway on "confident first pass" queries. Two problems:

- "Confident" is a score-margin heuristic, not a correctness signal — a
  first-pass ranking can be confidently wrong (the semantic near-band cohort
  IS exactly this: high-scoring interlopers, gold buried at rank 13–45). PRF
  seeded from a confidently-wrong top-k just re-injects the interloper's
  vocabulary, which is the drift mechanism wave-2 already measured.
- The `semantic_vocab_gap_947k_2026-08-31.json` receipt reinforces this: even
  for misses ranked ≤12 in the map (n=1) or 13–30 (n=14) — i.e. exactly the
  "confident, near-miss" cases PRF would target — `frac_kw_hitting_gold` is
  0.295 and 0.322 respectively, barely different from the fully-absent
  cohort's 0.244. Query-side confidence doesn't correlate with how
  gold-bearing the top-k vocabulary actually is on this corpus.

The plan is right that this is architecturally different from the query-side
`[synonyms]` map (doc-side PRF vocabulary vs. hand-authored query expansion),
so it isn't a literal duplicate. But it IS the same failure mechanism already
priced and killed under a "gated" framing, and the plan doesn't cite the
wave-2 kill or explain what's different about its gate. This should either be
cut, or re-scoped with its own falsifier (e.g., pre-register a kill rule like
W2.1's: "if PRF-selected feedback terms hit gold on <30% of confident-but-miss
needles, kill") before it's treated as ladder-eligible.

### 1b. "Coverage favored gold 16/21" is real but ERB-only, and the same mechanism was already inverted on EnronQA's actual paraphrase crater

The plan's Class picture cites `semantic_above_gold_947k_2026-08-31.json`
correctly in isolation: `summary.gold_beats_interloper_majority_on_coverage:
16` out of `n_targets: 21` (the rank-13–45 reachable subset). That's accurate
for ERB.

But `docs/benchmarks/2026-08-30-enronqa-paraphrase-crater.md` §3 ran the
*identical* discrimination question on a real (not synthetic) paraphrase
crater and got the opposite answer: **"gold beats the interloper majority on
5/16 needles only (11/16 losses)... There is no coverage margin to
discriminate on — the same shape as the W2.1 COVER-walk kill (mass → hubs, not
gold). Recorded as a fatal fact for coverage/coordination reranking on this
crater."** Inspecting the ERB near-band candidates in `semantic_above_gold`
also suggests why the two corpora disagree: ERB's above-gold interlopers on
needles like `erb_180`/`erb_182`/`erb_196` are dominated by near-duplicate
templated tickets (`sup-702468` appears twice, `sup-829101` twice, a long run
of `SUP-*`/`ENG-*` incident writeups sharing boilerplate tag vocabulary) —
gold outcovers them somewhat mechanically because it's the one doc that
actually is about the query, while the near-dupes match generically. EnronQA's
crater is a different regime entirely: real named-entity anchor loss where the
residual (post-paraphrase) query terms are generic and interlopers legitimately
match as well as gold.

The plan doesn't operationalize the 16/21 finding into an explicit ladder item
(it isn't W2.2/lane-5-narrow by name anywhere in the "Recommended path" or
"Experiment ladder"), so this may be intended only as motivating color for
"fielded cards will naturally do per-field coverage." If so, say that
explicitly and drop the implied portability claim; if an explicit
coverage/coordination reranking feature is still on the table, it needs the
wave-2 F2 gate AND a MULoc/EnronQA replication before funding — not just the
ERB 16/21 cited as if it generalizes.

### 1c. The muloc hard-floor finding falsifies a budget theory the plan doesn't test, and directly touches the plan's own stated deployment regime

Not yet in any doc — only in the raw receipt
`benchmarks/dogfood/muloc/receipts/ladder_muloc_budget14000_2026-08-31.json`
(worktree `vigilant-wu-5416d6`, config `budget_14000.toml`, "ONLY
expression_tokens differs (7000 -> 14000)"). Result: `delivered_gold_rate =
0.4441176470588235` — **byte-identical to the shipped 7000-token baseline**
(`0.444` in the semantic-portfolio-lane doc). Doubling the token budget bought
zero delivered gold on MULocBench.

This falsifies the semantic-portfolio-lane doc's working theory ("Code chunks
are token-heavy enough that `expression_tokens = 7000` genuinely binds at ~6
seats"). The real mechanism is almost certainly `[budget]
tier_hard_floor_frac = 0.15` (`cymatix_context/config.py:242`: "score-gate hard
floor — drop candidates scoring below this fraction of the top score" into a
half-weighted shadow pool) — a score-ratio gate that caps delivered count
independent of token headroom whenever gold's absolute score sits far below
the top candidate's, which is exactly the shape of a code repo where one
canonical implementation file scores much higher than a legitimately-relevant
but peripherally-worded file.

The Sol plan never lists `tier_hard_floor_frac` as a knob to instrument or
test, despite MULocBench being explicitly named in the plan's own charter
lineage as "Cymatix's actual deployment regime (context engine for coding
agents)" (semantic-portfolio-lane doc, Lane 2). Any deterministic-card or
structure work that improves candidate ranking on code corpora will not move
delivered gold if this gate is what's actually capping it — this is a missing
cell that should be added ahead of, or alongside, item 1 (fielded cards) if
code-corpus delivery is in scope for the 70/80% program at all.

### 1d. r@2/r@5 concentration goal doesn't conflict with the muloc hard floor directly — but the plan should notice the hard floor IS a concentration mechanism, with a cost

The prompt-brief hint asks whether the plan's r@2/r@5 concentration goal
conflicts with the muloc hard-floor finding. It's not a direct contradiction
(concentration is measured on ERB where the hard-floor interaction hasn't been
isolated), but there's a real tension worth naming: `tier_hard_floor_frac` is
*itself* a head-concentration lever — it prunes low-relative-score candidates
before delivery, which is precisely the kind of aggressive-concentration
behavior that also strands legitimate lower-scoring gold on multi-gold-file
tasks (MULoc) or multi-hop reasoning (LoCoMo). The plan's sequencing rule
("Tune concentration only after candidate-union recall improves," ladder step
5) implicitly assumes concentration and recall are cleanly separable phases.
The muloc null shows they aren't on code corpora: improving candidate-union
recall there won't convert to delivered gold at all while this gate silently
discards the improved candidates pre-delivery. Recommend adding a
`tier_hard_floor_frac` sensitivity sweep as its own pre-flight cell (cheap,
read-only-adjacent, same shape as `tier_tight_ratio`/`tier_focused_ratio`
sweeps already in the codebase) before assuming ladder step 5's ordering
holds across corpora.

---

## 2. Dead-bet repeats

| candidate repeat | verdict |
|---|---|
| Gated PRF (item 6) | **Live repeat** of wave-2 lane 3 KILL, see 1a. Highest-priority item to fix or cut. |
| Generic/statistical COVER graph | **Correctly avoided.** Plan explicitly cites "W2.1: 1 genuine rescue / 1,410 slots" (matches the receipt exactly: 470 queries × 3 append slots = 1,410; 1 genuine novel rescue, `erb_276`) and proposes a different substrate (explicit typed structural edges — reply-to, parent/child, issue/file — vs. statistically-derived entity-co-occurrence edges). This is a real distinction, not a repeat. |
| Entity-graph flat +0.5 unbanded additive | **Correctly avoided.** Plan's item 1 explicitly says "fuse with existing RRF/eps-band," which is the banding discipline the wave-2 doc says this lane violated ("a verbatim eps_band violation... do not flip it as-is"). |
| Query-side `[synonyms]` hand map (measured −3.3pp at n=30) | **Adjacent but not identical.** Item 4's "conservative normalization... stemmed view" risks being read as the same mechanism. It differs in kind (rule-based canonicalization as an independent scored leg vs. flat query-side term injection into the single shared field) but the plan doesn't say so explicitly, and should — see §3 on the existing `_singular_plural_variants` machinery below, which is close enough in spirit that conflation is a real risk for anyone skimming the plan later. |
| Dense/SPLADE defaults | **Correctly deferred**, not reopened. Plan's whole thesis is "model-backed only after deterministic plateau," consistent with the 2026-08-15/16 encoder-removal receipts. |

### 2a. A concrete, code-verified gap in item 4: the "stemmed view" isn't new territory, and the existing version is crude

`cymatix_context/accel.py:140` (`_singular_plural_variants`) already runs at
query time, inside `expand_query_terms` → `extract_query_signals` (the
Stage-1 keyword extractor used for tag matching, and reused by the
`semantic_vocab_gap` diagnostic itself). It is a **blind suffix
toggle** — append "s" unless the word already ends in a handled suffix — with
no part-of-speech awareness. That's exactly why the `kw_missing_from_gold`
lists in `semantic_vocab_gap_947k_2026-08-31.json` are full of non-words:
`"durings"`, `"boths"`, `"aboves"`, `"confirmings"`, `"gettings"`,
`"alway"/"always"/"always-on"/"always-ons"`. Two consequences for the plan:

1. The 24–32% "keyword-hits-gold" fractions cited as motivating evidence for
   fielded/phrase work are somewhat noisy — a meaningful chunk of the
   denominator is junk tokens from this suffix-toggle, not real vocabulary
   variance. Treat the percentages as directionally right, not precise.
2. Item 4's "stemmed view" needs to specify a real stemmer (Porter/Snowball —
   cheap, stdlib-adjacent, and spaCy is already in the ingest path for NER) or
   it will just re-ship the same crude mechanism as a new leg and likely
   reproduce a result in the same negative-to-null range as the existing
   `[synonyms]` map, rather than the improvement the plan is betting on.

---

## 3. Missing cells

1. **`tier_hard_floor_frac` sensitivity, especially on code corpora.** See 1c.
   Not listed anywhere in the plan's ladder despite being the most likely
   actual driver of MULoc's delivered-count cap, and despite MULoc being the
   plan's own cited deployment regime.
2. **The abstain norm-ratio edge and the `[know]` calibration coverage gap.**
   `docs/benchmarks/2026-08-30-enronqa-paraphrase-crater.md` §4: a real (if
   rare, 1/500) false-negative abstain from the RRF ratio gate reading a flat
   candidate curve as "tied → no signal," with the `abstain_reason` string
   (`score_below_floor`) actively mislabeled under RRF (the absolute floor is
   bypassed). Separately, `BASELINES.md`'s 2026-08-19 know-abstain-sanity row
   flags `[know]` emit as "coverage-dead on the shipped path... ceiling ≈0.31
   < emit_floor 0.45." The Sol plan adds several new scored legs (fielded
   cards, phrase/proximity, normalization, typed adjacency) that will reshape
   the RRF candidate-score curve on every query. None of that work is graded
   against whether it shifts the abstain false-negative/false-positive rate.
   Given the pipeline's whole external contract is the know/miss agent
   contract (per CLAUDE.md), a plan that changes ranking signals without a
   companion abstain-rate check is incomplete.
3. **Per-leg C_K instrumentation feasibility is asserted, not scoped.**
   Ladder step 1 — "Instrument per-leg candidate recall at K=50/100/500 +
   conditional head concentration + delivery separately" — is treated as the
   unlocking first move. `benchmarks/dogfood/erb/ablation_ladder.py` today
   only computes `recall_at_k`/`final_recall_at_k` at the single delivered
   k=12 cutoff, with no per-leg (per rerank-class) attribution and no
   sweep over K=50/100/500. Every prior per-mechanism diagnostic in this
   corpus (`semantic_above_gold`, `semantic_vocab_gap`,
   `w2_cover_reachability_preflight`) required a bespoke one-off script, not
   a flag on the existing ladder tool. Step 1 is real engineering work, not
   a warm-up; it should be prototyped/timeboxed before the rest of the ladder
   is scheduled against it as a dependency.
4. **Dev/holdout split arrives too late relative to how small the driving
   cohorts are.** See §4.
5. **Cross-corpus confirmation is scheduled only at the very end (ladder
   step 6, "confirm on LoCoMo/MULoc/FinanceBench/EnronQA")**, after weights
   are frozen. But 1b and 1c above show the ERB-vs-EnronQA and
   ERB-vs-MULoc mechanisms already disagree on cheap, already-available beds
   (LoCoMo/MULoc/EnronQA beds exist now per the semantic-portfolio-lane doc).
   A cheap early smoke replay of the fielded-card prototype against those
   beds (not a full paired ladder run, just a sanity direction-check) before
   committing to item-1-through-4 designs would catch ERB-specific
   overfitting (e.g. tuning field weights against ERB's templated-ticket
   near-duplicate structure) much earlier than step 6.
6. **FinanceBench is queued, not run** (semantic-portfolio-lane doc: "after
   the two lanes above, user ordering"). The plan's step 6 treats it as an
   available confirmation corpus; no timeline or capacity is stated for
   getting it built before that step is needed.
7. **No latency budget stated per new leg**, despite latency being one of the
   plan's own "real graduation" criteria. Per-query wall time on the 947k bed
   is already ~10–24 seconds in the `semantic_above_gold` replay receipts
   (e.g. `erb_199`: 24,476 ms; `erb_180`: 18,824 ms) — before any of items
   1–6 add legs. Item 6 (gated PRF) in particular is architecturally a
   second retrieval pass for gated queries; the plan should state a
   per-leg latency ceiling up front rather than measuring it only at the
   end.
8. **Hub-guard discipline isn't explicitly carried over to the new typed-
   adjacency lane.** The COVER-walk kill's root cause was mass concentrating
   on shared-entity hub neighbors; W2.1 mitigated this in its own substrate
   with an explicit `degree_cap`/hub guard. Item 5's typed edges (same-
   heading, parent/child, reply-to) can build their own hubs (a long thread,
   a heavily-cross-referenced index/README) — the plan doesn't say the same
   guard applies there, and it should, explicitly, rather than being
   assumed transferred.

---

## 4. Statistical hygiene

- **Arithmetic checks out.** 70% r@12 = 329/470, current 320/470 → +9 (≈1.9pp).
  80% = 376/470 → +56. Semantic 70%/80% (+44/+56 on n=125) and r@5 80%
  (+97 hits) all reproduce from the cited receipts exactly.
- **The system is genuinely deterministic, and the team already exploits
  this well in places.** Repeated exact-reproduce witnesses across
  `BASELINES.md` (wave-1 confirm: Δ=0.000000; sema-ingest-ab: graded twice
  order-reversed, identical; neutralize-ab: 141/141 windows byte-identical;
  floor-width-curve: 0/470 rank diffs across all three floor arms) mean
  there is no run-to-run measurement noise to average away. The
  "gained N / lost 0" strictly-nested pattern used for the floor and wave-1
  flips is a legitimately strong evidentiary form given this — it should be
  the template, and the plan does seem to intend it (ladder step 4: "one
  paired cell at a time").
- **But determinism doesn't protect against overfitting the fixed n=470
  set across a long sequential search.** A +9-hit gate is small relative to
  effect sizes single interventions have already produced on this exact set
  (floor 6→12: +11; wave-1 combo: +43; floor 0→6: +7). Items 1–5 each carry
  multiple tunable choices (field weights, phrase window widths, proximity
  distance thresholds, alias/acronym/date normalization forms, adjacency hop
  counts and gate thresholds) that will be explored sequentially against the
  same fixed, fully-known 470-needle population before any holdout split is
  introduced (that's reserved for ladder step 6, LambdaMART). Nothing stops
  an intervention from being kept because it happened to move 9–11 of these
  specific needles, the same way a single lucky knob already has twice in
  this campaign's history, without addressing the underlying representation
  gap the plan is nominally testing.
- **Several driving cohorts are far too small for a population-level
  decision, and the plan doesn't flag which numbers are anecdote vs.
  estimate.** From the wave-2 doc's own semantic decomposition: 61
  pool-absent / 14 @13–30 / 6 @31–100 / 1 delivery-lost. A "kill iff
  semantic net ≤ 0" rule (W2.1's own, reused implicitly by the plan's
  ladder) is fine at n=125 or even n=61, but conclusions keyed to the
  n=6 or n=1 sub-cohorts (e.g., the single `erb_276` "genuine rescue" in
  the COVER-walk receipt) are single-needle anecdotes, not estimates — the
  plan should say so explicitly wherever a sub-cohort claim this small
  drives a design decision, and should avoid re-deriving per-mechanism
  conclusions from cohorts under ~20 without treating them as
  hypothesis-generating only.
- **The half-set holdout shrinks these further.** `needles_resolved_v09x_half.json`
  (n=235) halves semantic to ~62 and its sub-cohorts to low single/low-double
  digits — a dev/holdout split at half-set granularity, if introduced only
  at ladder step 6 as currently written, would be evaluating LambdaMART on
  cohorts that are already too small to have supported the deterministic
  design decisions feeding its features.
- **Recommendation:** pull the frozen-development-split discipline forward
  to item 3 (fielded cards) rather than deferring it to step 6, and require
  every paired cell from item 1 onward to state, before running, a
  pre-registered kill/graduate threshold in the W2.1 style (this is
  already the plan's practice for the ladder as a whole in spirit — make it
  explicit per rung, not just at the end).

---

## 5. Sequencing

- **Items 1 (fielded cards) before item 2 (structure-aware segmentation +
  parent delivery) may be cart-before-horse.** Fielded cards need stable
  field/unit boundaries to assign content to columns; structure-aware
  segmentation changes what a "unit" is (retrieve unit vs. deliver
  parent/support span). Doing the fielded-card schema work first risks
  rework once segmentation changes what a card's boundaries should be.
  Consider at least prototyping segmentation's unit boundaries before
  locking the fielded-card column schema, even if the full fielded-card
  build stays first in priority.
- **Item 5 (typed adjacency: parent/child, reply-to, same-heading,
  issue/file) overlaps item 2's parent-delivery mechanism.** If item 2
  already produces a parent pointer per unit, item 5's "parent/child" edge
  type may be the same relation observed from the other direction, not an
  independent graph to build. Worth an explicit note on whether item 5 is
  additive to item 2's output or should be folded into it, to avoid
  duplicate engineering.
- **Item 6 (gated PRF) should move out of the main serial ladder entirely**
  given 1a — either cut, or moved to a clearly-labeled "will not build
  unless a fresh falsifier clears it" bucket, so it doesn't read as an
  already-vetted rung between typed adjacency and LambdaMART.
- **Item 7 (LambdaMART) correctly last** — needs the deterministic features
  from 1–5 to exist and needs the clean dev split the plan (correctly)
  says it needs. No objection.
- **`tier_hard_floor_frac` sensitivity (missing per §1c/§3) should enter
  around the same time as item 1**, not after — it's cheap (a config sweep,
  no new code) and materially changes what "candidate-union recall" even
  means for delivery on the plan's own named deployment regime (MULoc-style
  code corpora).

---

## Top findings (ranked)

1. Item 6 (gated PRF) re-proposes a lane the wave-2 skeptic pass explicitly killed "even know-gated," with the deciding fact (gold-free feedback set by construction on miss needles) reconfirmed by the 2026-08-31 vocab-gap receipt — cut it or give it a fresh, pre-registered falsifier before it's ladder-eligible.
2. The plan's "coverage favored gold 16/21" motivating evidence is ERB-only and was already inverted on EnronQA's real paraphrase crater (5/16, "mass → hubs, not gold" — the same failure shape as the COVER-walk kill); any coverage/coordination-discrimination feature built from it needs cross-corpus confirmation before funding, not just the friendly ERB number.
3. An uncommitted receipt (`ladder_muloc_budget14000_2026-08-31.json`) shows doubling `expression_tokens` (7000→14000) produced a byte-identical MULocBench delivered rate — falsifying the token-budget theory for code-corpus delivery caps and pointing at the untested `tier_hard_floor_frac=0.15` score gate instead; this directly touches the plan's own stated deployment regime and isn't in the ladder anywhere.
4. The plan's headline 70%/80% gates are defined on map-based r@12 (320/470), not `delivered_gold_rate` (314/470) — and this codebase's own receipts (the min_delivered_docs floor curve, the COVER-walk arm) prove these two bases can diverge by double digits under levers that move one and not the other; delivered/fr@12 should be the primary gate.
5. Holdout discipline is deferred to the LambdaMART step while a +9-hit target (smaller than at least three single interventions already on record: +7, +11, +43) gets chased across a fully deterministic, fully-known n=470 set through several tunable legs — pull the frozen dev-split practice forward to item 3, and label sub-20 cohort claims (61/14/6/1 semantic decomposition) as hypothesis-generating, not population estimates.
