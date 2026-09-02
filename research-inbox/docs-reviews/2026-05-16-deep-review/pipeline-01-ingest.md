# Deep Review — Ingest Half of the Pipeline

**Scope:** Where accuracy loss *originates* at ingest, before retrieval runs.
Traced: `codons.py` → `encoding/fragments.py` (chunker), `encoding/tree_chunker.py`,
`tagger.py` (CpuTagger), `encoding/legibility.py`, `storage/ddl.py` + `storage/indexes.py`,
`knowledge_store.upsert_doc` / `apply_density_gate`, and the bench fixture builder
`scripts/build_fixture_matrix.py`.

**Bench grounding:** `benchmarks/results/claude_matrix_20260515T225605Z/`. Clean
sharded signal = `medium-sharded.jsonl` (gold_delivered 25/50 = 0.50). All blob
fixtures sit at 0.30–0.34 gold-delivered. Every claim below is reproduced with a
runnable snippet against current source.

**Verdict:** Three of the top-4 retrieval failures are *pre-ordained at ingest*.
Config/data files (`.toml`, `.json`, `.yaml`) — which carry the answer for a large
fraction of NIAH needles — are systematically chunked wrong, under-tagged, and have
their key facts dropped by hard caps. Dense recall (BGE-M3) is dead in every fixture.

---

## P0-1 — Chunker hard-cuts only ONCE; oversized files become one giant strand

**File:** `helix_context/encoding/fragments.py:176-216` (`_chunk_code` regex path),
`fragments.py:86-129` (`_chunk_text`).

Both the text and code chunkers handle an oversized block like this:

```python
if len(block) >= self.max_chars:
    strands.append(RawStrand(content=block[: self.max_chars], is_fragment=True, ...))
    seq += 1
    current = block[self.max_chars :]   # <-- whole remainder kept, NO loop
else:
    current = block
```

There is no `while len(remaining) >= max_chars` loop. The block is cut **exactly
once**; everything past the first 4000 chars becomes a single `current` that is
emitted as the final strand — at *any* size.

Contrast `tree_chunker.chunk_code_ast` (`tree_chunker.py:295-303`), which does it
correctly:

```python
while len(remaining) >= max_chars:
    merged.append((remaining[:max_chars], True))
    remaining = remaining[max_chars:]
```

So AST-parseable source (`.py/.rs/.js/.ts`) is chunked fine, but everything routed
to the regex fallback is not. The regex fallback fires whenever the file has **no
`def/class/async def/struct/interface/type/export` boundary token** — i.e. every
`.toml`, `.json`, `.yaml`, `.ini`, `.cfg`, `.sql`, plus prose with no `\n\n`.

**Proven:**

```
$ python -c "from helix_context.codons import CodonChunker; \
  toml='\n'.join(f'key_{i} = {i}' for i in range(1300)); \
  print(len(toml), [len(s.content) for s in CodonChunker().chunk(toml,'code')])"
18579  [4000, 14579]          # expected ~5 chunks of ~4000
```

`helix.toml` (28 809 chars) → **2 strands: 4000 + 24808**. A 24 808-char strand is
6× the intended size.

**Impact on retrieval (bench-confirmed):**
- The answer `port = 11437` lives at char 9121 of `helix.toml` → inside strand 1
  (the 24 808-char monster). That strand's tags/embedding are an average over 24k
  chars of unrelated `[section]` config, so it never ranks for "what port".
  `helix_port` gold-delivered = **false** in `medium`, `small`, `xl`.
- `helix_ribosome_budget` (expected `3000`): gold `helix.toml`, delivered set is
  100% `.py`/`.md` — see `medium-sharded.jsonl`.
- Same root cause for every `fleet.toml` / `bookkeeper.toml` needle
  (`biged_max_workers`, `biged_thermal_target`, `biged_complex_model`,
  `bookkeeper_ocr_confidence`, `bookkeeper_backup_interval`).

