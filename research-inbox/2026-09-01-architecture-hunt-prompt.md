# Architecture hunt: lift ERB delivered gold .668 → .80 (stretch .90)

You're working in F:\Projects\cymatix-context (Cymatix Context — knowledge-store context
compression, v0.9.1, shipped retrieval is fully algorithmic: FTS5 + tags + synonyms,
RRF rrf_k=20, eps_band all classes, min_delivered_docs=12, k=12). Mission: find
retrieval-architecture changes — **new items, tweaks to existing items, or using an
existing signal twice instead of once** (second pass, re-entry, dual granularity) —
that lift delivered gold on full ERB from .668 (314/470) to ≥.80 (+62 needles),
stretch .90 (+109), while keeping query speed roughly flat or at minor cost.
House rules: receipts before flips; paired per-needle A/Bs; new levers ship
default-inert behind a knob; CYMATIX_DISABLE_LEARN=1 on bench runs; 15-min cold gates;
BASELINES.md conventions.

## Metric
delivered_gold_rate on ERB 947k (bed F:/tmp/erb_blob_v09x.db), 470 needles, k=12,
shipped v0.9.1 config. Baseline receipt:
benchmarks/dogfood/erb/receipts/ladder_v09x_w24_min_delivered_2026-08-28.json
(delivered .6681 — byte-reproducible, two exact 470/470 reproductions on record).

## Current miss anatomy (156 misses; interloper mining 2026-08-31, all receipted)
- **61 drowned semantic**: paraphrase queries; gold shares ~15% of query terms;
  pool-absent; winners are same-genre max-length sibling chunks (NO hub effect:
  1,645 unique winners / 1,674 seats). Every read-time rescue signal measured dead.
- **37 basic outranked**: gold HOLDS the exact query phrase (phrase DF ~90× more
  selective than best-term DF; 37/37 return on exact-phrase probe) but bigger chunks
  scattering more distinct terms outrank it.
- **41 near-band (rank 13–100)**: gold often WINS the keyword-coverage duel and still
  loses on RRF lane placement — re-weighting existing lanes is dead (two kills);
  only a NEW independent lane acts here.
- **6 seat-capped** (rank 7–12, 6-seat class cap) + **11 multi-chunk-diluted** other-class.
- Cross-cutting: **chunk-split dilution** — in 65/156 the gold DOC's union coverage
  ties/beats the top winner but its best CHUNK loses. Winners sit at the 4,000-char
  chunk cap 85% vs gold 43% (length = distinct-term coverage subsidy).

## Killed — do not re-propose without new evidence (receipts exist for each)
dense default-ON (−.20..−.33 at every scale) · gated-dense fallback (ceiling measured:
4/86 semantic at k=12, median dense rank 3,020 — dense_ceiling_probe_829k) · SPLADE ·
PRF/PPMI query expansion · W2.1 COVER graph walk (mass→hubs; ERB has no hub substrate) ·
W2.2 in-band coverage tie-break (band geometry at rrf_k=20) · score-threshold abstain
(miss slates score-normal vs hits — hit_slate_sample receipts) · cymatics as semantic
rescue (spectra are term hashes = lexical in a different coat) · expression_tokens
doubling (null on prose AND code) · freshness gate as suspect (0 pass-overs / 3,322
mined misses across 7 beds).

## Live levers, scoped but not built (full map: docs/benchmarks/2026-08-31-interloper-what-wins.md)
1. **Phrase/proximity lane** — separate detail=full evidence FTS enabling exact-phrase
   + NEAR(); targets the 37 basic + near-band basic misses.
2. **Doc-level lane-evidence aggregation before RRF seating** — GROUP BY source_id over
   chunk evidence, seat the best chunk of winning docs. No graph, no new nodes
   (source_id is already a column). Targets the 65/156 duel-flips. Highest-leverage
   single fix on the board.
3. **Title/doc-identity fielded lane** — filenames, companies, years, doctypes as
   first-class matchable fields.
4. **Claims/KV column** — key_values are extracted at ingest and never value-indexed.
5. **Classifier per-class caps** (#205 code constants) + tier_hard_floor_frac ladder.
6. **Write-time question-space enrichment** for the drowned 61: APPEND hypothetical-
   question vocabulary to gold's index entry — never rewrite content (the gemma4:e2b
   ribosome bed receipted 45.8% compression stubs destroying answer containment;
   docs/benchmarks/2026-07-31-tagger-ab-tag-flood.md). Gold-side ceiling probe first:
   enrich only the 61 known gold docs, rerun their 61 queries — minutes, not
   ingest-days. gemma4:e2b itself measured 0.833 r@12 as a 1.4s-median query expander.
7. **Selectivity know-block** — "did the slate match the query's rare anchors" as the
   abstain-truthfulness feature (no recall change; makes "I don't know" true).

## "Use something twice" starters (hypotheses — receipt or kill them)
- Second retrieval pass seeded by first-pass deliveries' TAGS (pseudo-relevance via
  tags, never tested — PRF on terms is the thing that's dead, not tag feedback).
- Score the same FTS lane at two granularities (chunk AND doc-aggregate) and fuse
  both — lever 2 expressed as reuse.
- Phrase-lane second pass fired only when pass 1's slate matches no selective anchor
  (the receipted internal-I-don't-know rescue trigger design).
- Re-extract query signals from the top delivered doc's own phrasing and re-retrieve
  (query echo through the corpus's vocabulary) — displacement risk, gate it.

## Key files
- Mechanism map + lever table: docs/benchmarks/2026-08-31-interloper-what-wins.md ·
  artifact: https://claude.ai/code/artifact/ddf9bb08-1eee-4cd1-9c2e-6b3f24b3ad95
- Interloper dumps (per-miss delivered slates, scores, tags, snippets):
  benchmarks/dogfood/*/receipts/interloper_mine_*_2026-08-31.json · taxonomies:
  benchmarks/dogfood/interloper_taxonomy_wave{1,2}_2026-08-31.json
- Ladder: benchmarks/dogfood/erb/ablation_ladder.py
  (--genome F:/tmp/erb_blob_v09x.db --resolved benchmarks/dogfood/erb/needles_resolved_v09x_full.json
   --gold benchmarks/dogfood/erb/gold_by_needle_v09x.json --limit 0 --k 12
   --arms baseline --config <arm.toml> --per-query --stamp --out <receipt.json>)
- Miner (what-won-instead evidence): benchmarks/dogfood/mine_interlopers.py
- Retrieval core: cymatix_context/knowledge_store.py (query_docs) ·
  cymatix_context/retrieval/ (fusion, classifier, combinators) ·
  cymatix_context/storage/ddl.py (FTS5, default unicode61) · cymatix_context/scoring/
- Baselines/conventions: docs/benchmarks/BASELINES.md ·
  research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md (gitignored)

## Ask
Propose, then build receipts-first: pick the highest-expected-value cell, design the
paired A/B (arm config default-inert), run on the 947k bed with CYMATIX_DISABLE_LEARN=1,
and report per-needle flips (+/−) by class against the w24 floor-12 baseline. Kill fast
and keep the kill receipts. Do not touch shipped defaults without a graduated receipt.
