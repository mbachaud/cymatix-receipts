# Deep Review — Key-Value / Metadata Tagging & Tag-Based Retrieval

**Date:** 2026-05-16
**Scope:** Survey of 2023–2026 research on metadata tagging, query→tag alignment,
hybrid (tag + sparse + dense) retrieval, learned vs heuristic tagging, query
expansion, and entity linking — mapped concretely to helix's `tagger.py`,
`[synonyms]`, the query classifier, and tag-lookup retrieval.
**Status:** Research + analysis only. No source code modified.

---

## 0. The problem, grounded in the bench

The 50-needle full matrix (`benchmarks/results/claude_matrix_20260515T225605Z/`)
shows `gold_delivered` at **0.30–0.50** across profiles (medium-sharded 25/50,
blob ~17/50). I read every `gold_delivered: false` record in `medium.jsonl` and
`medium-sharded.jsonl` (33 and 25 misses respectively). The misses are not
random — they cluster into **one dominant failure mode** plus two secondary ones.

### Failure mode A — query-token-to-tag misalignment on factual KV lookups (dominant, ~80% of misses)

Almost every miss is a factual numeric/value lookup whose answer lives in a
config file or a doc, but the query's natural-language framing shares no token
with the tag (or `kv_key`) near the answer:

| Bench query | Gold source | Why the tag lookup misses |
|---|---|---|
| "How many **skills** does the BigEd **fleet** have?" | `Education/CLAUDE.md`, `fleet.toml` | answer is a prose count (`125 skills`); gold doc tagged with code/domain terms, not `skills`; retrieval returned Rust source + `values.yaml` instead |
| "What **RAM ceiling percentage** does BigEd target…" | `fleet.toml` | config key is `ram_pct` / `max_ram` — query says "ceiling percentage" |
| "BigEd's **CPU thermal cooldown target** in Celsius" | `fleet.toml` | key is `thermal_target_c` / `cooldown_c` — no shared token |
| "**idle timeout** in seconds before BigEd workers go to sleep" | `fleet.toml`, `config.rs` | key `idle_timeout_s` — `[synonyms]` has no `idle`, `timeout` maps elsewhere |
| "**OCR confidence threshold** below which BookKeeper sends invoices to human review" | `bookkeeper.toml` | key `ocr_review_threshold` — `[synonyms]` has no `ocr`, `invoice`, `review` |
| "How often does BookKeeper run automatic **backups** in seconds" | `bookkeeper.toml` | key `backup_interval_s` — no `backup` synonym |
| "current **version** of the MaxExpressKit (MEK) plugin" | `package.json`, `pyproject.toml`, `marketplace.json` | `version` is tagged but `maxexpresskit`/`mek` is an unknown entity → no project anchor |
| "What **port** does the BigEd fleet **dashboard** listen on" | `README.md`, `DEVELOPMENT.md` | `port` synonym exists, but gold is in prose docs, not the `.toml`; retrieval pulled the wrong `.toml` |
| "How many **dimensions** does the BigEd audit tracker grade against" | `CLAUDE.md`, `AUDIT_TRACKER.md` | `dimensions` synonym → `[audit, scoring, preset, ci_cd]` — close, but BigEd docs not tagged `audit` |

Two structural causes:

1. **`tagger.py` produces tags from the document's *surface vocabulary*, not
   from the *questions the document answers*.** A `fleet.toml` line
   `max_skills = 125` yields the KV `max_skills=125` and the domain token
   `fleet` (if "fleet" appears). It will *never* be tagged `skills`, `count`,
   `how many` — the words a user actually queries with. `_extract_domains`
   only emits tokens that are members of the fixed `_TECH_TERMS` set
   (`knowledge_store`/`tagger.py:98`). "skills", "thermal", "cooldown",
   "ocr", "backup" are **not in `_TECH_TERMS`**, so they are never tags.

2. **`[synonyms]` is a hand-maintained, ~70-entry static map** (`helix.toml:387`).
   Fix #124 already shows the failure pattern: the team is manually adding
   synonym keys *after* observing each miss (`fleet`, `ribosome`, `expression`,
   `agents`, `dashboard`, `tables`). This is O(n) human labour against an
   unbounded query vocabulary, and it only patches *one direction* (query
   token → broader bag); it never teaches `fleet.toml` that it answers a
   question about "skills".

### Failure mode B — query expansion fires AFTER signal extraction, and the classifier output is discarded for retrieval

`extract_query_signals` (`accel.py:179`) tokenizes, drops stop-words, keeps
`domains = keywords[:5]` and `entities = [w for w in expanded if len(w)>=4]`.
`expand_query_terms` only adds *morphology* (singular/plural). The `[synonyms]`
expansion happens later in `KnowledgeStore._expand_terms` (`knowledge_store.py:1189`).
Critically: **`classify_query()` runs (`context_manager.py:999`) and produces a
`ClassifierResult` with a `cls` ("factual", "arithmetic", …), but that class
only influences `decoder_mode` and `assembly_max_genes_cap` — it never changes
which *terms* are used for retrieval.** A query classified `factual` and a
query classified `multi_hop` retrieve with byte-identical term sets. The
classifier is a rich, free signal that retrieval throws away.

