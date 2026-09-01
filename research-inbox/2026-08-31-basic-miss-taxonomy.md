# ERB "basic" class — miss taxonomy and head-concentration analysis (947k bed)

**Date** 2026-08-31 · **Bed** `F:/tmp/erb_blob_v09x.db` (947k ERB blob)
**Receipt** `wave-1-semantic-ranking-5f1dab/.../receipts/ladder_v09x_w24_min_delivered_2026-08-28.json`, `arms[0] = baseline` (shipped config, `w24_min_delivered_12.toml`)
**Cohort** `question_type == "basic"`, n = 175 of 470
**Companion data** `2026-08-31-basic-miss-taxonomy.json` (per-needle rows + aggregates)

Written in response to Sol's note that *"basic is an upstream benchmark label, not a coherent
Cymatix failure mode."* That is correct. The decomposition below is empirical, needle by
needle, and it does **not** reproduce Sol's proposed sub-classes in the proportions he
guessed — three of them are effectively empty on this bed and one new mode (assembly width)
falls out of the data.

---

## 1. Standing

| basis | value |
|---|---|
| score-map r@2 | 78 / 175 = 44.6% |
| score-map r@5 | 103 / 175 = 58.9% |
| score-map r@12 | 120 / 175 = 68.6% |
| gold found anywhere in map | 138 / 175 = 78.9% |
| **delivered** gold (floor-12 arm) | 115 / 175 = 65.7% |
| misses (`delivered_gold == 0`) | **60** |

Miss rank buckets (rank in the full fused score map; `None` = gold scored zero anywhere):

| bucket | n | share of misses |
|---|---|---|
| pool-absent | **37** | 61.7% |
| rank 13–30 | 13 | 21.7% |
| rank 31–100 | 5 | 8.3% |
| rank ≤ 12 (delivery-lost) | 5 | 8.3% |
| rank > 100 | 0 | — |

---

## 2. Method

- Query keywords via `cymatix_context.accel.extract_query_signals(query)`; token rule
  `[a-z0-9_/\-]+`, `len > 2`, lowercase — the same extractor the pipeline uses.
- **Term / phrase document frequency** by capped FTS5 probe:
  `SELECT count(*) FROM (SELECT rowid FROM genes_fts WHERE genes_fts MATCH 'content: "<x>"' LIMIT 3001)`.
  `genes_fts.content` is `source_id ‖ tags ‖ body` flattened into one column — i.e. exactly
  the field BM25 scores. **Values of 3001 are censored** (`>= 3001`).
- **Tag DF** via `promoter_index` (capped 3001) — measures crowding of the
  `tag_exact` / `tag_prefix` legs only, which is a *different* population from body DF.
- **Filename leg** — 499,094 distinct filename stems pulled from `filename_index`, tokenized
  on `[-_.]`; `fn_files_matching_all` = how many distinct corpus filenames contain **all**
  query terms that matched the gold's filename.
- **Passage-boundary probe** — siblings of each gold via `filename_index(filename_stem)`;
  a sibling "recovers" a keyword if it carries a query keyword absent from the gold union.
- Read-only point reads throughout (a timed arm was live on the bed). No manager-mediated
  query was run.

### Caveats

1. DF probes are censored at 3001; any median reported as 3001 is a **lower bound**.
2. `min_body_df_phrase` is the *minimum* over verbatim query n-grams present in gold. It is
   an **upper bound on what a phrase leg could key on**, not a promise that an SDM
   implementation weights that particular phrase highest.
3. `extract_query_signals` emits plural/singular variants, which inflates `n_kw` and deflates
   `frac_content`. Use `frac_content_norm` / `frac_qword_norm` (stem-collapsed) for any
   coverage claim. Raw `frac_content` medians (0.429 hit vs 0.367 miss) understate coverage
   by ~28 points in both arms.
4. **Per-needle top-5 interloper identities were not available** (the receipt carries ranks,
   not score maps, and running the manager was disallowed). The rank 6–12 cohort is therefore
   characterised by *gold-side* evidence only — what would promote gold, not what currently
   outranks it.
5. `fn_files_matching_all` counts filenames, not genes; one filename maps to 1–8 genes.

---

## 3. The single most important measurement

**Single-term lexical selectivity is essentially nonexistent in this corpus, and phrase
selectivity is 18–67× better.**

