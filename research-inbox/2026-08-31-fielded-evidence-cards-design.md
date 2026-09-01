# Fielded evidence cards — design memo (grounded)

**Status:** research/design, not a plan. Grounds Sol's "fielded evidence cards" proposal
against the actual Cymatix retrieval code and SQLite FTS5's documented behavior
(sqlite.org/fts5.html, fetched 2026-08-31). Written for skepticism, not advocacy.

**One-line proposal recap:** replace the single flattened FTS5 `content` column with
several fielded columns (body, title/heading, source/path, entities, temporal facts,
literal claims), retrieve each as an independent leg with column filters / per-column
BM25 weights / phrase+NEAR, and fuse the legs via the existing RRF machinery.

---

## 1. Current state (exact, file:line)

### 1.1 `genes` table — what text exists per document

`cymatix_context/storage/ddl.py:59-86` (`_create_genes_table`):

```sql
CREATE TABLE IF NOT EXISTS genes (
    gene_id TEXT PRIMARY KEY, content TEXT, complement TEXT, codons TEXT,
    promoter TEXT, epigenetics TEXT, chromatin INTEGER, is_fragment INTEGER,
    embedding TEXT, source_id TEXT, repo_root TEXT, source_kind TEXT,
    observed_at REAL, mtime REAL, content_hash TEXT, volatility_class TEXT,
    authority_class TEXT, support_span TEXT, last_verified_at REAL,
    version INTEGER, supersedes TEXT, key_values TEXT, embedding_dense TEXT
)
```

Relevant fielded material that **already exists as structured data**, just not
exposed as FTS columns today:

| Field | Where | Shape | Currently fed into FTS5? |
|---|---|---|---|
| `content` | `genes.content` | body text | yes (flattened, see 1.2) |
| `complement` | `genes.complement` | extractive summary (`tagger.py:687-727`) | yes, own column |
| `source_id` | `genes.source_id` | file path / URL | yes, flattened into `content` |
| domains + entities | `promoter_index` table (`gene_id, tag_type∈{'domain','entity'}, tag_value`) | tag rows, `ddl.py:164-188` | yes, flattened into `content` via `GROUP_CONCAT` |
| **key_values** | `genes.key_values` JSON list, e.g. `["port=11437","model=gemma4:e4b"]` (`tagger.py:561-622`) | literal `key=value` facts | **no** — never appears in `genes_fts` or `genes_fts_source` at all |
| DATE-typed entities | discarded | spaCy NER extracts `DATE` spans internally but `tagger.py:449-452` only keeps `PERSON, ORG, PRODUCT, GPE, FAC, WORK_OF_ART, LAW, EVENT, LANGUAGE` — `DATE`/`TIME`/`CARDINAL` are computed by spaCy and thrown away | no |
| title / heading | **does not exist anywhere in the schema.** No field, no extraction. `_extract_intent` (`tagger.py:731-753`) produces a "first sentence / docstring line" `intent` string, which is adjacent but semantically different (used for `intent_class`, not a title) | no |

### 1.2 FTS5 table: DDL, insert path, exact composite text

