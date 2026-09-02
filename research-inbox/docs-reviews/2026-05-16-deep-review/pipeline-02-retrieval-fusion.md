# Deep Review — Stage-2 Retrieval & Fusion Path

**Date:** 2026-05-16
**Scope:** retrieval candidate generation + fusion ranking — where *relevant* docs fail to surface (recall failures).
**Reviewer focus:** `knowledge_store.py` retrieval, `retrieval/expand.py`, `retrieval/fusion.py`, `shard_router.py`, query signal extraction (`accel.py`).
**Method:** static trace + reproduction against `benchmarks/genome-bench-2026-05-08.db` (18,936 genes) + analysis of the 2026-05-15 50-needle matrix (`benchmarks/results/claude_matrix_20260515T225605Z/`).
**Read-only:** no source modified.

---

## Executive summary

The retrieval path has a **systematic recall failure for terse, high-value
documents** (config files: `.toml`, `.json`, `.yaml`; and short root-level
`CLAUDE.md`/`FRAMEWORK_BLUEPRINT.md`). The gold doc is usually *generated as a
candidate* but ranked far below the assembly cut because the ranker rewards
keyword density (prose) over the file that actually holds the answer.

Reproduced on `genome-bench-2026-05-08.db`: for the bench query *"How often
does BookKeeper run automatic backups in seconds?"* the gold `bookkeeper.toml`
(which literally contains `backup_interval = 1200`) ranks **#25 of 895**
under the production additive ranker — nowhere near the 5–12 doc delivery cut.

Five compounding root causes, ranked by impact below. The single highest-impact
finding is **F1**: the BGE-M3 dense-recall tier is configured OFF and, even
when on, is structurally skipped in the mode the bench runs — so "hybrid
retrieval" is in practice lexical-only.