| median over cohort | delivered hits (115) | misses (60) | pool-absent (37) | rank ≤5 (103) | rank 6–12 (17) |
|---|---|---|---|---|---|
| min body DF of any query **term** in gold | 1305 | **≥3001** | ≥3001 | 1108 | 2249 |
| min body DF of a verbatim query **phrase** in gold | **11** | 166.5 | 257 | 11 | **10** |
| phrase / term selectivity gain | 67× | 18× | 11.7× | 65× | **90×** |
| min tag DF of a gold **tag** the query hits | 336 | 2169 | ≥3001 | 292 | 801 |
| files (of 499,094) matching all query∩filename terms | **1** | 17 | 17 | 1 | 5.5 |

Counts, not medians:

| evidence available | hits 115 | misses 60 | absent 37 | rank 6–12 (17) |
|---|---|---|---|---|
| some query **term** in gold with body DF ≤ 50 | 18 (16%) | **2 (3%)** | 2 | 1 |
| some query **phrase** in gold with body DF ≤ 50 | **86 (75%)** | 22 (37%) | 12 | **12 (71%)** |
| … with body DF ≤ 200 | 98 (85%) | 32 (53%) | 18 | 13 |
| ≥2 query terms in the gold **filename** | 72 (63%) | 15 (25%) | 13 | 4 |
| … and ≤20 corpus files contain all of them | 62 (54%) | 9 (15%) | 8 | 3 |
| exact query **trigram** verbatim in gold | 87 (76%) | 23 (38%) | 13 | 11 (65%) |

Read that top row again: **only 2 of 60 misses have a single query term that appears in fewer
than 50 of 947k chunks.** The ERB corpus is one fictional company's enterprise archive, so
every topical word ("latency", "autoscaling", "us-east", "rollback", "procurement") occurs in
thousands of chunks. Bag-of-words BM25 over a flattened field has almost nothing to key on.
Where a hit happens today it is because the *co-occurrence* of a rare word sequence
accidentally survives BM25's term-independence assumption. Where it misses, the evidence was
there but only as an ordered phrase or as a filename, neither of which the current index can
weight.

### Reachability check (refutes an "unreachable gold" reading of pool-absence)

For each of the **37 pool-absent** basic misses, a 6-gram taken from the middle of the gold
body was run as an FTS5 phrase query. **37 / 37 returned the gold gene.** Pool-absence in the
basic class is a **ranking / candidate-depth failure, not an indexing or vocabulary-
reachability failure.** This is structurally different from the semantic class, where the 61
pool-absent needles reflected a genuine vocabulary gap.

---

## 4. Taxonomy

Two axes are reported, because they answer different questions.

### 4a. Descriptive mode (what kind of needle failed) — mutually exclusive

| mode | misses 60 | absent 37 | rank 13–100 (18) | rank 6–12 (17) | all 175 |
|---|---|---|---|---|---|
| `literal_fact_generic_terms` — coverage adequate, no query term in gold with body DF < 500; the fact is drowned | **31** | 17 | 14 | 6 | 57 |
| `title_path_named_doc` — query reproduces ≥2 tokens of the gold filename | 12 | 10 | 2 | 4 | 79 |
| `vocabulary_gap` — stem-collapsed query-word coverage of gold < 0.50 | 11 | 10 | 1 | 1 | 20 |
| `delivery_lost_classifier_cap` — gold in map top-12, assembly delivered only 6 seats | **5** | 0 | 0 | 5 | 5 |
| `selective_term_present_but_unranked` | 1 | 0 | 1 | 1 | 13 |
| `passage_boundary` | **0** | 0 | 0 | 0 | 1 |

### 4b. Prescriptive addressability (which deterministic leg would supply a hook) — non-exclusive

| leg | criterion | misses 60 | absent 37 | rank 13–100 (18) | rank 6–12 (17) | hits 115 (reference) |
|---|---|---|---|---|---|---|
| phrase / proximity (strict) | verbatim query phrase in gold, body DF ≤ 50 | **22** | 12 | 7 | **12** | 86 |
| phrase / proximity (loose) | … DF ≤ 200 | 32 | 18 | 11 | 13 | 98 |
| title / path (strict) | ≥2 filename terms, ≤20 corpus files match all | **9** | 8 | 1 | 3 | 62 |
| title / path (loose) | ≥2 filename terms, ≤100 files | 14 | 13 | 1 | 4 | 71 |
| assembly width | gold at map rank ≤12, delivered_count 6 | **5** | 0 | 0 | 5 | 0 |
| fielded KV | ≥2 query terms match gold KV keys | 12 | 7 | 3 | 4 | 38 |
| conservative normalization | stemming creates a *selective* anchor that raw matching missed | 4 | 4 | 0 | 1 | 16 |
| structure / parent | a non-gold sibling chunk carries ≥2 query keywords the gold lacks | **0** | 0 | 0 | 0 | 1 |