External-content FTS5 table (issue #338, `ddl.py:439-447`):

```sql
CREATE VIRTUAL TABLE genes_fts USING fts5(
    gene_id, content, complement,
    content='genes_fts_source', content_rowid='rowid'
)
```

Backing view (`ddl.py:425-437`, `FTS_SOURCE_VIEW_SQL`) — this is the **exact** text
indexed:

```sql
CREATE VIEW genes_fts_source AS
SELECT g.rowid, g.gene_id,
    COALESCE(g.source_id,'') || ' ' ||
    COALESCE((SELECT GROUP_CONCAT(t.tag_value,' ') FROM (
        SELECT pi.tag_value FROM promoter_index pi
        WHERE pi.gene_id = g.gene_id ORDER BY pi.rowid) t), '')
    || ' ' || g.content AS content,
    COALESCE(g.complement,'') AS complement
FROM genes g
```

So today's "content" FTS column is already `source_id + (domains then entities,
space-joined) + body` — three of the six things the proposal wants fielded
(path, entities, body) are **already concatenated into one undifferentiated BM25
column**, and `complement` is a genuine second column that already exists but is
never queried with a column filter (see 1.3).

No `tokenize=` option is set → the table uses SQLite's default `unicode61`
tokenizer (ASCII-folding, whitespace/punctuation splitting). No `detail=` option
is set → default `detail=full` (full per-token position info is already stored
for all 3 existing columns, i.e. phrase/NEAR are already structurally possible
today — see §3).

**Insert/delete path** (`cymatix_context/storage/indexes.py`):
- `fetch_fts_source_row` (55-78) reads the *prior* `(rowid, gene_id, content, complement)` from the view **before** the caller mutates `genes`/`promoter_index` — required because an external-content table's `'delete'` must reproduce the exact old token stream.
- `fts_delete_row` (103-120) issues `INSERT INTO genes_fts(genes_fts, rowid, gene_id, content, complement) VALUES ('delete', ?, ?, ?, ?)`.
- `fts_insert_from_source` (123-137) re-reads the *new* row from the view and inserts it.
- `sync_fts5` (140-196) orchestrates delete-then-insert per upsert; the legacy (pre-#338) contentful-table branch (179-183) builds the identical composite string in Python (`tag_text = domains + entities joined`; `fts_content = f"{source_id} {tag_text} {content}"`) — kept byte-identical to the view on purpose (see the ordering-must-match comment at `ddl.py:420-424`).

### 1.3 Query construction — Tier-3 FTS5 leg

`cymatix_context/knowledge_store.py:3193-3251`:

```python
fts_query = " OR ".join(f'"{t}"' for t in query_terms if len(t) > 2)
...
SELECT gene_id, rank FROM genes_fts WHERE genes_fts MATCH ? {lifecycle filter} ORDER BY rank LIMIT ?
```

Facts worth being precise about:
- `rank` here is `bm25(genes_fts)` with **no explicit column-weight arguments**, so per SQLite's documented default ("if there are not enough arguments for all table columns, remaining columns are assigned a weight of 1.0") every column — including the near-meaningless `gene_id` column, a content hash — gets equal weight 1.0. `gene_id` essentially never matches a query token but still contributes to `avgdl`/`dl` length normalization, a small unintended dilution.
- Each term is wrapped in `"..."` (a length-1 phrase, functionally identical to a bareword for FTS5) and the terms are **OR'd**, not AND'd. There is no phrase query, no NEAR, no column filter anywhere in this leg.
- Two more call sites reuse the identical unweighted `bm25(genes_fts)` discipline: `_bm25_candidate_set` (`knowledge_store.py:2575-2596`, the BM25 pre-filter), `encoding/chunk_fetch.py:74-83`, and `retrieval/lexical_rescue.py:156-165`. **None of the four current FTS5 call sites in the codebase use a column filter, a phrase query, NEAR, or a weighted `bm25()` call.** The proposal's query-time primitives (column filter syntax, per-column `bm25()` weights, NEAR) are all unused today even though the *table* already has multiple columns.

### 1.4 Where `query_terms` (the thing fed into the MATCH clause) comes from

`cymatix_context/accel.py:179-198` (`extract_query_signals`):

```python
words = re.findall(r"[a-z0-9_/\-]+", query.lower())
keywords = [w.strip(...) for w in words if len(w) > 2 and w not in STOP_WORDS]
expanded_keywords = expand_query_terms(keywords)   # compound-split + singular/plural variants
entities = [w for w in expanded_keywords if len(w) >= 4]
domains = keywords[:5]
return domains, entities
```

`context_manager.py:2776-2779`: `query_terms = expand_terms(domains) + expand_terms(entities)`.

**This is a flat, deduplicated, order-discarding bag of stemmed/expanded tokens.**
Original adjacency ("cache invalidation" as two consecutive words) is thrown away
before Stage 1 even returns a value — a dict/list of unordered keywords has no
concept of "these two words were next to each other in the user's question." This
is the single most important grounding fact for §3 below: **there is currently no
code path that could feed a faithful phrase or NEAR query** without a new
extraction step that preserves raw-query word order.

### 1.5 RRF fusion — the part of the proposal that is *not* novel

`cymatix_context/retrieval/fusion.py` — `Fuser.add_tier(tier_name, ranked_ids, weight)`
(110-182) takes **any** `[(gene_id, raw_score), ...]` list and rank-fuses it; `k=20`
(`config.py:683`, wave-1-graduated 2026-08-28, was Cormack's 60). The codebase
already runs 9+ independently-scored tiers through exactly this pattern —
`pki` (`knowledge_store.py:3019`, `pki_weight=1.0`, `config.py:895`),
`filename_anchor` (3055-3059, weight 4.0), `tag_exact` (3167), `tag_prefix` (3190),
`fts5` (3247, `fts5_weight=3.0`, `config.py:825`), `splade` (3318),
`sema_cold` (3452-3455), `dense` (3505-3507), `sr` (3690), and more.

**Implication:** "fuse a new leg via RRF" is the *cheap, already-solved* part of
this proposal — adding a 10th `fuser.add_tier(...)` call is mechanical, follows an
established pattern, and needs only a new config weight knob (same shape as
`fts5_weight`/`pki_weight`). The proposal's genuine novelty and genuine risk are
entirely upstream, in the FTS5 schema and the query-construction code that has to
build 5 independent `MATCH` clauses.

### 1.6 A load-bearing fact the proposal's authors may not know: half of "fielded cards" already ships, just not via FTS5

- **Path/source leg** → already exists as the `pki` tier (`path_key_index`, exact-match
  join of path tokens × `key_values` key names, `knowledge_store.py:2960-3023`) and the
  `filename_anchor` tier (weight 4.0, `knowledge_store.py:3025-3059`, "filename alone
  drives retrieval lift" per its own comment).
- **Entities leg** → `entity_graph` table already exists (`ddl.py`, `entity TEXT, gene_id TEXT`,
  indexed both directions) as an exact entity→document lookup, independent of `promoter_index`.
- **Literal claims leg** → `genes.key_values` already exists, is already extracted at ingest
  (regex patterns, `tagger.py:229-259`), and is already *partially* used at retrieval time —
  but only the **key names** (via `pki`'s `path_token × kv_key` join,
  `knowledge_store.py:173-219`), never the **values** or the full `"port=11437"` literal
  string as free text. Nobody can currently ask "what's the timeout value" and get a
  BM25/phrase hit on the literal `timeout=30` text.
- **Temporal facts leg** → the closest existing signal, spaCy's `DATE` entity type, is
  computed by the NER pass inside `_extract_entities` and then **explicitly discarded**
  by the type filter at `tagger.py:449-452`.

So the proposal's real net-new surface area is much smaller than "6 fielded
columns from scratch": path/entities are duplicative of shipped tiers,
claims/temporal are a wiring + label-filter change away from data that's
already computed, and only **title** is a genuinely new extraction with no
existing analogue.

---

## 2. Proposed schema

### 2.1 One multi-column table vs. several single-purpose tables — SQLite constraints that decide this

Verified against sqlite.org/fts5.html (2026-08-31):

- **External-content column matching is by NAME, not position or count.** FTS5 issues
  `SELECT <content_rowid>, <cols> FROM <content> WHERE <content_rowid>=?` where `<cols>`
  is exactly the FTS5 table's own declared column list. The backing view/table **may have
  extra columns** FTS5 ignores; it must supply every column FTS5 declares, by name. (Cymatix's
  own `FTS_SOURCE_VIEW_SQL` already relies on this — the view's `rowid` column is extra,
  ignored by the `fts5(gene_id, content, complement, ...)` declaration.) This means a fielded
  view is straightforward to write; column *count* is not the constraint.
- **`detail` (full / column / none) is a per-TABLE option, not per-column.** `detail=column`
  and `detail=none` both **disable phrase queries and NEAR entirely for the whole table**
  (`detail=none` also disables column filters). There is no way to get "NEAR on the claims
  column, cheap detail=none on the body column" inside one FTS5 table.
- Consequence: **if any column needs phrase/NEAR (title, claims, temporal — the
  proposal's actual differentiators), the whole table pays full per-token position storage**,
  including the large `body` column, which already pays it today (current table has no
  `detail=` override, so it's already `detail=full`). This is not a new cost from fielding —
  it's the existing cost. Where fielding *does* add cost is more indexed columns × more
  postings.
- **Recommendation:** do **not** create a single 6-column monolith. Split into:
  1. **`genes_fts`** (existing table, unchanged shape: `gene_id, content, complement`) —
     keep it as the bulk-body BM25 leg, exactly as today. No migration risk added here.
  2. **`evidence_fts`** (new, small, `detail=full`): `title, path, entities, temporal, claims`
     — all short, high-signal fields, backed by a new view joining `genes` + `promoter_index`
     + (new) title/date extraction. Splitting isolates the new/risky columns from the
     large stable one, so a bad `evidence_fts` design can be dropped and rebuilt without
     touching the (already fine) `genes_fts`.
  - A trigram-tokenized third table for fuzzy path/filename substring matching is a
    plausible future idea (`tokenize="trigram"` — verified compatible with column filters
    per the fetched docs, though not documented against external-content specifically) but
    is **explicitly out of scope** for this memo: `tokenize` is also per-table, so it would
    be a third virtual table, a third write-fan-out per ingest, and a mixing of two
    different relevance semantics (word BM25 vs. trigram substring) that the current
    RRF fuser has no precedent for reconciling. Flag as scope creep if it appears in a plan.

### 2.2 Concrete DDL

```sql
CREATE VIEW IF NOT EXISTS evidence_fts_source AS
SELECT
    g.rowid AS rowid,
    g.gene_id AS gene_id,
    COALESCE(g.title, '') AS title,                    -- NEW field, see 2.3
    COALESCE(g.source_id, '') AS path,                  -- reuse existing column
    COALESCE((SELECT GROUP_CONCAT(pi.tag_value, ' ') FROM promoter_index pi
              WHERE pi.gene_id = g.gene_id AND pi.tag_type = 'entity'
              ORDER BY pi.rowid), '') AS entities,       -- reuse promoter_index, entity rows only
    COALESCE(g.temporal_facts, '') AS temporal,          -- NEW field, see 2.3
    COALESCE(g.key_values_text, '') AS claims            -- NEW derived text, see 2.3