### Failure mode C — unknown project entities have no anchor

"MaxExpressKit", "MEK", "BookKeeper" are not in `_PROJECT_ENTITIES`
(`tagger.py:69`) nor `[synonyms]`. spaCy's `en_core_web_sm` will sometimes
catch them as `PRODUCT`/`ORG` and sometimes not (it is a small statistical
model). When it misses, the query has no project-level anchor and retrieval
spreads across the whole corpus. The `path_key_index` "Tier 0" — the one tier
designed to nail `(project, key)` lookups — keys on `path_token`, so it only
fires when the query literally contains a path token like `helix` or `fleet`.

---

This review surveys the research that addresses A, B, and C, ranked by
expected impact on helix's `gold_delivered` rate.

---

## Ranked recommendations

| # | Technique | Research basis | Helix change surface | Expected impact |
|---|---|---|---|---|
| 1 | **Document-side expansion (Doc2Query / generated-question tags)** | Nogueira & Lin 2019; Gospodinov et al. 2023 | `tagger.py` — add generated-question tag field | **High** — directly fixes mode A |
| 2 | **LLM-assisted query expansion (Query2Doc / pseudo-doc keywords) gated by the classifier** | Wang et al. 2023; Jagerman et al. 2023 | `context_manager` query-rewrite path + `query_classifier` wiring | **High** — fixes mode B |
| 3 | **Learned sparse retrieval on the ingest side (SPLADE-doc term expansion)** | Formal et al. 2021/2022; Lassance & Clinchant 2022; Nguyen et al. 2024 (DyVo) | `[ingestion] splade_enabled` is already true — verify it expands; raise `splade_weight` | **Medium-High** — already wired, likely under-exploited |
| 4 | **Self-query / structured metadata-filter extraction** | LangChain SelfQueryRetriever; Haystack metadata-filter; Setty et al. 2024 | new pre-retrieval filter-extraction step; reuse `path_key_index` | **Medium** — fixes mode C, tightens KV lookups |
| 5 | **KV-fact "answerable-question" tag taxonomy + unit/quantity normalization** | doc2query schema work; entity-linking literature | `tagger.py` `_extract_key_values` → emit question-form tags | **Medium** — complements #1 for numeric needles |
| 6 | **Entity linking to a project ontology (dynamic vocabulary)** | Nguyen et al. 2024 (DyVo); Ayoola et al. 2022 (ReFinED) | `_PROJECT_ENTITIES` → a real entity registry + alias table | **Medium** — fixes mode C robustly |
| 7 | **RRF fusion as default + per-tier weight tuning** | Cormack et al. 2009; Bruch et al. 2023 | flip `[retrieval] fusion_mode = "rrf"` | **Low-Medium** — infra already present, dark |
| 8 | **Pseudo-relevance feedback over tag co-occurrence** | Lavrenko & Croft 2001; Wang et al. 2023 (LM-PRF) | new optional retrieval tier | **Low** — incremental |

---

## 1. Document-side expansion: tag documents with the questions they answer

### What it is

**Doc2Query** (Nogueira et al. 2019) and its T5 successor **docTTTTTquery**
(Nogueira & Lin 2019) train a seq2seq model to read a passage and *generate
the queries that passage would answer*. The generated queries are appended to
the document before indexing. This is the canonical fix for **vocabulary
mismatch**: the document is now indexed under the *user's* vocabulary, not
just the author's. On MS MARCO, document expansion lifts BM25 substantially
(MRR@10 ~0.184 → ~0.277) purely by enriching the indexed text — neural cost
is paid once at index time, queries stay cheap bag-of-words lookups.