Unions over the 60 misses: **strict phrase ∪ title = 26** (5 in both), **loose = 39**.
Excluding the 5 delivery-lost, the 55 retrieval misses give **23 strict / 36 loose**.
**18 of 60 misses have no deterministic hook even under the loose thresholds** — that is the
honest floor for this line of work on this class.

---

## 5. Negative findings (Sol's taxonomy, priced)

Three of the seven proposed sub-classes are effectively empty on this bed. Stating this
explicitly so nobody funds them.

- **Passage boundary: 0 / 60 misses.** ERB source files chunk into 1–8 genes and the gold sets
  already include the sibling chunks (51/60 misses are multi-gold). A non-gold sibling
  carrying the missing query anchors happened in **1 of 175** needles, and that one is a hit.
  "Retrieve unit, deliver parent" has no measurable rescue headroom in the basic class here.
  It may still be right for *delivery* quality; it is not a recall lever.
- **Code-symbol register: 1 / 60 misses.** ERB queries are prose about business and eng
  documents. The one candidate (`erb_027`, git tag / `gh release` commands) is better
  explained by phrase evidence — its best hook is the trigram `"a signed annotated"`, body
  DF = 3, while its best single term is censored at ≥3001.
- **Structured KV as a *distinguishing* mode: no signal.** Every ERB gene is a JSON record, so
  KV-line density is 0.5 in **175/175** needles — hits and misses alike. The narrower
  "query terms match gold KV keys" test fires on 12/60 misses (20%) but on 38/115 hits (33%),
  i.e. it is *anti*-correlated with failure. A fielded-KV leg may still improve precision; it
  is not what is breaking the basic class.
- **Date / number needles:** number-seeking is a wash (miss rate 34.1% vs 34.5%). Date-seeking
  is a real but second-order effect: **47.3% miss rate (26/55) vs 28.3% (34/120)** for
  non-date needles. Worth a normalization sub-leg, not a headline.
- **Tag legs are largely inert as a selectivity mechanism.** The most selective query term
  present in gold's *body* is also one of gold's *tags* only ~14% of the time. `tag_exact` +
  `tag_prefix` cost ~3.2 s of the ~19 s median query and supply a hook with median DF 2169 on
  misses. Worth its own measurement pass.

---

## 6. Worked examples

**`literal_fact_generic_terms` (31 misses)**

- `erb_027` (pool-absent) — *"…creating and pushing a signed annotated Git tag and then making a
  draft GitHub release for the v1.14.0 release?"* Best single term: censored ≥3001.
  Best phrase `"a signed annotated"` → **body DF 3**. Gold `slack/1729999999-tagging-handoff-ops-checkin.json`.
- `erb_001` (rank 20) — *"…name of the new metric added so SRE can track when server-side
  streaming sessions get finalized…"* Best term ≥3001; phrase `"sre can track"` → DF 21.
- `erb_006` (pool-absent) — *"…average triage rubric score change between the older baseline
  build and the newer optimized build…"* Stem-collapsed query coverage 0.739 — the gold has
  the words — but best term ≥3001 and best phrase `"on policy"` DF 1900. **No deterministic
  hook at all**; the discriminator is a numeric delta between two rows of a bisection log.

**`title_path_named_doc` (12 misses)**

- `erb_021` (pool-absent) — *"…recommended liability cap language in the procurement legal
  triage SOP for vendor contracts…"* Filename `procurement-legal-risk-escalation-sop-2026`;
  query matches `{legal, procurement, sop}`; **exactly 1 file of 499,094** contains all three.
  Best phrase `"procurement legal triage"` → DF 4. Best single term: censored ≥3001.
- `erb_025` (pool-absent) — filename `20250603-customer-escalation-private-upgrade-rollback-request`;
  query matches `{customer, private, rollback, upgrade}` → **1 file**. Phrase
  `"the upgrade fails"` DF 5.