FROM genes g;

CREATE VIRTUAL TABLE evidence_fts USING fts5(
    gene_id, title, path, entities, temporal, claims,
    content='evidence_fts_source', content_rowid='rowid'
    -- no tokenize= override -> unicode61, matching genes_fts's tokenizer
    -- (mismatched tokenizers between legs would make cross-leg NEAR/phrase
    --  comparisons meaningless, see 4.5)
);
```

Two of these five columns (`path`, `entities`) are **pure re-projections of data
`genes_fts` already indexes** — this is why §1.6 matters: shipping `evidence_fts`
with all 5 columns measures a bundle where 2/5 columns are near-certain to be
redundant with tiers that already exist (`pki`, `filename_anchor`,
`entity_graph`/`tag_exact`), diluting whatever signal the 3 genuinely new
columns (`title`, `temporal`, `claims`) contribute. See §5 for why this argues
for shipping one column at a time.

### 2.3 Ingest mapping (tagger → columns)

| Column | Source | New work required |
|---|---|---|
| `path` | `genes.source_id` (existing) | none |
| `entities` | `promoter_index` rows where `tag_type='entity'` (existing) | none — just don't merge domains in |
| `claims` | `genes.key_values` JSON list, joined to text (`"port=11437 model=gemma4:e4b ..."`) | small: a text-projection helper, no new tagger extraction (values already computed by `_extract_key_values`, `tagger.py:561-622`) |
| `temporal` | spaCy `DATE` entities from the NER pass already run inside `_extract_entities` | small: widen the label filter at `tagger.py:449-452` to also collect `ent.label_ == "DATE"` into a **separate** list (do not merge into `promoter.entities`, which feeds `entity_graph`/tag tiers and would re-introduce the redundancy this design is trying to avoid); bump `TAGGER_VERSION` (currently 2, `tagger.py:53`) since this changes tagger output and therefore the bed-content digest per the project's own tagger-version rule (`BASELINES.md`) |
| `title` | **nothing existing.** Would need new heuristics per `content_type`, e.g. first Markdown `#`/`##` line, first non-blank code-comment/docstring line, or (for chunked prose) the source document's original heading if chunk metadata carries one. Closest existing analogue is `_extract_intent` (`tagger.py:731-753`, first-sentence/docstring heuristic) but that field is semantically "intent," already consumed for `intent_class`, and repurposing it risks conflating two different signals | genuinely new tagger method + a new `genes.title` (or reuse `Document.promoter.summary`? — no, `summary` is also already a distinct, consumed field, see `tagger.py:782-800`) |