**Fix:** wrap the hard-cut in a `while` loop, matching `tree_chunker`. ~3 lines in
each of `_chunk_code` and `_chunk_text`. Highest-ROI single change in ingest.

---

## P0-2 — `_extract_key_values` reads only `content[:5000]`; facts past the cap vanish

**File:** `helix_context/tagger.py:409` and `:439` — both KV regex loops slice
`content[:5000]`.

Because of P0-1, oversized config files arrive as one ~25k-char strand. The KV
extractor — the producer of the data that feeds the `path_key_index` retrieval
layer (`storage/indexes.py:110-131`, designed specifically to answer
"what is the value of helix_port") — only sees the first 5000 chars of it.

**Proven against the real file:**

```
$ python -c "from helix_context.codons import CodonChunker; \
  from helix_context.tagger import CpuTagger; \
  txt=open('helix.toml').read(); s=CodonChunker().chunk(txt,'code'); \
  g=CpuTagger().pack(s[1].content,'code','...helix.toml',1); \
  print('11437 offset in strand:', s[1].content.find('11437')); \
  print('in KV:', any('11437' in kv for kv in g.key_values))"
11437 offset in strand: 5121
in KV: False
```

`port = 11437` sits at offset **5121** within strand 1 — **121 chars past the
5000 cap**. It is never extracted, so `path_key_index` has no `(helix, port)`
row. The needle the index was built for cannot be answered by the index.

`ribosome_tokens=3000` / `expression_tokens=7000` happen to land at offsets 53/316
inside strand 1, so they *are* extracted — but the chunk is still 24 808 chars, so
P0-1's dilution defeats them anyway.

**Fix:** P0-1 (right-sized chunks) makes the 5000 cap mostly moot, since a 4000-char
chunk fits entirely. If the cap is kept as a spaCy-cost guard, raise it to
`max_chars` (4000) so it never truncates *within* a single chunk, or apply it to the
raw file before chunking, not per-strand.

---

## P0-3 — JSON config files extract ZERO key_values (regex assumes `key = value`)

**File:** `helix_context/tagger.py:129-150` (`_KV_PATTERNS`, `_KV_PAIR_PATTERN`).

Every KV pattern matches `key` followed by `\s*[=:]`. JSON syntax is
`"key": value` — there is a closing quote *between* the key name and the colon, so
`\s*[=:]` cannot match.

**Proven:**

```
$ python -c "from helix_context.tagger import CpuTagger; \
  pj='{\"name\":\"mek\",\"version\":\"2.4.1\"}'; \
  print(CpuTagger().pack(pj,'code','...package.json',0).key_values)"
[]
```

`package.json`, `tsconfig.json`, `marketplace.json`, `composer.json`, etc. produce
**no key_values at all**. `.json` is in `CODE_EXTS` (`build_fixture_matrix.py:101`),
so it is treated as code and gets nothing from the code-identifier path either
(JSON has no `def/class`).

**Bench-confirmed:** `mek_version` (expected `0.1.3`) — gold is
`MaxExpressKit/package.json` + `marketplace.json`. Gold-delivered = false, score
−1. The version literal exists only in FTS full-text, not in any KV/promoter index.

**Fix:** add a JSON-aware KV pattern (`"(\w+)"\s*:\s*"?([^",}]+)`), or detect
`content_type` from extension and parse `.json` with `json.loads` for a structured
key path walk. TOML/YAML scalars work today; JSON is the gap.

---

## P0-4 — BGE-M3 dense recall is dead in every bench fixture (and after every plain ingest)

**Files:** `storage/ddl.py:113` declares `embedding_dense_v2 BLOB`;
`knowledge_store.upsert_doc:1079-1113` is the *only* writer of the `genes` row and
its 24-column INSERT **does not include `embedding_dense` or `embedding_dense_v2`**.
The columns are populated *exclusively* by `scripts/backfill_bgem3_v2.py`
(confirmed: grep for `embedding_dense_v2` finds writes only in that script).