Matrix retr-hit (gold_delivered_rate): small 0.30, medium 0.34, large 0.34,
xl 0.34, **medium-sharded 0.50** (cleanest signal), xl-sharded 0.36 (mislabeled,
issue #133). Even the best profile loses half its gold docs in retrieval.

---

## F1 — Dense recall (BGE-M3) is dead in every bench profile  [CRITICAL]

**Claim:** the second-class retrieval signal the architecture advertises —
BGE-M3 dense recall — never runs in the benchmark, for two independent reasons.

### 1a. Config disables it outright

`helix.toml:275` → `dense_embedding_enabled = false`
`helix.toml:298` → `fusion_mode = "additive"`
`helix_context/config.py:280` / `:308` — code defaults agree (`False`, `"additive"`).

The bench harness (`benchmarks/bench_claude_matrix.py`) runs against the live
`helix.toml` with no override, so dense recall is config-off for all 6 profiles.

### 1b. Even with the flag on, additive mode skips dense entirely

`knowledge_store.py:1922`:

```python
if self._dense_embedding_enabled and self._fusion_mode == "rrf":
    ... dense_hits = self.query_docs_dense_recall(...)
```

Dense recall participates in `query_docs()` **only under `fusion_mode == "rrf"`**.
In `additive` mode (the configured default) the dense tier is unconditionally
skipped — the inline comment at `:1918-1921` confirms this is intentional
("keep byte-identical compatibility with pre-Stage-3 ranking"). So a single
config knob (`fusion_mode`) silently controls *whether dense recall happens at
all*, which is surprising and undocumented as a coupling.

### 1c. Sharded mode looks like it uses dense — it does not

`sharding.py:181` sets `ShardedGenomeAdapter._fusion_mode = "rrf"`. A reader
would conclude the sharded profiles do dense+RRF. They do **not**:

- `sharding.py:196` → `ShardedGenomeAdapter._dense_embedding_enabled = False`
  (hard-coded; the adapter "doesn't run dense ... each per-shard Genome handles
  those internally").
- Per-shard `Genome` objects are constructed in `ShardRouter._open_shard`
  (`shard_router.py:305`) with `**self._genome_kwargs` — the *same* kwargs
  `HelixContextManager` passed, i.e. `fusion_mode="additive"`,
  `dense_embedding_enabled=False` (`context_manager.py:481`, `:491`).
- Therefore each shard runs `query_docs()` in **additive** mode → per-shard
  dense recall is skipped at `knowledge_store.py:1922`.
- The adapter's `_fusion_mode="rrf"` only affects the *cross-shard merge*, and
  even there RRF is a **tiebreaker**, not the primary key (see F3).

**Net:** in all 6 bench profiles, retrieval is **tag + FTS5-BM25 + SPLADE +
harmonic + SR**, fused **additively**. The dense semantic recall path — the
thing meant to catch paraphrase gaps — is inert. The matrix even includes a
needle (`helix_dense_encoder`, run.log:195/400/604/808) probing *which* dense
model Helix uses, while that very model is switched off.

**Impact:** every query whose gold doc shares *meaning* but not *surface tokens*
with the query has no recall path. This is the largest single recall gap.

**Fix direction:** decouple dense participation from `fusion_mode`; let dense
recall run in additive mode too (union its hits into `gene_scores`). Backfill
`embedding_dense_v2` on the fixtures (CLAUDE.md gotcha: NULL until
`scripts/backfill_bgem3_v2.py` runs) and turn `dense_embedding_enabled` on for
the bench. Until then, "hybrid retrieval" is a misnomer.

---

## F2 — Query signal extraction destroys the discriminative token  [CRITICAL]

**File:** `helix_context/accel.py:179-198` (`extract_query_signals`) +
`:154-176` (`expand_query_terms`).

Two defects, both reproduced live (`extract_query_signals` run on the actual
bench queries):

### 2a. Filenames are shredded before they become a term

`extract_query_signals` tokenizes with `re.findall(r"[a-z0-9_/\-]+", query)`
(`accel.py:186`). **The character class excludes `.`** Therefore the query
*"...maximum number of fleet workers BigEd boots by default in **fleet.toml**?"*
tokenizes `fleet.toml` into two separate words `fleet` and `toml`. The literal
filename token `fleet.toml` — the single most discriminative term in the query,
and a near-perfect pin for the gold doc — **never exists as a query term**.

Confirmed output for that query:
```
domains[:5] = ['maximum', 'number', 'fleet', 'workers', 'biged']
entities    = [..., 'fleet', 'fleets', ..., 'toml', 'tomls']   # 'fleet.toml' absent
```

`toml`/`tomls` is generic noise (matches every TOML file in the corpus). The
gold-pinning signal is gone at tokenization, step 1 of the pipeline. Same
shredding happens for `bookkeeper.toml`, `helix.toml`, `package.json`,
`marketplace.json`, `pyproject.toml` — every config-value needle in the matrix.

### 2b. `domains` is the first 5 keywords, positionally — including noise

`accel.py:197` → `domains = keywords[:5]`. No IDF ranking, no specificity
filter — just the first five surviving tokens in *sentence order*. English
question words land first, so `domains` is routinely polluted:

| Query | `domains[:5]` (verbatim) |
|---|---|
| "How **often** does BookKeeper **run** automatic backups…" | `['often','bookkeeper','run','automatic','backups']` |
| "How **many** tokens are allocated for the ribosome decoder…" | `['many','tokens','allocated','ribosome','decoder']` |
| "What is the **maximum number** of fleet workers BigEd boots…" | `['maximum','number','fleet','workers','biged']` |
| "What is the **current version** of the MaxExpressKit…" | `['current','version','maxexpresskit','mek','plugin']` |

`often`, `run`, `many`, `maximum`, `number`, `current`, `automatic`, `default`
are **not** in `STOP_WORDS` (`accel.py:121-136`). They flow into:

- **Tier 1 exact-tag** (`knowledge_store.py:1635`) — `tag_value IN (...)` with
  the noise terms, scoring every doc tagged "run"/"default" at +3.0/match.
- **FTS5 OR-query** (`:1708`) — `"often" OR "run" OR "automatic" OR ...`
  drowns the BM25 signal in common-word matches.
- **Shard routing** (`shard_router.py:335`) — `LIKE '%"often"%'` etc. against
  `fingerprint_index` (see F4).

`domains` and `entities` are then merged and `_expand_terms`'d
(`knowledge_store.py:1401-1404`), so the noise also seeds synonym expansion.

**Impact:** the ranker's input is mostly noise. The keyword-density tiers
(tag-count, FTS) reward whichever doc mentions the *common* words most — almost
never the terse config file. This is the mechanism behind F5's #25 ranking.

**Fix direction:** (a) add `.` to the tokenizer class or special-case
`*.ext` filename tokens and keep them as first-class high-IDF terms; (b)
replace `keywords[:5]` with an IDF/specificity-ranked top-N; (c) expand
`STOP_WORDS` with interrogative-quantifier words (`often`, `many`, `much`,
`maximum`, `minimum`, `number`, `current`, `default`, `run`).

---

## F3 — Lexical ranking rewards prose density; the gold config file loses  [CRITICAL]

**Reproduced end-to-end** on `genome-bench-2026-05-08.db`.
Query: *"How often does BookKeeper run automatic backups in seconds?"*
Gold: `BookKeeper/bookkeeper.toml` (gene `940bd622c3e2df6b`), contains
`backup_interval = 1200`.

Running the production additive scoring (Tier-1 exact tag ×3.0 + Tier-2 prefix
×1.5 + Tier-3 FTS5 capped at 6.0):

```
gold rank (additive tag+fts): #25 of 895
top of ranking:
  21.0  BookKeeper/docs/TENANCY_IMPLEMENTATION_SUMMARY.md
  19.5  Education/biged-rs/tests/supervisor_backup_test.rs
  19.5  BookKeeper/bookkeeper/storage/backup.py
  18.0  Education/fleet/backup_manager.py
  ...
  15.0  bookkeeper.toml                          <-- gold, rank 25
```

The gold IS a candidate (#25/895) — it is **not** lost in candidate generation.
It is **demoted by the ranker**. Three mechanics combine:

### 3a. FTS5 score is capped at 6.0 — saturates the lexical signal

`knowledge_store.py:1745` → `fts_score = min(-fts_ranks[gid], 6.0)`. A doc with
a near-perfect BM25 match and one with a mediocre match both saturate at 6.0 in
additive mode. (The comment at `:1743-1744` says the cap was lowered from 45 to
stop FTS drowning tags — but it now also erases FTS's ability to *discriminate*
among lexical matches.) The raw `-rank` is fed to the Fuser (`:1753`) but the
Fuser is unused in additive mode.

### 3b. Tag-count scoring is unnormalized → favors long, verbose docs

Tier 1/2 score = `match_count × weight` (`:1651`, `:1691`). A 400-line `.md`
that mentions many query tags out-scores a 30-line `.toml` purely on volume.
No length normalization, no per-doc cap. `bookkeeper.toml` has 24 tags
(`port, model, url, debug, ...`), most unrelated to "backup".

### 3c. No path/filename signal strong enough to rescue the config file

- **Tier 0 PKI** (`path_key_index`, `:1494-1582`) is the strongest signal but
  needs a `(path_token, kv_key)` pair. Verified: `bookkeeper.toml`'s indexed
  kv_keys are `port, model, url, version, max_tenants, threshold, host, debug,
  ...` — **`backup_interval` is not among them.** The chunker/tagger did not
  extract it as a kv_key, so PKI cannot fire for a "backup" query.
- **Tier 0.5 filename-anchor** (`filename_anchor.py`, enabled —
  `helix.toml:255`) does help: `filename_stem='bookkeeper'` matches the query
  term `bookkeeper`, adding flat +4.0. Re-simulated with it: gold rises to
  **#6 of 895** — but ties at 19.0 with three *unrelated* `backup.rs` files,
  and #6 is still on the edge of a 5-doc cut. The +4.0 is flat and IDF-free:
  a project with a common name gets the same blanket boost (`boost_scores`,
  `filename_anchor.py:189`).

### 3d. RRF would help but not fix it

Re-simulated the same query through `retrieval/fusion.Fuser` (tag_exact ×3.0,
tag_prefix ×1.0, fts5 ×3.0): gold moves #25 → **#11 of 895**. Better, still
below a realistic cut. RRF removes the scale-mismatch problem (F3a/F3b) but
cannot manufacture relevance — both the tag tier and the FTS tier *agree* in
ranking prose above the `.toml`, so rank fusion preserves that agreement.

**Impact:** this is the dominant pattern in the matrix recall failures (see
the BigEd cluster, F4). The ranker structurally cannot prefer "the config file
for project X" over "prose that discusses X's behavior."

**Fix direction:** length-normalize tag-count scores; raise/remove the FTS cap
*and* move to RRF so scale stops mattering; make filename-anchor IDF-weighted
(rare project name → strong boost, common stem → weak); extend kv_key
extraction so config knobs like `backup_interval` become PKI keys.

---

## F4 — Sharded routing & cross-shard merge: subtree-path bias + truncation  [HIGH]

Medium-sharded is the *best* profile (0.50 gold rate) yet still loses half.
The clearest failure cluster is **BigEd: 3/16 gold delivered**.

### 4a. Routing + path-token bias pulls the wrong subtree

The BigEd project ("Education/") gold docs live at the **repo root**:
`Education/CLAUDE.md`, `Education/fleet/fleet.toml`,
`Education/FRAMEWORK_BLUEPRINT.md`, `Education/ROADMAP.md`.

But retrieval consistently delivers `Education/biged-rs/...` files —
`DEPLOYMENT.md`, `README.md`, `docs/RUNBOOK.md`, `deploy/helm/.../values.yaml`,
`biged-rs/Cargo.toml`. Verified across all 16 BigEd needles
(`medium-sharded.jsonl`):

```
biged_max_workers   gold=fleet.toml          delivered: DEPLOYMENT.md, README.md,
                                                        values.yaml, Cargo.toml, RUNBOOK.md
biged_thermal_target gold=fleet.toml         delivered: README.md, DEPLOYMENT.md,
                                                        values.yaml, RUNBOOK.md, Cargo.toml
biged_db_tables     gold=AUDIT_TRACKER.md    delivered: README.md, DEPLOYMENT.md, ...
```

Mechanism: the query term `biged` (or `fleet`) appears **in the path** of every
file under `biged-rs/`, so those docs match the `biged`/`fleet` token in tags,
FTS, source-authority boost (`_apply_authority_boosts`,
`knowledge_store.py:1248-1251` — `+2.0` when a query term is a substring of
`source_id`), and shard routing. The actual config `Education/fleet/fleet.toml`
does **not** have `biged` in its path → it gets no source-authority boost and
loses the path-token race. Retrieval is biased toward the *deepest* path that
echoes the query term, not the doc that holds the answer.

`route()` (`shard_router.py:314-352`) compounds this: it matches query terms
against `fingerprint_index.domains/entities` with `LIKE '%"term"%'`. Those are
*ingest-time* tags. A query term not tagged on the gold doc at ingest (e.g. the
shredded `toml`, or `backup_interval`) cannot route to the gold's shard at all;
and noise terms (`often`, `many`) route broadly to the wrong shards.

### 4b. Cross-shard merge top-K truncation is shallow

`shard_router.py:580-581`:
```python
limit = max(1, int(max_genes) * 2)        # 12*2 = 24
ranked_ids = ranked_ids_full[:limit]
```
The merged candidate set is truncated to **24** before the co-activation pass.
`per_shard_fetch = max_genes*2 = 24` (`:441`), and each shard's `query_docs`
itself returns `max_genes*2`, so the merge sees ~24/shard. A gold doc at
intra-shard rank > ~24 never enters the merge (the comment at `:436-438`
acknowledges exactly this risk). With the F2/F3 ranking defects pushing config
files to rank ~25 *within* a shard, this truncation routinely clips them.

### 4c. Doc-type boost is too narrow and too weak

`_doc_type_boost_for` (`shard_router.py:117-144`) multiplies score by `1.15`
for basenames in `{readme.md, claude.md, index.md}` **only**. It misses every
config file (`fleet.toml`, `bookkeeper.toml`, `*.json`) and structural docs
(`FRAMEWORK_BLUEPRINT.md`, `AUDIT_TRACKER.md`, `ROADMAP.md`) — which are the
gold docs in the BigEd cluster. And `1.15×` cannot overtake the 1.5–2× score
gap that F3's prose-density bias opens. The mechanism (#121) is sound; its
basename allow-list and magnitude are insufficient for the observed failures.

### 4d. IDF correction is merge-scale-only, can't fix intra-shard rank

`_compute_shard_idf_correction` (`shard_router.py:147-252`) rescales each
shard's scores by global-vs-local IDF mismatch — a real cross-shard *scale*
fix. But it is applied as a uniform per-shard multiplier (`:534-538`), so it
**cannot reorder docs within a shard**. If the gold is intra-shard rank 25, IDF
correction keeps it rank 25. The doc-type comment at `:98-101` admits this.

**Impact:** the sharded path's three #118/#120/#121 fixes address scale, graph
reachability, and doc-type — but none addresses the *intra-shard ranking*
defect (F3) that is the actual cause, and the merge truncation (4b) then clips
the mis-ranked gold.

**Fix direction:** widen the merge `limit` (decouple from `max_genes`); expand
`DOC_TYPE_BOOST_BASENAMES` to config + blueprint files and raise the multiplier
(or fold doc-type into the per-doc score *before* the per-shard sort, so it
fixes intra-shard rank); make `route()` fall back to broad fan-out when query
terms are low-IDF/noisy rather than trusting a thin tag match.

---

## F5 — Candidate pool is shallow; assembly cut is shallower  [MEDIUM]

`config.budget.max_genes_per_turn = 12` (`helix.toml:73`).
`knowledge_store.py:1410` → `limit = max_genes * 2 = 24`.

`query_docs()` caps the *entire* scored ranking at 24 (`:2278`, `:2294`) and
the returned candidate list at 24 (`:2352`). The matrix shows actual delivery
of **5–12 docs** (`delivered_count` field), so after assembly/budget the
effective recall window is ~5–12.

When F2/F3 push a gold doc to rank ~25 (reproduced: #25/895 additive, #11 RRF,
#6 with filename-anchor), a 24-deep candidate cut and a ~8-deep delivery cut
both clip it. The pool is not *grossly* undersized, but it leaves zero margin
for the ranking defects above — a correct doc at rank 13–24 is generated and
then silently dropped at delivery. The dense-pool sizing the task flagged
(`k = min(dense_pool_size, limit*4)`, `knowledge_store.py:1927`,
`dense_pool_size=500`) is generous **but moot** — that line is unreachable
because dense recall is off (F1).

**Impact:** amplifies F2/F3/F4 — there is no slack to absorb a mis-ranked gold.

**Fix direction:** decouple the *candidate pool* depth from `max_genes` (keep a
deep pool, e.g. 100–200, for the ranker to work with; cut to `max_genes` only
at assembly). Cheap given retrieval is SQLite-local.

---

## F6 — Retrieval-side conflict pattern: co-equal siblings both demoted  [MEDIUM]

Scoring/selection conflict is owned by a sibling review; noting the
**retrieval-side** instances here.

### 6a. Gold doc sets with siblings — the BM25 shortlist can drop all but one

`bm25_shortlist_enabled = true`, `bm25_shortlist_size = 50` (`helix.toml:260-261`).
`knowledge_store.py:2215-2249`: after all tiers score, `gene_scores` is
**hard-filtered** to the FTS5 BM25 top-50 for the OR-query. Any doc not in that
top-50 is deleted from the ranking regardless of how strongly tag/SPLADE/
harmonic/SR scored it. When a query has several co-relevant gold docs (the
matrix `gold_source` lists routinely have 3–6 paths), the noisy OR-query (F2b)
can let only one or two of them clear the BM25 top-50 — the rest are dropped
*before* the sort even though a non-lexical tier had surfaced them. This is a
retrieval-side "both candidates demoted" pattern: the shortlist is a lexical
gate applied *after* non-lexical recall, silently discarding non-lexical hits.

### 6b. RRF adjacent-rank tie-break can split a tied sibling pair

`retrieval/fusion.py:92-97` + `:117-120`: tied scores get **adjacent** ranks
(not shared), broken by `gene_id` ascending. Two equally-relevant siblings with
bitwise-equal tier scores receive ranks *r* and *r+1*; the one at *r+1* gets a
strictly smaller `1/(k+rank)` contribution from every tier. Across several
tiers this can push the *r+1* sibling below a third, less-relevant doc that
happened to rank consistently. The doc-string defends this as "monotone," but
the practical effect under a tight `max_genes` cut is that one of a co-relevant
pair is demoted out by an arbitrary `gene_id` sort.

### 6c. Co-activation tie at `_expand_coactivated`

`storage/co_activation.py:131-145`: each gene contributes only its first
3 (`co_activated_with[:3]`) or 5 (`typed_co_activated[:5]`) neighbours. If two
co-relevant docs are each other's 4th+ neighbour, neither pulls the other in.
Bounded-fanout pull-forward silently drops mutually-relevant pairs beyond the
slice.

**Fix direction:** make the BM25 shortlist a *soft* re-rank signal, not a hard
`gene_scores` filter (or union non-lexical hits back in); break RRF ties by a
relevance signal (neighbourhood, freshness) before `gene_id`; widen the
co-activation neighbour slice or rank neighbours by edge weight.

---

## F7 — Minor / lower-confidence observations

- **FTS5 drops short query terms.** `knowledge_store.py:1709` —
  `f'"{t}"' for t in query_terms if len(t) > 2`. A 1–2 char needle token
  (`db`, `id`, numeric knobs) is silently excluded from FTS. Same `len > 2`
  filter in `_bm25_candidate_set` (`:1347`) and the shortlist (`:2222`).
- **SR / harmonic depend on co-activation history that a frozen bench corpus
  lacks.** `sr.py` and Tier-5 harmonic (`knowledge_store.py:2021-2059`) only
  reinforce docs reachable via `harmonic_links` edges. On a freshly-ingested
  fixture those edges are sparse/empty, so SR (`sr_enabled=true`,
  `helix.toml:239`) and harmonic contribute ~nothing — the bench effectively
  runs tag+FTS+SPLADE only. Not a bug, but it means two of the configured
  "tiers" are inert on the benchmark, narrowing real recall further.
- **`sema_cold` (Tier-4 mode B) only fires when the pool is starved.**
  `knowledge_store.py:1857` — `if len(gene_scores) < limit // 2` (i.e. < 12).
  The noisy OR-query (F2b) almost always over-fills the pool past 12, so the
  ΣĒMA cold-scan rescue path rarely runs even though it could surface a
  semantically-close doc the lexical tiers missed.
- **`expand_terms` plural variants add low-value noise.**
  `accel.py:140-152` emits `often→oftens`, `run→runs`, `biged→bigeds` — junk
  tokens that widen the FTS OR-query and tag IN-clause for zero recall gain.
- **Telemetry blind spot.** Per-tier contribution telemetry
  (`knowledge_store.py:2190-2205`) records *which tier scored a doc* but there
  is no counter for "gold doc was a candidate at rank N but cut at delivery."
  The matrix's `gold_delivered` is the only visibility, and it conflates
  "never retrieved" with "retrieved then ranked out" — the two failure modes
  need very different fixes (F2/F3 vs F1).

---

## Bench-needle evidence index (medium-sharded — cleanest profile)

True recall failures (`retrieval.gold_delivered=false` AND `score<=0`) — 13/50.
All fit F2/F3/F4: gold is a terse config/blueprint doc; delivery is prose.

| needle | gold (basenames) | delivered (sample) | root cause |
|---|---|---|---|
| `biged_max_workers` | `fleet.toml`, `contract_test.rs` | DEPLOYMENT.md, README.md, values.yaml, Cargo.toml | F4a path-bias + F3 |
| `biged_thermal_target` | `fleet.toml`, `FRAMEWORK_BLUEPRINT.md` | README.md, DEPLOYMENT.md, values.yaml, RUNBOOK.md | F4a + F3 |
| `biged_complex_model` | `fleet.toml`, `FRAMEWORK_BLUEPRINT.md`, `SESSION_HANDOFF.md` | DEPLOYMENT.md, README.md, deployment-supervisor.yaml | F4a + F3 |
| `biged_db_tables` | `CLAUDE.md`, `AUDIT_TRACKER.md`, `AUDIT_TRACKER_COMPLIANCE_REPORT.md` | README.md, DEPLOYMENT.md, Cargo.toml, architecture.md | F4a + F4c |
| `biged_audit_dimensions` | `CLAUDE.md`, `ROADMAP.md`, `ray_trace_plan.md` | dimensions.py, __init__.py, README.md, ray_trace.py | F4a + F3 |
| `biged_core_agents` | `README.md`, `ROADMAP.md`, `boot_sequence.txt` | README.md, values.yaml, RUNBOOK.md, Cargo.toml | F4a + F3 |
| `biged_skills_count` | `CLAUDE.md`, `FRAMEWORK_BLUEPRINT.md`, `ROADMAP.md`, wiki/* | RUNBOOK.md, README.md, values.yaml, DEPLOYMENT.md | F4a + F4c |
| `biged_smoke_tests` | `CLAUDE.md`, `CONTRIBUTING.md`, `CROSS_PLATFORM.md` | README.md, DEPLOYMENT.md, Cargo.toml, RUNBOOK.md | F4a + F3 |
| `bookkeeper_ocr_confidence` | `bookkeeper.toml`, `README.md` | MULTI_TENANT_ARCHITECTURE.md, CLAUDE.md, README.md, GAPS.md | F2a + F3 |
| `bookkeeper_backup_interval` | `bookkeeper.toml` | MULTI_TENANT_ARCHITECTURE.md, README.md, CLAUDE.md, xero_client.py | F2a + F3 (reproduced #25) |
| `mek_version` | `package.json`, `pyproject.toml`, `marketplace.json` | README.md, marketplace.json, SKILL.md | F2a + F3 |
| `helix_ribosome_budget` | `helix.toml`, `README.md`, `config-reference.md` | context_manager.py, compressor.py, CLAUDE.md | F2a + F3 |
| `helix_headroom_port` | `helix.toml`, `config-reference.md` | test_api_walk.py, aliases.py, claude_core_ingest.py, test_server.py | F2a + F3 |

(`gold_delivered=false` with `score=+1` cases are excluded — the gold-label set
lists multiple paths and a sibling chunk was delivered; not a true recall miss.)

---

## Priority-ranked fix list

1. **F1** — decouple dense recall from `fusion_mode`; run BGE-M3 dense in
   additive mode too; backfill `embedding_dense_v2` and enable it for the
   bench. (Largest recall gap; the advertised hybrid retrieval is lexical-only.)
2. **F2** — fix query tokenization so `*.ext` filenames survive as terms;
   replace `domains = keywords[:5]` with IDF-ranked selection; extend
   `STOP_WORDS` with quantifier/interrogative noise. (Restores the gold-pinning
   signal at step 1.)
3. **F3** — length-normalize tag-count scores, raise/remove the FTS 6.0 cap,
   switch the default to RRF, make filename-anchor IDF-weighted. (Stops the
   ranker from preferring prose over the answer-bearing config file.)
4. **F4** — widen the cross-shard merge `limit` (decouple from `max_genes`);
   expand `DOC_TYPE_BOOST_BASENAMES` to config + blueprint files and fold the
   boost into the pre-sort per-doc score; broaden `route()` fallback on noisy
   queries. (Fixes the BigEd 3/16 cluster.)
5. **F5** — keep a deep candidate pool (100–200) independent of the
   `max_genes=12` delivery cut, so a rank-13–24 correct doc is not silently
   clipped.
6. **F6** — make the BM25 shortlist a soft signal not a hard `gene_scores`
   filter; break RRF ties on relevance before `gene_id`.

---

## Files cited

- `helix_context/knowledge_store.py` — `query_docs` 1366–2352, dense gate 1922,
  FTS cap 1745, tag scoring 1651/1691, PKI 1494–1582, BM25 shortlist 2215–2249,
  RRF branch 2259–2294, `query_docs_dense_recall` 2458–2517.
- `helix_context/accel.py` — `extract_query_signals` 179–198, `expand_query_terms`
  154–176, `STOP_WORDS` 121–136, `_STRIP_CHARS` 137.
- `helix_context/retrieval/fusion.py` — `Fuser` 45–177, tie-break 92–120.
- `helix_context/shard_router.py` — `route` 314–352, `query_genes` 356–615,
  `_doc_type_boost_for` 117–144, `_compute_shard_idf_correction` 147–252,
  merge truncation 580–581, cross-shard co-activation 619–805.
- `helix_context/sharding.py` — `ShardedGenomeAdapter` 153–231, `_fusion_mode`
  181, `_dense_embedding_enabled` 196, `open_read_source` 472–486.
- `helix_context/filename_anchor.py` — `boost_scores` 137–196.
- `helix_context/storage/co_activation.py` — `expand_coactivated` 111–181.
- `helix_context/retrieval/freshness.py`, `sr.py`, `lexical_rescue.py`,
  `relevance_window.py`, `fusion_plr.py`, `intent_router.py` — reviewed; no
  retrieval-blocking defects (notes in F7).
- `helix_context/context_manager.py` — retrieval entry 1995–2026, `max_genes`
  flow 1042/1100/1129.
- `helix.toml` — retrieval section 239–308 (`dense_embedding_enabled` 275,
  `fusion_mode` 298, `bm25_shortlist` 260–261, `filename_anchor_enabled` 255).
- Bench: `benchmarks/results/claude_matrix_20260515T225605Z/` (summary.json,
  medium-sharded.jsonl, run.log, uvicorn.log); reproduction DB
  `benchmarks/genome-bench-2026-05-08.db`.