### 2.4 Migration path — is it incremental?

**No. A column-set change to an FTS5 table is not incremental in SQLite; it is
DROP + CREATE + a single `'rebuild'` command inside one transaction**, exactly the
same shape `scripts/migrate_fts5_external_content.py` already uses for the #338
contentful→external-content migration (`migrate_fts5_external_content.py:288-306`:
`BEGIN IMMEDIATE; DROP TABLE genes_fts; CREATE VIEW ...; CREATE VIRTUAL TABLE ...;
INSERT INTO genes_fts(genes_fts) VALUES ('rebuild'); COMMIT`). Since `evidence_fts`
is a brand-new table (not an ALTER of `genes_fts`), the very first build is the
same one-shot `'rebuild'` insert against the whole `genes` table — there is no
per-row incremental path in FTS5 for a table that doesn't exist yet either way.
This holds one exclusive write transaction for its entire duration; the store is
write-blocked (not necessarily read-blocked, under WAL) until it commits.

**Real receipt** (`benchmarks/dogfood/erb/receipts/fts5_external_content_migration_10k.json`,
issue #338, on a 15,888-gene / 0.82 GB bed): `rebuild_seconds: 2.85`,
`vacuum_seconds: 9.66` (VACUUM is separate, needed to reclaim the file, and per
the script's own docstring needs up to 2× the file size in free disk while it runs).

**Scaling to the current production-shape bed:** `docs/benchmarks/BASELINES.md`
records the live 947,531-gene bed (`F:/tmp/erb_blob_v09x.db`, post-PKI-drop +
FTS5-external-content-migration + vacuum) at **37,055,066,112 bytes (~34.5 GiB)**;
a sibling 829k-gene bed (`erb_829k_nosplade.db`) is 17,433,264,128 bytes (~16.2 GiB).
Naive linear extrapolation from the 10k receipt (2.85 s / 15,888 genes ≈
0.18 ms/gene for a 3-column rebuild) gives **~170 s (under 3 min)** for a
same-shape `genes_fts` rebuild at 947k rows. `evidence_fts` indexes different
(smaller-per-row: title/path/entities/temporal/claims are all short strings, no
full body) but *more numerous* columns — expect the rebuild to be in the same
1-5 minute order of magnitude, not a new order of magnitude, but this is an
estimate, not a receipt: **nobody has measured a 5-6 column external-content FTS5
rebuild at this row count in this codebase.** VACUUM afterward, scaling the
10k receipt's 9.66 s / 0.82 GB ratio to a ~34.5 GB file, is order **several
minutes**, plus the 2×-free-disk requirement — on a 34.5 GB store that's ~69 GB
of scratch space, worth stating explicitly since it's easy to trip on with large
beds.

**Incrementally, per new document going forward:** yes — once `evidence_fts`
exists, `sync_fts5`'s per-upsert delete/insert pattern (`indexes.py:140-196`)
extends the same way it does for `genes_fts` today, no rebuild needed for
steady-state ingest. The rebuild cost is a one-time (per schema change) event,
not a per-ingest one.

---

## 3. Query legs — construction and RRF plug-in points

### 3.1 Per-leg MATCH construction

Each new leg is structurally identical to the existing Tier-3 pattern
(`knowledge_store.py:3193-3251`), just column-filtered and pointed at
`evidence_fts`:

```python
# title leg
fts_query = " OR ".join(f'title:"{t}"' for t in query_terms if len(t) > 2)
cur.execute("""
    SELECT gene_id, bm25(evidence_fts, 10.0,0,0,0,0) AS rank
    FROM evidence_fts WHERE evidence_fts MATCH ? ORDER BY rank LIMIT ?
""", (fts_query, *params, depth))
```

A useful implementation trick the docs support but the codebase doesn't use yet:
because `bm25(tbl, w0, w1, ...)` accepts an explicit weight vector, **a single
`MATCH` against all 5 columns, fetched once, can be re-scored N times in Python
with N different one-hot weight vectors** to derive N independent per-column
rankings without N separate SQL round trips — cheaper than 5 fully separate
`SELECT...WHERE MATCH...ORDER BY` queries, at the cost of pulling a slightly
wider candidate set per leg (a row that matches only on `path` still needs to be
fetched to be re-scored for the `title` ranking, even though its title-only
score would be near-zero). This is a genuine design option worth costing
out, not something currently implemented anywhere — flagging it here so it
isn't independently "discovered" mid-implementation and treated as free.

### 3.2 Phrase / NEAR generation — and its failure modes

This is where the proposal is weakest relative to what the codebase actually
has available, per §1.4:

1. **No word-order signal survives Stage 1.** `extract_query_signals` (`accel.py:179-198`)
   returns an unordered, deduplicated bag; `expand_query_terms` (`accel.py:154-176`)
   adds compound-split and singular/plural variants that have no natural adjacency
   to anything. **Building a real phrase or `NEAR(a b, N)` query requires a wholly
   new extraction path that preserves the raw query's token order** — not a reuse
   of `query_terms`. This is new code, not new wiring.
2. **Stopword mismatch.** `extract_query_signals` strips its own stopword list
   before FTS5 ever sees the query; FTS5's `unicode61` tokenizer does not remove
   stopwords by default. A phrase built from the *post-stopword-strip* term list
   ("what is the port timeout" → `port timeout`) is a different phrase than the
   literal user text, and `NEAR("port timeout", 2)` will match differently than
   `NEAR("the port timeout", 2)` would over the real body text — the distance-N
   semantics silently drift from user intent.
3. **Synonym/morphology expansion breaks phrase fidelity.** `expand_query_terms`
   generates variants ("cache" → "caches", compound splits) with no textual
   adjacency; a synthesized phrase/NEAR clause built by naively pairing adjacent
   *expanded* terms can quote a synonym pair that never co-occurs in any source
   document — a specific, mechanical way to get a phrase query that structurally
   cannot match anything (0 recall on that leg), silently.
4. **NEAR on synthetic tag-concatenation columns is close to meaningless.**
   `entities` (and `temporal`, `claims`) are `GROUP_CONCAT(..., ' ')` joins of
   independently-extracted tags in insertion order, not natural language. Two
   unrelated entities that happen to be adjacent in that list (an artifact of
   `promoter_index` rowid order) will satisfy a small-N `NEAR()` even though
   they have zero real proximity relationship in the source text. `NEAR` is a
   body/title-of-natural-prose tool; applying it to `entities`/`claims` columns
   built by concatenation is very likely to manufacture false positive
   "proximity" evidence rather than surface real ones. This should be flagged
   explicitly to whoever writes the NEAR-generation rules — restrict NEAR
   generation to the `title`/`temporal`/`claims` legs only if those stay
   short/single-fact-per-entry, and never to `entities`/`path`.

### 3.3 RRF plug-in point

Exactly `Fuser.add_tier(tier_name, ranked_ids, weight)` (`retrieval/fusion.py:110-182`).
Each new leg's query returns `[(gene_id, -bm25_rank), ...]` (same sign convention
as the existing `fts5` tier, `knowledge_store.py:3238-3246`: `bm25()` is
lower-is-better, so the codebase negates it before handing scores to the fuser)
and becomes one more `fuser.add_tier("evidence_title", ranked, weight=self._evidence_title_weight)`
call, following the exact shape of the `pki` tier at `knowledge_store.py:2960-3023`.
New config knobs (`evidence_title_weight`, `evidence_claims_weight`, ...) follow
the pattern already established for `fts5_weight`/`pki_weight` (`config.py:825`,
`895`). **This part genuinely is as cheap as it looks in the proposal** — it's
the one piece that doesn't need new grounding beyond "the pattern already exists
9 times."

---

## 4. Risk register

1. **Index size growth.** The existing 3-column `genes_fts`, even in its
   *external-content* form (no duplicated body text), still occupied 7.68% of
   file size on the 10k receipt (down from 17.28% for the old contentful form —
   `fts5_external_content_migration_10k.json`). A new 5-column `evidence_fts`
   duplicates zero body bytes (external-content) but adds a full postings list
   per column per matching term, plus one `genes_fts_docsize` integer per
   column per row. At 947k rows × 5 columns that's ~4.7M new docsize entries
   alone, before postings. No receipt exists yet for this shape — treat any
   pre-implementation size estimate as a guess, and get a real number from a
   `evidence_fts`-only build on a 10-50k slice before trusting a 947k-scale
   projection.
2. **Ingest-time cost.** `sync_fts5`'s per-document write (`indexes.py:140-196`)
   grows from a 3-column external-content insert to a 6-column one (`genes_fts`
   stays 3-col; `evidence_fts` adds a second, separate insert). Two virtual-table
   writes per upsert instead of one is a real, measurable per-ingest overhead —
   this project has already hit multi-writer/latency ceilings before (see the
   2026-08 perf campaign and the EnronQA ingest-decay investigation) and any new
   per-row write fan-out needs its own before/after ingest-throughput receipt,
   not an assumption that "it's just another column."
3. **External-content trigger complexity is not hypothetical — it's already a
   documented sharp edge.** SQLite does not auto-generate delete/insert triggers
   for a *view*-backed external-content table (only for a real backing table);
   Cymatix hand-rolls the capture-prior-row → mutate → insert-new-row sequence
   specifically because of this (`indexes.py:160-169` docstring; the tag
   insertion-order comment at `ddl.py:420-424` is a scar from getting this
   subtly wrong once already). A 5-column `evidence_fts` sourced from `genes` +
   `promoter_index` + two new derived fields means **more values that must be
   captured before every mutation** — forgetting to snapshot `key_values`/title
   text before an upsert overwrites it silently corrupts the delete-time token
   stream, leaving orphaned postings that are only caught later by the
   orphan-ratio drift check (`ddl.py:521-539`) or a full rebuild. More columns
   is directly proportional to more ways to get this ordering wrong.
4. **Query-time latency.** Today's Tier-3 is one `MATCH` + one lifecycle-filter
   join (`knowledge_store.py:3193-3251`), already timed via `_sig("fts5", ...)`.
   A naive 5-leg implementation is 5 more `MATCH` round trips per turn on top of
   the 9+ tiers already running (`pki`, `filename_anchor`, `tag_exact`,
   `tag_prefix`, `fts5`, `splade`, `sema_cold`, `dense`, `sr`). The one-`MATCH`-
   many-`bm25()`-rescores trick in §3.1 can collapse this to 1 extra round trip,
   but that is an unimplemented optimization, not the naive baseline — cost the
   naive version first since that's what a first PR will actually ship.
5. **Tokenizer mismatch.** Current tables use the SQLite default (`unicode61`,
   no explicit `tokenize=`). The proposal materials ask specifically about the
   trigram tokenizer; per the fetched docs, trigram is a *substring-matching*
   tool (fixed 3-character n-grams, sub-3-character query terms match nothing,
   and IDF is computed over trigram frequency, not word frequency — a
   different relevance signal, not a drop-in replacement for word BM25). `tokenize`
   is per-table, so mixing trigram (for fuzzy path/filename matching) into the
   same table as word-level phrase/NEAR columns is not possible; it would need
   a third virtual table. Recommend keeping `evidence_fts` on `unicode61` (same
   tokenizer as `genes_fts`) for this round and treating trigram-for-paths as an
   explicitly separate, later proposal — mixing them now conflates two
   unrelated risk profiles in one measurement.
6. **What could make this a null result — grounded in this project's own recent
   track record, not a generic caveat.** Every recent *new retrieval leg*
   experiment in this exact codebase has come back null-to-negative under an
   isolation receipt: dense embeddings (`dense_embedding_enabled`, default OFF
   since 2026-08-15 — four-scale isolation receipts measured dense *displacing*
   gold from the delivered top-k at every scale, −0.20..−0.33 final recall);
   SPLADE (`splade_enabled`, default OFF since 2026-08-16 — n=469 receipt,
   null-to-negative over the full expansion index); the W2.1 COVER-walk
   experiment (killed by receipt, PR #408 — "mass->hubs not gold"). That's
   0-for-3 on the last three "add an independently-ranked leg and RRF-fuse it"
   experiments graduating to a shipped default. Fielded evidence cards is
   architecturally the same shape (new leg → independent ranking → RRF fusion),
   so treat "this measures null" as the base-rate-favored outcome, not the
   surprising one. Specific mechanisms that would produce a null result here:
   - `path`/`entities` legs measure ~0 unique-recall lift because `pki` and
     `filename_anchor` (already shipped, already weighted) already capture that
     signal via exact-match rather than BM25 — the new leg would be redundant,
     not additive (§1.6).
   - `claims`/`temporal` legs are populated from thin per-document text
     (`key_values` capped at 15 entries / 200 chars each, `tagger.py:622`; DATE
     entities are likely sparse per chunk) — too little indexed text per
     document for BM25's document-frequency statistics to differentiate well
     at 947k-document corpus scale.
   - At `rrf_k=20` with 9+ already-competing tiers, a new tier's rank-1
     contribution is `weight/(20+1) ≈ 0.048·weight` — small relative to
     already-tuned tiers unless its weight is set disproportionately high,
     and this codebase has already hit the failure mode of an overweighted
     lexical tier "drowning out tag matches" once (`fts5_weight` cap history,
     `knowledge_store.py:3236`, "was 15*3=45 — drowned out tag matches at 3-9").

---

## 5. Effort estimate — smallest measurable cell first

The point of staging is to avoid measuring a 5-column bundle where 2 columns
are near-certainly redundant (§1.6) and diluting whatever the other 3 contribute.
Each stage below is independently measurable via an isolation receipt (this
project's own established methodology — see the dense/SPLADE/COVER-walk
citations above).

**Stage 0 — claims leg on the existing table (smallest possible, no new table).**
Add a 4th column to the *existing* `genes_fts`/`FTS_SOURCE_VIEW_SQL`
(`ddl.py:425-447`) sourced from `genes.key_values` joined to text. Zero new
tagger extraction (the values are already computed, `tagger.py:561-622`), zero
new table, one already-receipted rebuild pattern (§2.4), one new Tier-3.5 leg
following the exact shape of `knowledge_store.py:3193-3251` restricted to
`claims:`, one new `fuser.add_tier` call, one new weight knob. This tests
whether literal-value BM25 matching (not just `pki`'s key-name × path
co-occurrence) adds anything at all — the cleanest possible test of "does a new
fielded leg help" with the least new code and the least redundancy risk.

**Stage 1 — title/path column alone, as a *new small table* (`evidence_fts` with
just `title`, `path`).** This is the cell the task brief explicitly asked to
consider "before the full card design." Caveat from §1.6: `path` is very likely
redundant with `pki`/`filename_anchor` — expect this cell's honest contribution
to come almost entirely from `title`, which requires new extraction work
(§2.3) with no existing analogue. Worth running specifically to get a
receipted answer to "does title add lift once path's redundancy is accounted
for," not to validate path.

**Stage 2 — temporal facts.** Requires the `tagger.py:449-452` label-filter
widen (cheap, but bumps `TAGGER_VERSION` and therefore invalidates cross-bed
comparability per `BASELINES.md`'s tagger-version rule — budget a full re-ingest
of the comparison bed, not an in-place ALTER). Add as a column to the Stage-1
`evidence_fts` table once title/path have an independent isolation receipt.

**Stage 3 — entities column in `evidence_fts`, only if Stage 1/2 show the small
table's overhead (§4.1-4.3) is acceptable.** Expect near-zero unique lift over
`entity_graph`/`tag_exact` per §1.6 — this stage exists mainly to confirm that
expectation with a receipt, not because it's likely to graduate.

**Stage 4 — phrase/NEAR generation.** Gate behind Stages 0-3 landing with
non-null receipts; per §3.2 this is genuinely new extraction code (raw-query
order preservation), not a wiring exercise, and its failure modes are specific
enough (synthetic-column NEAR, synonym-expansion phrase drift) that it should
be scoped and receipted as its own unit, never bundled with the column-adding
stages above.

Do not attempt the full 6-column `evidence_fts` + phrase/NEAR design as a
single PR — every prior expansion-tier effort in this codebase that shipped as
one bundle made it harder to attribute a null or negative result to the
specific column/mechanism responsible.

---

**Sources consulted:** `cymatix_context/knowledge_store.py`,
`cymatix_context/storage/ddl.py`, `cymatix_context/storage/indexes.py`,
`cymatix_context/tagger.py`, `cymatix_context/accel.py`,
`cymatix_context/context_manager.py`, `cymatix_context/retrieval/fusion.py`,
`cymatix_context/encoding/chunk_fetch.py`, `cymatix_context/retrieval/lexical_rescue.py`,
`cymatix_context/config.py`, `cymatix_context/schemas.py`,
`scripts/migrate_fts5_external_content.py`,
`benchmarks/dogfood/erb/receipts/fts5_external_content_migration_10k.json`,
`docs/benchmarks/BASELINES.md`; sqlite.org/fts5.html (fetched 2026-08-31, three
targeted queries: column-filter/bm25/NEAR/phrase/trigram/external-content
syntax; external-content column-matching semantics; `detail=`/`columnsize=`
option interaction with phrase/NEAR).