- `erb_003` (pool-absent) — filename `2026-01-16-gcp-marketplace-onboarding-and-billing-review`;
  matches `{gcp, marketplace, onboarding}` → 17 files. Phrase `"entitlement is not"` DF 6,
  stem-collapsed coverage 0.947.

**`vocabulary_gap` (11 misses)**

- `erb_042` — *"…brief p99 latency jump on the hosted text generation endpoint in us-west-2…"*
  Coverage 0.400; best phrase `"us west 2"` is itself censored ≥3001. No hook.
- `erb_076` — *"…three-step message sequence used for the new cross-language streaming startup
  handshake in the SDKs?"* Coverage 0.417; best phrase `"in the"`.
- `erb_050` — *"…cost-aware model routing proposal, what telemetry fields were suggested…"*
  Coverage 0.438; best phrase `"cost aware"` DF 2142.

**`delivery_lost_classifier_cap` (5 misses)** — all five had `delivered_count = 6`:

- `erb_053` map rank 11 — phrase `"lattice scheduler into"` **body DF 1**.
- `erb_046` map rank 11 — phrase `"order of exemplars"` **body DF 2**.
- `erb_049` map rank 7, `erb_045` map rank 7, `erb_144` map rank 9.

---

## 7. Head concentration: the rank 6–12 cohort (n = 17)

17 basic needles have gold at map rank 6–12 (12 delivered, 5 delivery-lost). This is the r@5
promotion lever Sol identified. Gold-side profile vs the rank ≤5 population:

| | rank ≤5 (103) | rank 6–12 (17) |
|---|---|---|
| min body DF of any query term in gold | 1108 | 2249 |
| min body DF of a verbatim query phrase | 11 | **10** |
| phrase/term selectivity gain | 65× | **90×** |
| exact query trigram in gold | 79/103 = 77% | **11/17 = 65%** |
| exact query bigram in gold | 103/103 | **17/17** |
| phrase with body DF ≤ 50 | 77/103 = 75% | **12/17 = 71%** |
| ≥2 query terms in the filename | 68/103 = 66% | 4/17 = 24% |
| stem-collapsed query-word coverage | 0.750 | 0.636 |

**This cohort is not term-poor, it is phrase-rich and term-starved.** Its term-level
selectivity is *worse* than the misses' (2249 vs the censored miss median) yet its phrase
selectivity is the best of any cohort measured (median DF 10, 90× gain). Concretely:
`erb_087` `"plant rap"` DF 1, `erb_102` `"span cost delta"` DF 1, `erb_077` `"panel that pins"`
DF 2, `erb_053` `"lattice scheduler into"` DF 1, `erb_046` `"order of exemplars"` DF 2,
`erb_055` `"nccl watchdog timeouts"` DF 7.

These documents sit at rank 6–12 because BM25 gives them term credit only, and the terms are
generic. Every one of them contains a word sequence that occurs in ≤50 chunks of 947k. **The
phrase-proximity leg is the r@5 lever for basic, and the SDM phrase-leg headroom on this
cohort is 12 of 17 needles (71%) at DF ≤ 50, 13 of 17 at DF ≤ 200.** Filename evidence
addresses only 3–4 of them, and normalization 1.

Caveat 4 applies with force here: I could not see *what currently outranks gold*. A phrase leg
promotes gold only if the interlopers do not also carry the phrase — DF ≤ 50 bounds the number
of competitors that could, but does not prove they are absent from the current top-5.

---

## 8. Headroom per proposed leg

Conversion ranges are judgement calls over the measured addressable counts. The measured
counts are receipts; the conversion fractions are not. Basic class is n = 175; score-map
r@12 is 120 and delivered is 115.