`build_fixture_matrix.py` builds every fixture by calling
`genome.upsert_doc(gene, ...)` directly (`:303`, `:521`) and **never runs the
backfill**. Therefore every frozen fixture has `embedding_dense_v2 = NULL` for all
rows.

`query_docs_dense_recall` (`knowledge_store.py:2487-2495`) detects the empty column
and returns `[]`:

```python
matrix, ids = self._ensure_dense_matrix()
if matrix is None or ids is None:
    log.warning("embedding_dense_v2 coverage is empty; dense recall disabled. "
                "Run scripts/backfill_bgem3_v2.py ...")
    return []
```

So **Stage 2 of the advertised 7-stage pipeline ("BGE-M3 dense recall") contributes
nothing** in the entire 50-needle matrix. Retrieval is lexical-only (tags + FTS +
SPLADE). `CLAUDE.md`'s own Gotchas section admits this ("Low retrieval rate without
them") — but the bench harness ships the broken state as the headline result.

This is partly a *bench-methodology* defect (fixtures should be backfilled) and
partly an *ingest-architecture* defect (a first-class retrieval signal requires a
separate manual sweep that no normal ingest path triggers).

**Fix options:** (a) call BGE-M3 encoding inside `upsert_doc` (or the ingest batch
drain) like SPLADE already is; (b) at minimum, add a backfill step to
`build_fixture_matrix.build_profile` so bench numbers reflect the real pipeline.
Until then, every retrieval number in `summary.json` understates a
dense-recall-enabled system.

---

## P1-1 — `content_type` for data files is mislabeled "code", routing them to the wrong chunker AND tagger branch

**File:** `scripts/build_fixture_matrix.py:101-105` puts `.json .yaml .yml .toml`
in `CODE_EXTS`; `:175` sets `ct = "code"` for them.

Consequences cascade through the tagger:
- `tagger._extract_codons` (`tagger.py:472-495`) takes the **code branch** for
  `.toml`: it regex-scans for `def|class|...` (none in TOML) and for
  `^(\w+)\s*[=:]` assignments. For TOML this yields the bare key names
  (`port`, `model`, …) as "fragments" — acceptable — but for JSON it yields
  nothing.
- `tagger._extract_intent` (`tagger.py:567-589`) takes the code branch and looks
  for a `"""docstring"""`; a TOML/JSON file has none, so intent falls back to the
  first "sentence" of a config file (a comment or `[section]` line) — low-value.
- `_chunk_code` regex path is the one with the P0-1 single-cut bug.

A dedicated `content_type="config"` (or routing `.toml/.json/.yaml` to a
structured chunker that cuts on `[section]` / top-level JSON keys) would fix
chunking *and* give the tagger a sane branch. Today config files get the worst of
both the code and text paths.

---

## P1-2 — Key-value regex mis-parses model strings into noise (`gemma4:7b` → `gemma4=7`)

**File:** `tagger.py:147-150` (`_KV_PAIR_PATTERN`).

The generic pair pattern `(\w+(?:_\w+)*)\s*[=:]\s*["\']?(\d+...|[a-zA-Z0-9._:/-]+)`
matches a prose/value token like `gemma4:7b` as key=`gemma4`, value=`7` when the
high-confidence `model=` named pattern does not fire (e.g. the value appears in
prose, not after a literal `model` key).

**Proven:**

```
$ python -c "from helix_context.tagger import CpuTagger; \
  md='The default conductor model is gemma4:7b for orchestration.'; \
  print(CpuTagger().pack(md,'text',None,0).key_values)"
['gemma4=7']
```

`gemma4=7` is wrong on both sides (truncated value, key is a product name). It
pollutes `key_values` and the `path_key_index`. Also seen: the version pattern
`(?:\.[\d]+)?` making the patch component optional emits **both** `version=2.4.1`
*and* `version=2.4` for `pyproject.toml` (duplicate/wrong fact).