**Doc2Query−−** (Gospodinov et al., ECIR 2023, "Doc2Query−−: When Less is
More", arXiv:2301.03266) shows that ~30% of doc2query's generated queries are
*hallucinated* (the passage does not actually answer them) and that filtering
them with a relevance model *improves* effectiveness while shrinking the index.
**Doc2Query++** (2025, arXiv:2510.09557) adds topic-coverage control so the
generated questions span the document's facets rather than clustering.

### Evidence

- Nogueira & Lin 2019, *From doc2query to docTTTTTquery* — https://cs.uwaterloo.ca/~jimmylin/publications/Nogueira_Lin_2019_docTTTTTquery-v2.pdf
- Nogueira et al. 2019, *Document Expansion by Query Prediction*, arXiv:1904.08375
- Gospodinov, MacAvaney, Macdonald 2023, *Doc2Query−−: When Less is More*, ECIR 2023 — https://arxiv.org/pdf/2301.03266
- Mackenzie et al. 2024, *Revisiting Document Expansion and Filtering for Effective First-Stage Retrieval*, SIGIR 2024 — https://jmmackenzie.io/pdf/mzzm24-sigir.pdf

### Why this is the #1 fix for helix

The bench miss table is *exactly* the vocabulary-mismatch problem doc2query
was invented for. "How many skills does the BigEd fleet have?" misses because
`fleet.toml` / `CLAUDE.md` were never tagged with `skills`, `how many`, `count`.
If, at ingest, helix asked a model *"what questions does this document
answer?"* and got back `["how many skills does the fleet have", "what is the
skill count", "how many agents"]`, those question tokens become tags and the
query lands on Tier 1 (exact tag match, weight 3.0).

helix already has the seam: `[ribosome] enabled` with a `claude` / `litellm`
backend, and `query_expansion_enabled` is described in `helix.toml:40` as a
*query*-side expansion hook. The same `ribosome.pack()` path that `CpuTagger`
replaced for CPU speed is the natural home for an **optional** document-side
question-generation pass.

### Concrete helix change

1. **Schema:** add a `question_tags: List[str]` field to `PromoterTags`
   (`schemas.py`) — or reuse `codons` with a `question:` prefix. Index them
   into `promoter_index` with a new `tag_type = 'question_term'` (the table is
   already `(gene_id, tag_type, tag_value)`; `rebuild_promoter_index` at
   `storage/indexes.py:31` just needs a third insert loop).

2. **Tagger:** in `CpuTagger.pack()`, after the heuristic pass, when a ribosome
   backend is available and a new `[ingestion] question_expansion_enabled`
   flag is on, call the model once per chunk with a fixed prompt:
   *"List 3–6 short questions this text answers. One per line, lowercase."*
   Tokenize the questions (drop stop-words, the same `STOP_WORDS` filter) and
   add the tokens as `question_term` tags. This is the doc2query step.

3. **Filtering (doc2query−−):** drop generated questions whose tokens have
   <1 token overlap with the document body — a cheap, model-free hallucination
   filter that the ECIR 2023 paper validates.

4. **Retrieval:** add a Tier 1.5 that matches query tokens against
   `tag_type='question_term'` rows with a weight between `tag_exact_weight`
   (3.0) and `tag_prefix_weight` (1.5) — these are *generated* tags so they
   should rank below an author-written exact tag but above a prefix match.
   Suggest `question_tag_weight = 2.5` in `[retrieval]`, RRF-participating.

5. **Cost control:** this is ingest-time only. For a CPU-first deployment,
   keep `CpuTagger` as the default and make question-generation a batched
   background `replicate()` pass (the `[ribosome]` section is explicitly
   designed as an idle-time "subconscious" layer). Use Haiku via the existing
   `claude` backend — the bench memory note already establishes Haiku as the
   default bench agent model, and Message Batches API halves the cost.

**Expected impact:** This is the highest-leverage change. It attacks the
dominant failure mode at its root and uses infrastructure that already exists
(ribosome seam, `promoter_index` tag-type column, RRF fuser).

---

## 2. LLM-assisted query expansion, gated by the existing classifier

### What it is

The query-side mirror of #1. **Query2Doc** (Wang, Yang & Wei, EMNLP 2023)
few-shot-prompts an LLM to write a *pseudo-document* (a hypothetical answer
passage) for the query, then concatenates it onto the query before retrieval.
This disambiguates the query and injects the answer's likely vocabulary.
Reported lift: **BM25 +3–15% on MS MARCO / TREC DL with no fine-tuning**, and
gains for dense retrievers too. **HyDE** (Gao et al., ACL 2023, *Precise
Zero-Shot Dense Retrieval without Relevance Labels*) is the dense-only variant:
generate a hypothetical document, embed *that* instead of the query.
**Jagerman et al. 2023** (*Query Expansion by Prompting Large Language Models*,
arXiv:2305.03653, Google) show that asking the LLM for a *chain-of-thought
expansion* or a set of *keywords* often beats pseudo-document expansion and is
cheaper.

### Evidence

- Wang, Yang, Wei 2023, *Query2doc: Query Expansion with Large Language Models*, EMNLP 2023 — https://aclanthology.org/2023.emnlp-main.585/
- Gao, Ma, Lin, Callan 2023, *Precise Zero-Shot Dense Retrieval without Relevance Labels* (HyDE), ACL 2023 — https://aclanthology.org/2023.acl-long.99/
- Jagerman, Zhuang, Qin, Wang, Bendersky 2023, *Query Expansion by Prompting Large Language Models*, arXiv:2305.03653

### Why this fixes failure mode B for helix

Right now `classify_query()` produces a `factual` / `arithmetic` / `procedural`
/ `multi_hop` label and helix *only* uses it to pick `decoder_mode`. The
classifier is a free, infallible router and retrieval ignores it. The research
says different query types want different expansion: a `factual` "what port…"
query wants **keyword expansion** (cheap, precise — Jagerman's keyword mode);
a `multi_hop` query wants **pseudo-document expansion** (Query2Doc) or
**sub-query decomposition** (helix already has `intent_router.sub_queries_for`).

### Concrete helix change

1. **Wire the classifier into retrieval-term selection.** In
   `context_manager`, after `classify_query()`, branch the expansion strategy
   on `classifier_result.cls`:
   - `factual` / `arithmetic` → LLM keyword expansion (Jagerman keyword mode):
     one cheap call returning ~10 lowercase keywords, merged into `domains`
     before `query_docs`. This is the single most surgical fix for the
     "what port / how many / what threshold" misses.
   - `multi_hop` → Query2Doc pseudo-document expansion *or* the existing
     `sub_queries_for` decomposition (already gated by
     `query_decomposition_enabled`).
   - `default` → current behavior (synonym map only).
   This makes the existing `DECODER_MODE_TABLE` pattern (`query_classifier.py:124`)
   the template for a parallel `EXPANSION_MODE_TABLE`.

2. **Make it a config knob, off by default.** Add
   `[retrieval] query_expansion_mode = "synonyms" | "llm_keywords" | "query2doc"`.
   The current `[ribosome] query_expansion_enabled` flag is the natural master
   switch. `helix.toml:40` already documents the cost ("one ribosome call per
   request"); the win is restricting it to *only* the classes that benefit and
   *only* the cheap keyword variant for `factual`.

3. **Dense path:** when `dense_embedding_enabled` is eventually flipped on
   (currently false, `helix.toml:275`), apply HyDE — embed the pseudo-document
   rather than the bare query — for the dense recall tier only.

4. **Latency guard:** the bench shows retrieval `latency_s` ~2.4s already; one
   Haiku keyword call adds ~0.5–1s. Cache the expansion keyed on the normalized
   query (helix has an `adapters/cache`), and skip expansion entirely when the
   classifier emits `arithmetic` with `assembly_max_genes_cap=2` (those need
   precision, not recall breadth).

**Expected impact:** High. It costs one cheap model call on a *subset* of
queries and turns the already-computed classifier label into a retrieval
signal. Pairs naturally with #1 (document expansion + query expansion is the
standard two-sided vocabulary-mismatch fix).

---

## 3. Exploit the SPLADE ingest path that is already enabled

### What it is

**SPLADE** (Formal, Piwowarski, Clinchant — *SPLADE: Sparse Lexical and
Expansion Model for First Stage Ranking*, SIGIR 2021; **SPLADE v2** 2021;
**SPLADE++** / Lassance & Clinchant, *An Efficiency Study for SPLADE Models*,
SIGIR 2022) is **learned sparse retrieval**: a transformer with a masked-LM
head projects each document onto the full BERT WordPiece vocabulary, assigning
a learned weight to every term — *including terms that do not appear in the
document*. It is doc2query and BM25 fused into one model: term expansion +
term weighting, output as a sparse vector indexable in a standard inverted
index. SPLADE-doc (document-side expansion only, query stays bag-of-words) is
the cheap, query-latency-free variant. The 2024 *Mistral-SPLADE*
(arXiv:2408.11119) and *CSPLADE* (AACL 2025) lines show decoder-LLM-based LSR
beating encoder SPLADE.

### Evidence

- Formal, Piwowarski, Clinchant 2021, *SPLADE*, SIGIR 2021 — https://dl.acm.org/doi/10.1145/3404835.3463098
- Formal et al. 2021, *SPLADE v2: Sparse Lexical and Expansion Model for IR*, arXiv:2109.10086
- Lassance & Clinchant 2022, *An Efficiency Study for SPLADE Models*, SIGIR 2022 — https://arxiv.org/pdf/2207.03834
- Naver SPLADE repo — https://github.com/naver/splade
- Nguyen et al. 2024, *DyVo: Dynamic Vocabularies for LSR with Entities*, EMNLP 2024 — https://aclanthology.org/2024.emnlp-main.45/

### Why this matters for helix right now

**`[ingestion] splade_enabled = true` is already set** (`helix.toml:193`) and
`[retrieval] splade_weight = 3.5` is the highest single-tier weight. So helix
*should* already have learned term expansion at ingest. Two things to verify
in the deep review (this survey flags them; implementation review confirms):

1. **Is SPLADE actually producing expansion terms, or is it degenerate?** A
   common failure: the SPLADE backend is loaded but emits only terms present
   in the document (no expansion), making it a slow BM25. Check
   `backends/splade*` — if the model is a *SPLADE-doc* checkpoint it expands;
   if it is a generic MiniLM it does not.
2. **Stage 2 backfill.** `CLAUDE.md` Gotchas already warns that
   `embedding_dense_v2` is NULL until `scripts/backfill_bgem3_v2.py` runs.
   There may be an analogous SPLADE backfill state: documents ingested before
   `splade_enabled` flipped on have no SPLADE vector. If the bench genomes
   were built before that flip, SPLADE is silently contributing nothing.

### Concrete helix change

1. **Audit the SPLADE checkpoint** in `backends/`. It must be a SPLADE/
   SPLADE++ doc-expansion checkpoint (e.g. `naver/splade-cocondenser-ensembledistil`
   or `splade-v3`), not a plain bi-encoder. If it is wrong, swapping the
   checkpoint is a one-line config change with no schema impact.
2. **Confirm SPLADE vectors are populated for the bench corpus.** Add (or run)
   a `scripts/backfill_splade.py` analogous to the BGE-M3 backfill, and gate
   the bench on it the way `CLAUDE.md` already gates on the dense backfill.
3. **Use SPLADE as the term-expansion source for documents instead of (or
   alongside) doc2query #1** — they solve the same problem; SPLADE is a single
   cheaper model. If SPLADE is healthy, #1 becomes lower priority. Recommend
   the deep-review *measure SPLADE health first*, because if it is already
   expanding terms then the bench misses point to a weighting/backfill bug,
   not a missing capability.
4. **DyVo direction (longer-term):** SPLADE splits "MaxExpressKit" into
   nonsensical WordPieces. DyVo augments the SPLADE vocabulary with entity
   embeddings so multi-word project names get a single dimension — directly
   relevant to failure mode C. Track as a follow-up once the entity registry
   (#6) exists.

**Expected impact:** Medium-High, and possibly the *cheapest* — the capability
may already be present and merely mis-configured or un-backfilled. Verify
before building #1.

---

## 4. Self-query: extract structured metadata filters from the query

### What it is

A **self-query retriever** (popularized by LangChain's `SelfQueryRetriever`,
2023; Haystack's metadata-extraction blog, 2024) uses an LLM to parse a natural
language query into (a) a semantic search string and (b) a *structured filter*
over metadata fields. "Bugs filed by Alice in 2024 about auth" →
`search="auth bug"`, `filter={author: "Alice", year: 2024}`. The filter is a
hard constraint applied before/with vector search; it eliminates the
false-positive documents that share vocabulary but not provenance.
Setty et al. 2024 (*Improving Retrieval for RAG based Question Answering Models
on Financial Documents*, arXiv:2404.07221) and the 2025 *Metadata-Driven RAG
for Financial QA* (arXiv:2510.24402) both show metadata filtering materially
improves precision on fact-lookup QA — the same task family as the helix bench.

### Evidence

- LangChain SelfQueryRetriever docs — https://python.langchain.com/docs/how_to/self_query/
- Haystack 2024, *Advanced Retrieval: Extract Metadata from Queries* — https://haystack.deepset.ai/blog/extracting-metadata-filter
- Setty et al. 2024, *Improving Retrieval for RAG-based QA on Financial Documents*, arXiv:2404.07221
- *Metadata-Driven Retrieval-Augmented Generation for Financial Question Answering* 2025, arXiv:2510.24402

### Why this fits helix

helix already *has* the structured-metadata machinery — it just does not
populate the filter from the query:

- `genes.source_id` is a path → project / module / file-type are derivable.
- `path_key_index(path_token, kv_key, gene_id)` is literally a structured
  index. "Tier 0" already does an IDF-weighted lookup against it
  (`knowledge_store.py:1494`), but it fires only when the query *literally*
  contains both a path token and a kv_key token. It has no notion that
  "BigEd" → `path_token=fleet` or "how many skills" → `kv_key=max_skills`.
- `gene_attribution` already supports party scoping.

A self-query step would extract, e.g., from "What is the OCR confidence
threshold in BookKeeper": `project=bookkeeper`, `kv_key≈ocr_threshold`,
`file_type=toml`, and feed those directly into the Tier-0 path-key lookup and
as a `source_id LIKE` filter — turning a corpus-wide spray into a 2–3 document
shortlist.

### Concrete helix change

1. **Project/file-type filter (model-free, ship first).** Build a small
   alias→project map (BigEd→Education, MEK→MaxExpressKit, …) and a file-type
   classifier on the query ("config", "threshold", "port", "version" →
   prefer `.toml/.json/.yaml`). `lexical_rescue.py` already has a
   `_source_path_bonus` doing a primitive version of this — generalize it into
   a real pre-retrieval filter that constrains the candidate set, not just a
   late re-rank bonus. No model call needed.
2. **LLM filter extraction (model-gated, for `factual` class).** When the
   classifier says `factual` and `[retrieval] self_query_enabled = true`, one
   Haiku call returns `{project, module, kv_key_guess, file_type}`. Map
   `kv_key_guess` into the `path_key_index` Tier-0 lookup. This makes Tier 0 —
   helix's highest-confidence tier, designed precisely for KV needles — fire
   on natural-language queries instead of only on queries that happen to
   contain the literal key.
3. **Soft filters, not hard.** Per the GraphRAG / Neo4j 2024 guidance, apply
   metadata as a *score boost* + a *shortlist*, not an exclusionary `WHERE`,
   so an extraction error degrades to current behavior rather than returning
   nothing. helix's `bm25_shortlist` pattern is the right shape.

**Expected impact:** Medium. Step 1 is model-free and directly addresses
failure mode C ("MEK", "BigEd" unanchored). Step 2 activates the dormant
Tier-0 path-key index for the numeric-needle queries that dominate the misses.

---

## 5. KV-fact tagging: emit answerable-question tags and normalize quantities

### What it is

`tagger.py._extract_key_values` (line 397) extracts `port=11437`,
`timeout=30` etc. as KV strings, and `path_key_index` indexes them by `kv_key`.
But the *kv_key* is the raw config token (`max_skills`, `idle_timeout_s`) —
which, again, the user never types. The doc2query insight applied at the KV
level: for each extracted fact, also emit the **question that fact answers**
and a **normalized form** of the key. The entity-linking / knowledge-base
literature (and schema-matching work) consistently shows that aligning a
structured field to a natural-language label space is what makes it queryable.

### Evidence

- Nogueira et al. 2019, *Document Expansion by Query Prediction* (the
  question-generation principle) — arXiv:1904.08375
- Entity/attribute linking surveys — e.g. Sevgili et al. 2022, *Neural Entity
  Linking: A Survey*, Semantic Web Journal
- Quantity/units in IR: Almasian et al. 2022, *Quantity-aware Ranking*
  (quantity normalization for numeric queries), CIKM 2022

### Concrete helix change

In `_extract_key_values`, for each `key=value`:

1. **Key normalization / decompounding.** `idle_timeout_s` → also emit tokens
   `idle`, `timeout`, `seconds`; `max_skills` → `max`, `skills`, `count`;
   `ocr_review_threshold` → `ocr`, `review`, `threshold`. Split on `_`/`-`/
   camelCase and strip unit suffixes (`_s`, `_ms`, `_pct`, `_gb`). These become
   `tag_type='kv_key_token'` rows. This *alone* would catch
   "idle timeout", "how many skills", "OCR … threshold" misses — the query
   tokens would finally have a matching tag.
2. **Question-form KV tag.** Emit a synthetic question tag per fact:
   `max_skills=125` → `question_term` tokens from "how many skills".
   A tiny rule table (key contains `max_`/`count`/`num_` → "how many …";
   `_threshold`/`_floor` → "what threshold …"; `port`→"what port …";
   `_interval_s`/`timeout` → "how often / how long …") does this with **no
   model call** — it is `_classify_intent`-style heuristics, which helix
   already trusts.
3. **Unit awareness.** When the query says "in seconds" / "percentage" /
   "in Celsius", boost facts whose value carries the matching unit
   (`_s`, `_pct`, `_c`). This is the Almasian 2022 quantity-aware idea in
   miniature and directly serves bench queries like "...in seconds",
   "...percentage", "...in Celsius".

**Expected impact:** Medium. Pure-heuristic, no model dependency, no new
infra — extends the existing regex KV extractor and the `tag_type` column.
A strong, cheap complement to #1 specifically for the numeric needles.

---

## 6. Entity linking against a real project ontology (dynamic vocabulary)

### What it is

`_PROJECT_ENTITIES` (`tagger.py:69`) is a hand-typed list fed into a spaCy
`EntityRuler`. It is a proto-ontology with no aliases, no IDs, no
query-side resolution. The research direction:

- **ReFinED** (Ayoola et al., NAACL 2022, *ReFinED: An Efficient
  Zero-shot-capable Approach to End-to-End Entity Linking*) — fast entity
  linking that resolves surface mentions to a KB, *including unseen entities*
  via descriptions. The relevant idea: a mention → canonical-entity resolver
  with an alias table.
- **DyVo** (Nguyen et al., EMNLP 2024) — adds entity dimensions to a learned
  sparse retriever so multi-word entities are first-class index terms instead
  of WordPiece fragments. Substantially beats SPLADE on entity-rich ranking.
- **Entity-aware tagging in enterprise search** generally: a small curated
  ontology + alias normalization is repeatedly shown to beat free-text tagging
  for precision on named-thing queries.

### Evidence

- Ayoola, Tyagi, Fisher, Christodoulopoulos, Pierleoni 2022, *ReFinED*, NAACL 2022 (industry track) — arXiv:2207.04108
- Nguyen, Chatterjee, MacAvaney, Mackie, Dalton, Yates 2024, *DyVo*, EMNLP 2024 — https://aclanthology.org/2024.emnlp-main.45/
- Sevgili et al. 2022, *Neural Entity Linking: A Survey*, Semantic Web Journal 13(3)

### Concrete helix change

1. **Promote `_PROJECT_ENTITIES` to a registry with aliases.** A small TOML/
   JSON file: each canonical entity has `id`, `canonical`, `aliases`,
   `type`, optionally `path_prefix`. e.g.
   `{id:"biged", canonical:"BigEd", aliases:["BigEd CC","biged-rs","the fleet"], path_prefix:"Education/"}`,
   `{id:"mek", canonical:"MaxExpressKit", aliases:["MEK"]}`.
2. **Ingest side:** the `EntityRuler` is fed *all* aliases, and every alias
   match writes the **canonical id** as the `entity` tag (so `biged-rs` and
   "the fleet" both index as `biged`). This normalizes the entity tag space.
3. **Query side:** resolve query mentions to the same canonical ids before
   `query_docs`. "BigEd fleet" → `biged` → which (via `path_prefix`) also
   lets the self-query filter (#4) constrain to `Education/`. This is the
   piece that fixes "MaxExpressKit (MEK)" and "BookKeeper" having no anchor.
4. **Maintenance:** the registry can be *bootstrapped* from the corpus —
   harvest frequent capitalized n-grams and directory names, let a human (or a
   one-shot LLM pass) confirm canonical/alias groupings. This is far smaller
   and more stable than the unbounded `[synonyms]` map, because the entity set
   of a codebase is finite and slow-changing.

**Expected impact:** Medium. Fixes failure mode C robustly and makes the
self-query project filter (#4) reliable. Lower urgency than #1/#2 because the
bench has fewer pure entity-resolution misses than vocabulary-mismatch misses,
but it is a structural cleanup that the `[synonyms]` map is currently
(badly) substituting for — note how `[synonyms]` already contains entity
aliasing like `biged = ["biged-rs", ...]`, `cosmictasha = ["cosmic","tasha",...]`.
That belongs in an entity registry, not a synonym map.

---

## 7. Make RRF the default fusion mode

### What it is

**Reciprocal Rank Fusion** (Cormack, Clarke, Büttcher, SIGIR 2009,
*Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning
Methods*) combines ranked lists by `score(d) = Σ 1/(k + rank_i(d))`. It is the
standard, hyper-parameter-light way to fuse heterogeneous retrievers (tag,
sparse, dense) whose raw scores are not comparable. Bruch et al. 2023
(*An Analysis of Fusion Functions for Hybrid Retrieval*, ACM TOIS) confirm
rank-based fusion is robust precisely *because* it discards incommensurable raw
scores — which is exactly helix's situation (tag score = `match_count × 3.0`,
SPLADE score, dense cosine — all different scales, currently *added*).

### Evidence

- Cormack, Clarke, Büttcher 2009, *Reciprocal Rank Fusion…*, SIGIR 2009 — https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- Bruch, Gai, Ingber 2023, *An Analysis of Fusion Functions for Hybrid Retrieval*, ACM TOIS 41(4)

### Why for helix

`[retrieval] fusion_mode = "additive"` is the default (`helix.toml:298`); RRF
is fully implemented (`retrieval/fusion.py`, `Fuser`, `rrf_k=60`) and *dark*.
The additive accumulator means a single tier with a large raw score (e.g.
Tier 0 PKI capped at +12) can dominate the *agreement* signal that fusion of
tag+sparse+dense is supposed to surface. `CLAUDE.md` Gotchas already states
"RRF will become default in a future version." The bench is the moment:
flip `fusion_mode = "rrf"` for an A/B. The deprecation timeline is already
written into `helix.toml:298`.

### Concrete helix change

Flip `fusion_mode = "rrf"`; run the matrix A/B. The per-tier weights
(`fts5_weight`, `splade_weight`, `tag_exact_weight`, …) are already RRF
post-multipliers in the code. If RRF wins on `gold_delivered`, ship it as
default per the documented timeline. Zero new code.

**Expected impact:** Low-Medium and free — pure config flip + measurement.
Most useful *after* #1/#3 add real recall tiers, since RRF's value grows with
the number of independent retrievers being fused.

---

## 8. Pseudo-relevance feedback over the tag co-occurrence graph

### What it is

Classic **PRF** (Lavrenko & Croft, *Relevance-Based Language Models*, SIGIR
2001; the RM3 family) does a first retrieval, assumes the top-k are relevant,
harvests their salient terms, and re-queries. The modern LLM variant is
**LM-PRF / GRF** (Mackie et al. 2023, *Generative Relevance Feedback*, SIGIR
2023). helix has the raw material for a *graph* PRF: the co-activation graph
(`harmonic_links`), `expand.py`, and the `[synonyms]` reverse map.

### Evidence

- Lavrenko & Croft 2001, *Relevance-Based Language Models*, SIGIR 2001
- Mackie, Chatterjee, Dalton 2023, *Generative Relevance Feedback*, SIGIR 2023 — arXiv:2304.13157

### Concrete helix change

After Tier 1–3, take the top-3 documents' *own* `promoter.domains`/`entities`
tags (helix already fetches these — `get_promoter_batch` at
`knowledge_store.py:3136`), select tags not in the original query, and run one
additional tag-lookup tier with a discounted weight. This is RM3 over tags,
fully model-free. It would, e.g., let an initial weak hit on a BigEd doc pull
in sibling BigEd docs via shared `fleet`/`biged` tags.

**Expected impact:** Low / incremental. Worth it only after #1–#4; on its own
PRF amplifies whatever the first pass found, and if the first pass missed the
gold entirely (the common bench case) PRF cannot recover it.

---

## Cross-cutting: stop hand-maintaining `[synonyms]`

`[synonyms]` is doing three different jobs badly:

1. **Query expansion** (`slow → [performance, latency, …]`) — should be
   subsumed by learned query expansion (#2) or document expansion (#1).
2. **Entity aliasing** (`biged → [biged-rs, …]`, `cosmictasha → […]`) —
   belongs in the entity registry (#6).
3. **Domain-tag enrichment** (the reverse map in
   `CpuTagger._reverse_synonyms` adds parent tags at ingest) — should be a
   learned/ontology relation, not a flat synonym list.

Fix #124's pattern — adding a synonym key every time the bench surfaces a
miss — is unsustainable: it is supervised learning with a human in the
gradient step, one example at a time. Each of #1/#2/#5/#6 replaces a slice of
`[synonyms]` with something that generalizes. Recommended end state: keep
`[synonyms]` only as a small operator-override escape hatch; move its real
load onto learned/structured mechanisms.

---

## Suggested sequencing for the deep review / implementation

1. **First, measure (cheap, no code):** flip `fusion_mode = "rrf"` (#7) and
   audit SPLADE health + backfill state (#3). Re-run the matrix. This may
   recover several points with zero new capability and tells you whether the
   sparse-expansion tier is already alive.
2. **Then, the model-free tagger wins (#5 KV-key decompounding + #4 step 1
   project/file-type filter + #6 entity registry).** No model dependency, no
   latency cost, attacks failure modes A (numeric subset) and C directly.
3. **Then, the model-assisted expansions (#1 doc2query question-tags, #2
   classifier-gated query expansion).** Highest ceiling, but cost the ribosome
   seam — sequence them after the free wins so their measured lift is clean.
4. **Last, PRF (#8)** as a top-up once recall is healthy.

This ordering front-loads the changes that are cheapest and lowest-risk
(config flips, heuristic tagger extensions) and defers the model-dependent
work until the measurement baseline is clean.

---

## Appendix — full citation list

| Paper | Authors | Venue / Year | URL |
|---|---|---|---|
| Document Expansion by Query Prediction (doc2query) | Nogueira, Yang, Lin, Cho | arXiv 2019 | https://arxiv.org/abs/1904.08375 |
| From doc2query to docTTTTTquery | Nogueira, Lin | tech report 2019 | https://cs.uwaterloo.ca/~jimmylin/publications/Nogueira_Lin_2019_docTTTTTquery-v2.pdf |
| Doc2Query−−: When Less is More | Gospodinov, MacAvaney, Macdonald | ECIR 2023 | https://arxiv.org/pdf/2301.03266 |
| Revisiting Document Expansion and Filtering for Effective First-Stage Retrieval | Mackenzie et al. | SIGIR 2024 | https://jmmackenzie.io/pdf/mzzm24-sigir.pdf |
| Query2doc: Query Expansion with LLMs | Wang, Yang, Wei | EMNLP 2023 | https://aclanthology.org/2023.emnlp-main.585/ |
| Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE) | Gao, Ma, Lin, Callan | ACL 2023 | https://aclanthology.org/2023.acl-long.99/ |
| Query Expansion by Prompting LLMs | Jagerman, Zhuang, Qin, Wang, Bendersky | arXiv 2023 | https://arxiv.org/abs/2305.03653 |
| SPLADE: Sparse Lexical and Expansion Model for First Stage Ranking | Formal, Piwowarski, Clinchant | SIGIR 2021 | https://dl.acm.org/doi/10.1145/3404835.3463098 |
| SPLADE v2 | Formal, Lassance, Piwowarski, Clinchant | arXiv 2021 | https://arxiv.org/abs/2109.10086 |
| An Efficiency Study for SPLADE Models | Lassance, Clinchant | SIGIR 2022 | https://arxiv.org/pdf/2207.03834 |
| Mistral-SPLADE: LLMs for better Learned Sparse Retrieval | Doshi et al. | arXiv 2024 | https://arxiv.org/abs/2408.11119 |
| DyVo: Dynamic Vocabularies for Learned Sparse Retrieval with Entities | Nguyen, Chatterjee, MacAvaney, Mackie, Dalton, Yates | EMNLP 2024 | https://aclanthology.org/2024.emnlp-main.45/ |
| ReFinED: Efficient Zero-shot-capable End-to-End Entity Linking | Ayoola et al. | NAACL 2022 (industry) | https://arxiv.org/abs/2207.04108 |
| Neural Entity Linking: A Survey | Sevgili et al. | Semantic Web Journal 2022 | (SWJ 13(3)) |
| Reciprocal Rank Fusion outperforms Condorcet… | Cormack, Clarke, Büttcher | SIGIR 2009 | https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf |
| An Analysis of Fusion Functions for Hybrid Retrieval | Bruch, Gai, Ingber | ACM TOIS 2023 | (TOIS 41(4)) |
| Relevance-Based Language Models (PRF/RM) | Lavrenko, Croft | SIGIR 2001 | (ACM DL) |
| Generative Relevance Feedback | Mackie, Chatterjee, Dalton | SIGIR 2023 | https://arxiv.org/abs/2304.13157 |
| Improving Retrieval for RAG-based QA on Financial Documents | Setty et al. | arXiv 2024 | https://arxiv.org/abs/2404.07221 |
| Metadata-Driven RAG for Financial Question Answering | — | arXiv 2025 | https://arxiv.org/html/2510.24402v1 |
| Quantity-aware Ranking | Almasian et al. | CIKM 2022 | (ACM DL) |

Practitioner references (not peer-reviewed, cited as implementation patterns):
LangChain SelfQueryRetriever — https://python.langchain.com/docs/how_to/self_query/ ;
Haystack metadata-filter extraction — https://haystack.deepset.ai/blog/extracting-metadata-filter .
