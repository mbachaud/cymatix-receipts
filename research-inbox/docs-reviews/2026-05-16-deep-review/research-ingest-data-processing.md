# Deep Review — Ingest / Data Processing for RAG Recall

**Date:** 2026-05-16
**Scope:** Research survey of document/data-processing techniques for RAG ingest, mapped to concrete `helix-context` code changes.
**Status:** Research + analysis only. No source code modified.

---

## 1. Problem framing — what the bench actually tells us

The 50-needle full-matrix bench (`benchmarks/results/claude_matrix_20260515T225605Z/`) shows
**retrieval is the dominant failure mode**, not the LLM:

| Profile | gold_delivered_rate | answers correct |
|---|---|---|
| small | 0.30 | 27/50 |
| medium | 0.34 | 27/50 |
| large | 0.34 | 26/50 |
| xl | 0.34 | 27/50 |
| medium-sharded | **0.50** | 24/50 |
| xl-sharded | 0.36 | 21/50 |

When the gold doc *is* delivered, the agent answers it; when it isn't, the agent
guesses. So **every recall point is worth roughly one answer point.** The ceiling
is the retriever, full stop.

Inspecting the miss records (`gold_delivered: false`) shows a clear pattern. The
misses are concentrated in two query shapes:

1. **Count / aggregation queries** — "How many skills does the BigEd fleet have?",
   "How many steps are in the Helix expression pipeline?", "How many tokens are
   allocated for the ribosome decoder prompt?". The answer is a *number* that
   either (a) lives in one sentence whose vocabulary doesn't match the query, or
   (b) must be *derived* by counting items spread across a doc/corpus.
2. **Named-fact queries against prose** — "What is the default local model used
   by BigEd for conductor tasks?", "What is the target compression ratio?". The
   fact is one clause buried in a 1000-token chunk dominated by other topics.

Both are **query-document vocabulary/granularity mismatches**: the question is a
short interrogative; the answer is one clause inside a long, topically-mixed
chunk whose pooled dense vector is dominated by the *other* 950 tokens.

### Current ingest pipeline (what we are changing)

- `helix_context/context_manager.py:668` `ingest()` — orchestrator. Chunks via
  `CodonChunker`, tags via `CpuTagger.pack()`, attaches a 20-D **SEMA** vector
  (`gene.embedding`), upserts. Creates a parent doc when N>=2 chunks
  (`_upsert_parent_doc`, line 795).
- `helix_context/encoding/fragments.py` — `CodonChunker`. `max_chars=4000`
  (~1000 tokens). Text = paragraph-greedy fill; code = tree-sitter AST (good)
  with regex fallback. **Fixed, large chunks.**
- `helix_context/tagger.py` — `CpuTagger`. spaCy NER + a hard-coded
  `_TECH_TERMS` dictionary + regex KV extraction + noun-chunk "codons" +
  extractive `complement`. **No surrounding-document context; tags limited to a
  closed vocabulary.**
- `helix_context/backends/bgem3_codec.py` — BGE-M3 dense encoder. **Only the
  dense head is used.** `embedding_dense_v2` is a BLOB column that is *NULL at
  ingest* — populated only by a separate `scripts/backfill_bgem3_v2.py` sweep.
- `helix_context/storage/ddl.py:317` — FTS5 over `source_id + tag_values +
  content`. BM25 lexical rescue (`retrieval/lexical_rescue.py`).

Three structural weaknesses jump out before we even reach the literature:

- **W1 — Dense recall is bolt-on.** BGE-M3 vectors are not written by `ingest()`.
  Any genome ingested via `helix ingest` / `/ingest` has *zero* dense recall
  until an operator remembers to run the backfill script. The bench corpus may
  itself be running on tag + BM25 + SEMA-20D only. (CLAUDE.md "Gotchas" confirms:
  *"BGE-M3 dense vectors are NULL until you run scripts/backfill_bgem3_v2.py."*)