| leg | measured addressable (misses) | conservative | optimistic | confidence | notes |
|---|---|---|---|---|---|
| **Assembly width** (raise the width-6 classifier cap to 12 for basic) | 5 | **+5 delivered** | +5 delivered | **very high** | Deterministic and already-ranked. All 6 delivery-lost queries in the whole 470-needle set are in the width-6 bucket; 5 are basic. Zero retrieval change. Costs tokens; 107/175 basic queries already deliver 12. Does **not** move score-map r@12. |
| **Phrase / proximity (SDM)** | 22 strict / 32 loose | **+9 to +13 r@12** | +22 to +28 r@12 | medium-high | Largest pool. Also the r@5 lever: 12/17 of the rank 6–12 cohort. Risk: it re-ranks the whole class, not just the misses — 86/115 current hits also carry a DF ≤ 50 phrase, so a badly weighted phrase leg can churn existing wins. Needs per-phrase IDF weighting and a paired cell. |
| **Title / path leg** | 9 strict / 14 loose | **+6 to +9 r@12** | +12 to +14 r@12 | high (precision) | Highest precision per fire: for hits the median filename match is **unique in 499,094 files**. 8 of the 9 strict cases are pool-absent, so it attacks candidate generation — exactly where basic misses live (37/60). Cheap: a separate FTS column for `source_id` with its own BM25 weight, no new service. |
| **Conservative normalization** | 4 | +1 to +3 | +4 | medium | Small as a *rescue* lever. Its real value is dilution: stem-collapsing raises keyword coverage 0.367 → 0.600 on misses and 0.429 → 0.714 on hits, which mostly de-noises the extractor's plural spam. Ship as an extra leg, not a replacement view. |
| **Fielded KV cards** | 12 | +0 to +3 | +5 | low | Anti-correlated with failure (20% of misses vs 33% of hits). Not the basic-class problem. |
| **Structure / parent delivery** | 0 | **+0** | +0 | high (null) | Refuted on this bed for this class. |

**Union ceiling.** 26 of 60 misses (43%) are addressable by phrase ∪ title at strict
thresholds, 39 (65%) at loose. Excluding delivery-lost: 23 / 36 of the 55 retrieval misses.
Sol's class targets were +3 for basic-70% and +20 for basic-80% at r@12. **70% is comfortable**
— inside the strict union with room to spare. **80% requires converting ~87% of the strict
union**, which is optimistic for a first cut; the loose union (36) would need ~56% conversion,
which is more plausible but depends on thresholds nobody has validated yet.

**Recommended order** — by headroom × confidence:

1. **Title / path leg** first. Highest precision, attacks pool-absence (the dominant bucket),
   smallest surface area, and the receipt is unambiguous: a filename match is a document
   identity signal in this corpus (median 1 file of 499k).
2. **Phrase / proximity leg** second. Biggest pool and the only lever with real r@5
   headroom, but it perturbs the entire ranking and needs a paired cell before graduation.
3. **Assembly width** in parallel — it is a config change worth +5 delivered basic hits
   (+2.9 pp basic delivered recall, +1.3 pp overall) and touches no retrieval code. Should be
   validated for token cost, not for recall.

---

## 9. Surprises

1. **Pool-absence in `basic` means "outranked", not "unreachable".** All 37 pool-absent golds
   are in `genes_fts` and return for an exact phrase probe. The word "absent" has been doing
   double duty across the semantic and basic receipts and means opposite things in each.
2. **Term-level selectivity is gone.** Only 2 of 60 misses (and 18 of 115 hits) have any query
   term in gold appearing in fewer than 50 of 947k chunks. At this corpus scale the *unit* of
   lexical evidence has to change; no amount of term-weight tuning recovers a signal that is
   not there.
3. **The rank 6–12 cohort is the phrase-richest population measured** (median best-phrase
   DF 10, 90× selectivity gain over its best term) while being term-poorer than the misses.
   Head concentration for basic is a phrase problem almost purely.
4. **Passage boundary is zero.** I expected this to be a real slice and it is not — 0/60.
5. The tag legs (`tag_exact` + `tag_prefix`, ~3.2 s of a ~19 s median query) contribute a hook
   with median DF 2169 on misses, and only ~14% of the time is the most selective body term
   even present as a gold tag. Their cost/benefit deserves its own receipt.

---

## 10. Files

- `2026-08-31-basic-miss-taxonomy.json` — per-needle rows (all 175, with `primary_mode`,
  `addressable_by`, `descriptors`, DF measurements, phrase and filename evidence) plus the
  aggregates quoted above.
- Working scripts (also in `research-inbox/`, gitignored): `_basic_taxonomy_build.py`,
  `_basic_taxonomy_classify.py`, `_basic_taxonomy_pass4.py`, `_basic_taxonomy_pass5.py`,
  `_basic_taxonomy_emit.py`. Intermediates: `_basic_raw_rows.json`,
  `_basic_enriched_rows.json`, `_basic_final_rows.json`, `_filename_stems.json`.