**Fix:** require word boundaries / anchor the pair pattern to line starts for
config-like input; make the version patch component non-optional or capture greedily
to end-of-token.

---

## P1-3 — Numeric facts in prose are never captured as key_values

**File:** `tagger.py:_extract_key_values` — all patterns need `key [=:] value`
*syntax*.

NIAH needles are overwhelmingly "how many X" / "what is the threshold for Y". When
the answer is stated in prose ("the BigEd fleet ships **125 skills**", "audit
coverage spans **12 dimensions**"), no KV is produced:

```
$ python -c "from helix_context.tagger import CpuTagger; \
  md='The BigEd fleet ships 125 skills. Audit coverage spans 12 dimensions.'; \
  g=CpuTagger().pack(md,'text',None,0); print('KV:',g.key_values)"
KV: []
```

The number survives only as a spaCy noun-chunk `codon` (`'125 skills'`) and in the
full-text FTS column. So prose-stated facts depend entirely on FTS/dense recall —
and dense is dead (P0-4). `biged_skills_count`, `biged_audit_dimensions`,
`biged_db_tables`, `biged_core_agents` all miss gold in `medium-sharded`.

**Fix (heuristic):** add a "quantity claim" extractor — `(\d+)\s+([a-z_]{3,})`
near an entity, or noun-chunk + leading-cardinal detection — and emit a soft KV
(`skills~125`) so the structured index has something. This is the single biggest
*tagging* gap for NIAH-style factual recall.

---

## P2-1 — spaCy sentence segmentation glues markdown headers to body text

**File:** `tagger.py:_extract_codons` text branch (`:499`), `_extract_intent`
(`:583`), `_extract_complement` (`:530`), `_extract_summary` (`:624`) all iterate
`doc.sents` / `doc.noun_chunks`.

spaCy's `en_core_web_sm` does not treat a markdown `#`-header line as a sentence
boundary. The first noun chunk of a doc comes out as e.g.
`'BigEd Fleet\n\nThe BigEd fleet'` (header + first sentence fused). This corrupts
the first `codon`, the `intent`, and the `summary` — all per-document promoter
fields used for tag-based recall and legibility headers.

**Fix:** strip/normalize markdown structure (headers, list bullets, code fences)
before `nlp()`, or add a custom sentence-boundary component that splits on `\n`.

---

## P2-2 — Hard truncation caps in the tagger silently drop the tail of large strands

**File:** `tagger.py` — multiple un-equal caps applied to the *same* strand:
- `pack`: spaCy runs on `content[:50_000]` (`:223`)
- `_extract_domains`: scans `content[:20_000]` (`:317`)
- `_extract_entities` CamelCase scan: `content[:10_000]` (`:300`)
- `_extract_codons` code branch: `content[:20_000]` / `content[:10_000]` (`:477`, `:485`)
- `_extract_key_values`: `content[:5000]` (P0-2)
- `_extract_intent`: `content[:2000]` (`:574`)

For a normal 4000-char strand none of these bite. But because of P0-1, oversized
strands (24k chars) are real, and their tail beyond each cap is invisible to that
extractor. The caps are also *inconsistent* — a fact at char 12 000 is seen by
domain extraction but not entity extraction, producing partial, position-dependent
tagging.

**Fix:** once P0-1 caps strand size at `max_chars`, set every tagger cap `>=
max_chars` (or remove them) so a strand is always processed whole. The caps exist
only because oversized strands exist.

---

## P2-3 — `is_fragment` is set on the clean prefix of a 2-way split

**File:** `fragments.py:106-116` / `:194-204`.

When a block exceeds `max_chars`, the **first** 4000-char slice is emitted with
`is_fragment=True`, even though that prefix is a clean cut and the *remainder*
(which is the actually-truncated piece) is emitted with `is_fragment=False`. The
flag is inverted relative to intent.

`is_fragment` flows into `provenance.infer_support_span` (`provenance.py:301-305`,
tags the chunk `chunk:N:fragment`) and the compressor's `[fragment]` note
(`backends/compressor.py:722`). Net effect: mild — a misleading provenance label,
not a recall loss. Worth fixing alongside P0-1 since the same lines change.

---

## P3 — Minor / lower-confidence observations

- **`make_gene_id` is content-only** (`knowledge_store.py:996-998`,
  `sha256(content)[:16]`). Two different files containing an identical chunk
  (common for boilerplate license headers, `__init__.py`, repeated config blocks)
  collide to one `gene_id`; `INSERT OR REPLACE` keeps only the last `source_id`.
  Provenance for the answer doc can be silently overwritten by an unrelated file.
  Consider hashing `source_id + sequence_index + content`.
- **Density gate can demote a sparse-but-correct config chunk to
  HETEROCHROMATIN.** `compute_density_score` (`knowledge_store.py:3447-3479`) is
  `tag_density*0.4 + kv_density*0.3 + ...`; threshold `<0.50` → heterochromatin
  (`:286`). A short config chunk that *is* the answer but has few tags scores low.
  Heterochromatin is excluded from hot-tier retrieval (`WHERE chromatin < 2`).
  After P0-3/P1-3 raise real KV/tag counts this is less likely, but the gate is a
  second, independent way an answer chunk becomes unreachable at ingest. Not yet
  bench-isolated — flagged for the retrieval-side review.
- **FTS5 content is assembled twice with slightly different code paths**
  (`ddl.py:333-343` bulk sync vs `storage/indexes.py:55-78` per-doc) — currently
  equivalent (`source_id + tags + content`), but a latent drift risk; consolidate.
- **`MIN_FILE_SIZE = 50` / `MAX_FILE_SIZE = 200_000`** (`build_fixture_matrix.py:133`)
  — silently skips any gold file outside that range. None of the current needles'
  gold appears affected, but a >200 KB doc would be invisible with no log of which
  needle lost its gold.

---

## Priority Summary

| # | Finding | Origin | Bench evidence | Fix size |
|---|---------|--------|----------------|----------|
| P0-1 | Chunker hard-cuts once → 25k-char strands | `fragments.py:176-216`, `:86-129` | `helix.toml` → 2 strands; `helix_port`/`helix_ribosome_budget` miss | ~3 lines ×2 |
| P0-2 | KV extractor caps at `content[:5000]` | `tagger.py:409,439` | `11437` at offset 5121 — never in KV | 1 line |
| P0-3 | JSON files → zero key_values | `tagger.py:129-150` | `mek_version` miss, score −1 | small |
| P0-4 | BGE-M3 dense recall dead in all fixtures | `upsert_doc:1079`, no backfill in builder | Stage 2 contributes 0 across 50 needles | medium |
| P1-1 | `.toml/.json/.yaml` mislabeled `content_type=code` | `build_fixture_matrix.py:101-105` | routes to buggy chunker + wrong tagger branch | medium |
| P1-2 | KV regex emits noise (`gemma4=7`, dup `version=2.4`) | `tagger.py:147-150` | reproduced | small |
| P1-3 | Prose numeric facts never become KV | `tagger.py:_extract_key_values` | `biged_skills_count` + 3 more miss | medium |
| P2-1 | spaCy fuses markdown headers into first sentence | `tagger.py:499,583` | reproduced | small |
| P2-2 | Inconsistent tagger truncation caps | `tagger.py` (6 caps) | tail of 25k strands under-tagged | trivial after P0-1 |
| P2-3 | `is_fragment` set on clean prefix, not remainder | `fragments.py:106,194` | provenance mislabel only | trivial |

**The single highest-leverage fix is P0-1.** It directly causes P0-2's truncation
to bite, P2-2's cap inconsistency to matter, and is the mechanism behind every
`.toml`-gold miss in the bench. Pair it with P0-3 (JSON KV) and P1-3 (prose-number
KV) and the bulk of the config/data-file needle failures should clear — independent
of any retrieval-side change.