- **W2 — BGE-M3's sparse + multi-vector heads are thrown away.** BGE-M3 emits
  dense, sparse (lexical), and ColBERT-style multi-vectors *in a single forward
  pass at no extra cost*. Helix calls `encode()` which returns dense only.
- **W3 — Chunks are large, fixed, and context-free.** 1000-token chunks with
  no document/section context prepended. A one-clause fact is diluted ~50:1 in
  the pooled vector and has no lexical anchor to the doc it came from.

The rest of this document surveys the research that addresses W1–W3 and ranks
the fixes by expected recall impact on *this* bench.

---

## 2. Technique survey

Each technique: what it is, the evidence, the helix mapping. Ranked summary in §3.

### 2.1 Contextual Retrieval / contextual chunk augmentation  ⭐ highest impact

**What.** Before embedding/indexing a chunk, prepend a short (50–100 token)
chunk-specific blurb that situates it in its parent document: what document it's
from, what section, what the surrounding discussion is. Anthropic generates the
blurb with an LLM ("Contextual Embeddings" + "Contextual BM25"); the cheaper
variant — **Contextual Chunk Headers (CCH)** — prepends a *deterministic* header
(document title + section path) with no model call.

**Evidence.**
- *Introducing Contextual Retrieval*, Anthropic, Sep 2024
  (<https://www.anthropic.com/news/contextual-retrieval>). Contextual Embeddings
  cut top-20 retrieval failure **35%** (5.7% → 3.7%); + Contextual BM25 cut it
  **49%** (→ 2.9%); + rerank **67%** (→ 1.9%). Gains held across codebases,
  scientific papers, and fiction.
- *Reconstructing Context: Evaluating Advanced Chunking Strategies for RAG*,
  arXiv:2504.19754, Apr 2025 (<https://arxiv.org/abs/2504.19754>). The
  deterministic CCH variant lifted the mean score **4.72 → 6.04 (+27.9%)** across
  four datasets — i.e. **most of the contextual-retrieval win does not need an
  LLM**, just a document/section header.

**Why it fixes this bench.** The dominant failure is one-clause facts in
topically-mixed chunks. A chunk that currently embeds as "...the conductor model
handles routing... [950 other tokens]..." would, with a header, embed as
`[helix-context/README.md > Expression pipeline] The 7-stage pipeline...`. The
query "how many steps in the Helix expression pipeline" now (a) lexically
matches `pipeline`, `Helix`, `expression` *in the chunk text itself* — directly
feeding FTS5/BM25 — and (b) pulls the pooled dense vector toward the section
topic. This is precisely the no_promoter_match / wrong-folder miss class.

**Concrete helix mapping.**
- *New module* `helix_context/encoding/contextual_header.py`: `build_chunk_header(strand, full_content, source_id) -> str`.
  Deterministic, no model:
  - Document identity from `source_id` (basename + parent dir — reuse
    `filename_anchor.filename_stem`).
  - For Markdown: nearest preceding `#`/`##` heading above the strand's char
    offset (track offsets in `CodonChunker._chunk_text`).
  - For code: enclosing class/module — `tree_chunker` already has the AST; emit
    the qualified name as the header.
  - First sentence of the document as a one-line "doc gist".
- *Wire it in* `context_manager.ingest()` (around line 700, before
  `cpu_tagger.pack`): compute `header`, store it on a new `PromoterTags`/schema
  field `context_header`, and **prepend `header + "\n"` to the text fed to the
  embedding encoder and to the FTS5 row** — but NOT to `gene.content` (keep raw
  content clean for the splice stage and for elision-stub byte hashes).
- *FTS5 change* (`storage/ddl.py:_create_fts5`): the INSERT already concatenates
  `source_id + tag_values + content`; add `context_header` to that concat so
  Contextual-BM25 falls out for free.
- The chunker must start returning a char offset per `RawStrand` (add
  `start_offset: int` to the dataclass) so the header builder can find the
  enclosing heading. This is a small, mechanical change to the paragraph/AST
  loops.
- **LLM-generated variant (later, opt-in):** add an `[ingestion]
  contextual_blurb_backend` knob that, when set, calls the existing compressor
  (`backends/compressor.py`) once per chunk with prompt-cached parent content
  (Anthropic's prompt-cache trick makes this ~1¢/M tokens). Default off; the
  deterministic CCH path is the baseline win.

**Risk / caveat.** Late-chunking's paper (§2.3) found contextual augmentation
*counterproductive on synthetic Needle-8192 / Passkey-8192* where a needle sits
in unrelated filler — the surrounding context is noise, not signal. helix's
fixtures are NIAH-style, so the *blurb* must describe the chunk's own section,
not the whole noisy file. The deterministic section-heading header is safe here
(it summarizes the local section); a whole-document LLM blurb is the risky one.
This is why CCH is ranked above LLM contextualization.

---

### 2.2 Proposition / atomic-fact decomposition (Dense X Retrieval)  ⭐ high impact

**What.** Instead of (or in addition to) indexing 1000-token chunks, decompose
the document into **propositions** — minimal, self-contained, decontextualized
factoid sentences ("BigEd's conductor model is qwen3:8b." rather than "...it
uses qwen3:8b for that."). Index propositions as the retrieval unit.

**Evidence.**
- *Dense X Retrieval: What Retrieval Granularity Should We Use?*, Chen et al.,
  EMNLP 2024 (<https://aclanthology.org/2024.emnlp-main.845/>,
  arXiv:2312.06648). Indexing by propositions **significantly outperforms
  passage- and sentence-level units** for dense retrieval, and improves
  downstream QA at a fixed token budget. They release FactoidWiki (Wikipedia
  re-segmented into propositions).
- Granularity is the single biggest lever in their ablation — bigger than the
  choice of retriever.

**Why it fixes this bench.** Count/named-fact needles are *exactly* propositions.
"The expression pipeline has 7 stages" as its own indexed unit has a pooled
vector that is 100% about that fact — no 50:1 dilution. The query embedding lands
on it directly. This attacks the miss class at its root: granularity.

**Concrete helix mapping.**
- helix already has a *fact-extraction surface* — `CpuTagger._extract_key_values()`
  pulls `port=11437`, `model=qwen3` via regex, and the `Claim` schema +
  `scripts/backfill_claims.py` extract structured claims (`CLAIM_TYPES`
  includes `config_value`, `benchmark_result`, `version_marker`). **The
  retrieval-unit half is missing: claims/KVs are not independently embedded or
  FTS-indexed as their own searchable rows.**
- *Phase 1 (CPU-only, ship first):* in `tagger.py`, after `_extract_complement`,
  add `_extract_propositions(doc) -> list[str]` — spaCy-driven: take each
  sentence containing a named entity or numeric literal, resolve trivial
  pronouns to the doc subject, emit as a standalone string. Store on a new
  `propositions: List[str]` schema field.
- *Index them:* extend `storage/ddl.py` with a `proposition_fts` FTS5 table
  (`gene_id, proposition_text`) so propositions are BM25-searchable as
  fine-grained units that point back to the owning gene. This is the cheap 80%.
- *Phase 2 (dense):* embed each proposition with BGE-M3 and store in a
  `gene_propositions(gene_id, prop_idx, embedding BLOB)` table; dense recall
  scores against proposition vectors and maps the hit back to the parent gene.
  This is the full Dense-X pattern; gate behind `[ingestion]
  proposition_index_enabled`.
- *LLM variant:* the Dense-X paper uses an LLM "propositionizer." helix can reuse
  `backends/compressor.py` with a propositionizer prompt as an opt-in
  `[ingestion] backend = "ollama"|"claude"` path; the CPU spaCy version is the
  default floor.

**Risk / caveat.** Propositions multiply row count (5–15× per chunk). Keep them
in a *separate* index that resolves to parent genes — do not inflate the primary
`genes` table or the assembly budget. Decontextualized propositions can also
lose nuance; the parent-gene fallback (deliver the full chunk once the prop
points at it) covers that.

---

### 2.3 Late chunking (chunked pooling)  — medium impact, near-free given BGE-M3

**What.** Normal ("naive") chunking embeds each chunk in isolation, so a chunk's
vector knows nothing about its neighbors. **Late chunking** runs the
long-context transformer over the *whole document first*, producing one
token-embedding per token *with full-document attention*, and only *then* splits
the token sequence into chunks and mean-pools each chunk's slice. Every chunk
vector is contextualized by the entire document — at no extra model cost and
with no extra stored text.

**Evidence.**
- *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding
  Models*, Günther, Mohr, Williams, Wang, Xiao (Jina AI), arXiv:2409.04701,
  Sep 2024 / rev. Jul 2025 (<https://arxiv.org/abs/2409.04701>). Across 3 models
  × 4 BeIR datasets: **+3.63% relative (1.9% absolute) nDCG@10** for
  sentence-boundary chunks, **+3.46% relative** for fixed-256-token chunks.
  Largest single gain NFCorpus fixed-256: **23.5% → 30.0% nDCG@10**. Models
  tested: jina-embeddings-v2-small, jina-embeddings-v3, nomic-embed-text-v1.
- **Critical caveat for helix:** the paper explicitly reports late chunking
  *underperforms* on the synthetic **Needle-8192 / Passkey-8192** tasks —
  "contextual augmentation becomes counterproductive with irrelevant
  surrounding content." helix's NIAH fixtures are that exact shape.

**Why it (partly) fixes this bench.** BGE-M3 is an 8192-token long-context model
— late chunking is *directly applicable* with the encoder helix already ships.
It contextualizes the one-clause-fact chunk vector toward its section for free.
But the Needle-8192 caveat means the win is real for the *natural-prose* misses
("default conductor model") and possibly *negative* for pure synthetic-needle
fixtures. Treat as a medium-confidence, A/B-gated change.

**Concrete helix mapping.**
- `backends/bgem3_codec.py` today exposes only `encode(text) -> dense`. Add
  `encode_document_late(full_text, chunk_spans) -> list[dense]`:
  1. Tokenize `full_text` once, capture the offset mapping.
  2. Forward pass → per-token last-hidden-state (FlagEmbedding's
     `output_dense=True` per-token, or sentence-transformers token embeddings).
  3. For each `(start_char, end_char)` span, mean-pool the covered token
     vectors, L2-normalize → that chunk's vector.
- `context_manager.ingest()` already has the full `content` *and* all the
  strand spans (once `RawStrand.start_offset` exists per §2.1). Call
  `encode_document_late(content, [(s.start_offset, s.start_offset+len(s.content)) for s in strands])`
  and write each result to `embedding_dense_v2` **inline at ingest** — which
  *also closes W1* (see §2.7).
- Documents longer than 8192 tokens: fall back to per-chunk naive encoding (the
  paper's "late chunking with long late chunking" handles this with overlapping
  macro-windows; a simple window split is fine for v1).
- Gate behind `[ingestion] late_chunking_enabled` (default off until the bench
  A/B confirms it nets positive on helix's fixture mix).

---

### 2.4 Hierarchical / parent-child retrieval + recursive summaries (RAPTOR)  — medium impact

**What.** Two related ideas:
- **Parent-child / small-to-big:** embed *small* units (precision) but, on a
  hit, return the *larger* parent (context). LangChain's ParentDocumentRetriever.
- **RAPTOR:** recursively cluster + LLM-summarize chunks bottom-up into a tree;
  index *every* node (leaves + summaries). A "collapsed-tree" query searches all
  levels at once, so a query naturally lands on whichever granularity answers
  it — leaf for a literal fact, summary for a global question.

**Evidence.**
- *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*,
  Sarthi et al., ICLR 2024 (<https://arxiv.org/abs/2401.18059>). +20% absolute
  accuracy on QuALITY with GPT-4; collapsed-tree querying beats layer-by-layer
  traversal — "questions often require information at varying levels of
  granularity."

**Why it fixes this bench.** Count queries are partly **aggregation** ("how many
skills does the fleet have" = count items spread across files). A leaf chunk
rarely states the total; a RAPTOR *summary node* over the fleet docs can ("The
fleet defines 12 skills..."). The collapsed-tree search surfaces the summary for
count queries and the leaf for literal facts.

**Concrete helix mapping.**
- helix **already has the parent-child skeleton** — `_upsert_parent_doc()`
  (`context_manager.py:795`) creates a file-level parent with `CHUNK_OF` edges
  (`StructuralRelation.CHUNK_OF = 100`). Two gaps:
  1. The parent's `content` is just `original_content[:1024]` — a raw prefix,
     not a *summary*. Make it a real extractive/abstractive digest
     (`CpuTagger._extract_complement` over the *whole file*, or a compressor
     call). A summarized parent is what makes a count/global query land.
  2. Parents are created per-file only. Add **one more tier** — cluster file
     parents by directory or by tag-cosine and summarize each cluster — so
     corpus-level aggregation queries ("how many skills in the *fleet*", which
     spans 6 files) have a node to hit. This is RAPTOR depth-2.
- *Retrieval side* (out of strict ingest scope but the payoff path): when a
  child gene hits, optionally promote to its `CHUNK_OF` parent for assembly —
  the "small-to-big" move. The edges already exist; retrieval just needs to walk
  them.
- Ship incrementally: (a) summarized parents first (small change to
  `_upsert_parent_doc`), (b) cluster-tier later behind `[ingestion]
  hierarchy_depth`.

**Risk / caveat.** Full RAPTOR needs LLM summarization at ingest — cost + a model
dependency on the ingest path helix currently keeps CPU-only. Mitigate: use the
existing extractive `_extract_complement` for summaries (no model), accept
slightly weaker summary nodes. GMM/UMAP clustering is heavy; tag-cosine or
directory grouping is a cheap stand-in.

---

### 2.5 BGE-M3 unified hybrid: light up the sparse + multi-vector heads  ⭐ high impact, near-zero cost

**What.** BGE-M3 is explicitly a *multi-functional* model: one forward pass
yields a **dense** vector, a **sparse lexical** weight map (learned term
weights, BM25-like but semantic — handles synonyms/morphology BM25 misses), and
**multi-vector** ColBERT-style token vectors for late-interaction reranking.
helix uses only the dense head. The sparse and multi-vector outputs are
*already computed and discarded*.

**Evidence.**
- *BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text
  Embeddings Through Self-Knowledge Distillation*, Chen, Xiao, Zhang, Luo, Lian,
  Liu, 2024 (<https://huggingface.co/BAAI/bge-m3>, arXiv:2402.03216). nDCG@10
  70.0 on MIRACL using all three modes; the model card states sparse weights
  come "without any additional cost when [you] generate dense embeddings."
- Anthropic Contextual Retrieval (§2.1): adding a sparse/BM25 signal on top of
  dense took the failure-rate cut from 35% to 49% — the sparse head is the
  single biggest *additive* signal after dense.

**Why it fixes this bench.** Literal-token needles (`11437`, `qwen3:8b`,
exact config keys) are precisely what a learned-sparse head nails and a pure
dense vector smears. helix's current sparse signal is plain FTS5 BM25 over
exact tokens — it misses morphology and synonymy. BGE-M3 sparse is a strict
upgrade on the *same vectors helix is already paying to compute*.

**Concrete helix mapping.**
- `backends/bgem3_codec.py`: `_load()` already prefers `FlagEmbedding`'s
  `BGEM3FlagModel`. Change the `encode()` call to
  `model.encode(..., return_dense=True, return_sparse=True, return_colbert_vecs=True)`
  and return all three. Add `encode_full(text) -> {dense, sparse, colbert}`.
- *Storage* (`storage/ddl.py`): add `embedding_sparse_v1 BLOB` (the
  `{token_id: weight}` map, msgpack/JSON) and optionally `embedding_colbert_v1
  BLOB` to the `genes` table, mirroring the `embedding_dense_v2` migration
  pattern already there.
- *Ingest* (`context_manager.ingest()`): write dense + sparse in the same call
  that §2.7 introduces — one encode, three columns.
- *Retrieval* (`retrieval/fusion.py` already has an RRF mode): add the BGE-M3
  sparse score as a *third* ranked list into the existing RRF fusion alongside
  dense and FTS5-BM25. The fusion plumbing exists; this is one more input list.
- The ColBERT multi-vector head is a natural **reranker** — helix's rerank stage
  (Stage 3) is "off by default"; BGE-M3 colbert late-interaction is a
  zero-extra-model way to turn it on.

**Risk / caveat.** sentence-transformers backend doesn't expose sparse — only
FlagEmbedding does. `_load()` already tries FlagEmbedding first; just make sure
the sparse path no-ops gracefully on the sentence-transformers fallback. Sparse
maps add storage (~hundreds of nonzero terms/doc) — bounded, fine.

---

### 2.6 Ingest-time normalization for code & config  — medium impact, low cost

**What.** Normalize and *enrich* content at ingest so the indexed text matches
how queries are phrased. For structured/code content: chunk on real boundaries
(helix's tree-sitter path already does this for code — good); for config files
(TOML/YAML/JSON), emit a *flattened, queryable* representation of each key path
rather than indexing raw nested syntax. Generally: expand abbreviations, attach
units, and normalize identifiers so `port`, `PORT`, `listen_port` collide.

**Evidence.**
- *Searching for Best Practices in Retrieval-Augmented Generation*, Wang et al.,
  EMNLP 2024 (<https://aclanthology.org/2024.emnlp-main.981.pdf>) — ingest
  representation choices materially move end-to-end RAG quality.
- *Chunk Twice, Embed Once* (chemistry-aware RAG), arXiv:2506.17277, 2025 —
  domain-aware segmentation + representation beats naive fixed-span on
  structured technical corpora.

**Why it fixes this bench.** Multiple misses are config facts —
"how many tokens for the ribosome decoder prompt" → `helix.toml` has
`ribosome_tokens = 3000` under `[budget]`. Raw TOML indexed as-is gives the
dense vector almost nothing to grip ("[budget]\nribosome_tokens = 3000\n..."),
and FTS5 only matches the exact token `ribosome_tokens`. A normalized fact line —
`budget.ribosome_tokens = 3000 (ribosome decoder prompt token allocation)` —
matches both the dense and lexical query.

**Concrete helix mapping.**
- helix has the raw material: `CpuTagger._extract_key_values()` already
  regex-extracts `key=value` pairs, and `_KV_PATTERNS` knows `port`, `model`,
  `version`, `timeout`. Two upgrades:
  1. For `.toml/.yaml/.json` `content_type`, replace the regex KV scan with a
     **real parser** (`tomllib`, `yaml.safe_load`, `json.loads`) and emit one
     normalized fact string per leaf key path: `section.subsection.key = value`.
     Far higher recall than the current regex, which misses nested tables.
  2. Append a human-readable gloss to each fact using the key name
     (`ribosome_tokens` → "ribosome decoder prompt token allocation") so the
     fact line carries query-style vocabulary. Feed these fact lines into both
     the embedding text and the FTS5 row (same hook as §2.1's header).
- New helper `helix_context/encoding/config_normalize.py:flatten_config(text, fmt) -> list[str]`,
  called from `tagger.pack()` when `content_type == "config"` (or the source
  extension is config-like — `cmd_ingest.py` already knows the extension).
- The `_TECH_TERMS` hard-coded dictionary in `tagger.py` is a maintenance
  liability and a recall ceiling (a domain term not in the set never becomes a
  tag). Medium-term: derive domain tags statistically (corpus TF-IDF / RAKE /
  YAKE keyword extraction) instead of matching a closed set — this is an
  ingest-time normalization that removes a hard recall cap.

**Risk / caveat.** Config parsing must soft-fail (malformed TOML mid-edit) and
fall back to the current regex path — wrap in `except Exception` per the repo's
error-handling rule.

---

### 2.7 Make BGE-M3 dense embedding happen *at ingest* (close W1)  ⭐⭐ prerequisite, highest leverage

**What.** Not a research technique — an **engineering defect fix** — but it gates
the value of §2.1, §2.3, §2.5, so it is called out separately.

helix's `embedding_dense_v2` column is populated **only** by
`scripts/backfill_bgem3_v2.py`, a manual operator sweep. `context_manager.ingest()`
attaches a 20-D SEMA vector but **never computes a BGE-M3 dense vector.**
Consequence: any corpus ingested through the normal `helix ingest` / `/ingest`
path has *no dense recall at all* until someone runs the backfill. The bench
"recall is weak" symptom is consistent with the bench genome running on
tag + FTS5-BM25 + SEMA-20D only — i.e. the strongest retriever helix has
(BGE-M3 1024-D dense) may simply be **off**.

**Evidence.** CLAUDE.md "Gotchas" states it outright: *"Stage 2 backfill: BGE-M3
dense vectors (embedding_dense_v2) are NULL until you run
scripts/backfill_bgem3_v2.py. Low retrieval rate without them."* The bench's
weak recall is the predicted symptom of that gotcha being in effect.

**Concrete helix mapping.**
- In `context_manager.ingest()`, after `cpu_tagger.pack()` produces the gene,
  lazily load the existing `_dense_codec` (the manager already has
  `self._dense_codec: BGEM3Codec | None` at `context_manager.py:418` and a
  `_dense_embedding_dim`), encode the chunk (`task="passage"`, the codec already
  bounds to 2000 chars), pack to the little-endian fp32 BLOB exactly as
  `backfill_bgem3_v2._vec_to_blob` does, and pass it through to
  `genome.upsert_doc()` so it lands in `embedding_dense_v2` on the INSERT.
- Batch per `ingest()` call: collect all strand texts, one
  `codec.encode`-batch, then upsert — same shape as the existing SEMA
  `encode_batch` at lines 687–693.
- Add `[ingestion] dense_embed_on_ingest` (default **true**); the backfill
  script stays as the one-time migration tool for pre-existing genomes.
- This single change is the cheapest, highest-leverage recall fix on the list:
  it turns on a retriever that already exists, is already configured, and is
  currently dark.

**Risk / caveat.** Adds BGE-M3 encode latency to the ingest path (~tens of ms/chunk
CPU, faster on GPU — `[hardware]` auto-detects). For bulk ingest that is the
correct trade (recall >> ingest speed) and §2.3's late-chunking encode would
do the same forward pass anyway. Keep the toggle so latency-sensitive callers
can defer to the backfill.

---

## 3. Ranked recommendations

Ranked by **expected recall lift on this bench per unit of implementation cost**.
"Cost" = code surface + new model/runtime dependency on the ingest path.

| # | Technique | Expected impact | Cost | Confidence |
|---|---|---|---|---|
| **1** | **§2.7 — BGE-M3 dense at ingest (close W1)** | **Very high** — likely turns a dark retriever back on | Low | High |
| **2** | **§2.5 — BGE-M3 sparse + multi-vector heads into RRF fusion** | **High** — best additive signal, near-zero compute | Low | High |
| **3** | **§2.1 — Contextual Chunk Headers (deterministic, no-LLM)** | **High** — directly targets the one-clause-fact miss class | Low–Med | High |
| **4** | **§2.2 — Proposition index (CPU phase 1: spaCy + proposition_fts)** | **High** — fixes granularity for count/fact needles | Medium | Med–High |
| 5 | §2.6 — Config/code ingest normalization (real parser + glossed fact lines) | Medium | Low–Med | High |
| 6 | §2.4 — Summarized parents + one cluster tier (RAPTOR-lite, extractive) | Medium — unlocks aggregation/global queries | Medium | Medium |
| 7 | §2.3 — Late chunking (BGE-M3 chunked pooling) | Low–Medium, **A/B-gated** — Needle-8192 caveat applies | Medium | Low–Med |

**Sequencing.** Do **1 → 2 → 3** first: all low-cost, all high-confidence, and
1+2 are essentially "use the BGE-M3 model helix already ships, fully." Expect
the largest jump from #1 alone if the bench genome is in fact running without
dense vectors. #3 stacks cleanly (Anthropic: dense + contextual-BM25 = 49%
failure cut). Then #4 (propositions) for the count/fact-needle long tail. #5 is
an easy parallel win on config-heavy corpora. #6 (RAPTOR-lite) needs more design
and earns its keep mainly on aggregation queries. #7 (late chunking) is last and
**must be A/B-gated** — its own paper shows it can *hurt* NIAH-style fixtures,
which is exactly what this bench is.

**Two cross-cutting enablers** (small, mechanical, unblock several rows):
- Add `start_offset: int` to `RawStrand` in `encoding/fragments.py` — needed by
  §2.1 (find enclosing heading) and §2.3 (chunk spans for late pooling).
- Replace the closed `_TECH_TERMS` set in `tagger.py` with statistical keyword
  extraction (YAKE/RAKE/TF-IDF) — removes a hard recall ceiling for §2.6 and for
  tag-based retrieval generally.

---

## 4. Sources

- Anthropic — *Introducing Contextual Retrieval*, Sep 2024. <https://www.anthropic.com/news/contextual-retrieval>
- Günther, Mohr, Williams, Wang, Xiao (Jina AI) — *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models*, arXiv:2409.04701, 2024 (rev. 2025). <https://arxiv.org/abs/2409.04701>
- Chen, Wang, Lin, Wu, Lin, Xu, Yu (Allen AI / Tencent) — *Dense X Retrieval: What Retrieval Granularity Should We Use?*, EMNLP 2024 / arXiv:2312.06648. <https://aclanthology.org/2024.emnlp-main.845/>
- Sarthi, Abdullah, Tuli, Khanna, Goldie, Manning — *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*, ICLR 2024 / arXiv:2401.18059. <https://arxiv.org/abs/2401.18059>
- Chen, Xiao, Zhang, Luo, Lian, Liu (BAAI) — *BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation*, arXiv:2402.03216, 2024. <https://huggingface.co/BAAI/bge-m3>
- Qu, Tu, Bagga, et al. (Vectara) — *Is Semantic Chunking Worth the Computational Cost?*, NAACL Findings 2025 / arXiv:2410.13070. <https://arxiv.org/abs/2410.13070>
- *Reconstructing Context: Evaluating Advanced Chunking Strategies for Retrieval-Augmented Generation*, arXiv:2504.19754, 2025. <https://arxiv.org/abs/2504.19754>
- Edge, Trinh, Cheng, Bradley, Chao, Mody, Truitt, Larson (Microsoft) — *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, arXiv:2404.16130, 2024. <https://arxiv.org/abs/2404.16130>
- Gao, Ma, Lin, Callan — *Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)*, ACL 2023. <https://arxiv.org/abs/2212.10496>
- Wang, Wang, Cao, et al. — *Searching for Best Practices in Retrieval-Augmented Generation*, EMNLP 2024. <https://aclanthology.org/2024.emnlp-main.981.pdf>
- *Chunk Twice, Embed Once: A Systematic Study of Segmentation and Representation Trade-offs in Chemistry-Aware RAG*, arXiv:2506.17277, 2025. <https://arxiv.org/html/2506.17277v1>
