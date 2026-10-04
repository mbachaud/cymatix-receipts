# Test-gamut review — what to add, what to refuse (2026-09-02)

Scope: which benchmarks and tests would actually refine cymatix-context, ranked
by decision value per hour. Method: four parallel scouts over public code and IR
benchmarks, the repo's own coverage gaps, and adoption cost, then a judge pass
that verified every load-bearing claim itself (workflow `wf_85dd16ef-f7f`).
Two of the shortlisted items were then **run** in this session, and one of them
killed a third — so this memo records outcomes, not just proposals.

Existing beds: ERB 947k (.668), EnronQA v2 85k (.856) and padded 597k (.792),
LoCoMo(+obs) (.435/.519), MULocBench 108k (.449), FinanceBench (.153).

---

## Outcomes from this session

### S1 — camelCase reachability. **RUN. KILLED.** (saves the code bed)

Two probes, no bed, no ingest, no download.

`probe_identifier_reach.py` established the mechanism on a synthetic corpus:
`unicode61` splits `get_user_by_id` into four query-matchable words and leaves
`getUserById` as one opaque token, and the extractor cannot compensate because
it lowercases before it splits. In the identifier-only regime that is a reach
collapse from 1.00 to 0.25; under shared boilerplate the camelCase gold falls
six rank positions.

`probe_casing_twin.py` then priced it on **real gold** — the 680 MULocBench
needles' gold files, with all 446,123 `snake_case` identifiers mechanically
rewritten to `camelCase` and nothing else changed:

| arm | median overlap loss | ≥30% loss | lose nothing |
|---|---:|---:|---:|
| whole gold file | 0.031 | 3.4% | 40.7% |
| best-matching 4,000-char chunk | 0.067 | 5.4% | 36.8% |

Pre-registered kill was *median < 0.10*. Both arms clear it. **Verdict: the
tokenizer is exonerated as a recall mechanism on real code.** Real files carry
comments, docstrings, strings, imports and dozens of other identifiers, so a
term one identifier's casing hides is nearly always present elsewhere in the
same chunk. The synthetic `identifier_only` regime is real but repository code
is rarely in it.

**What this buys: the ~16–20 h non-Python code bed is defunded**, and MULoc's
`.449` stands as a code-regime number rather than a snake_case best case.

### S2 — `filename_anchor`. **RUN. Defect confirmed, tests added.**

The lane with the **highest weight in the store** (4.0 vs 3.0 for `fts5` and
`tag_exact`) had no unit test anywhere. It now has 12. Two findings:

1. **Latent nondeterminism.** `filename_anchor.py:164` builds its term list as
   `list({...})` and `:170` truncates to 64, so `PYTHONHASHSEED` decides *which*
   stems are queried. Measured across four seeds: four different selections. The
   identical hazard was fixed twenty lines away in a sibling module with the
   reason spelled out (`knowledge_store.py:2186-2191`, #131). It bites only above
   64 distinct terms — a minority of ERB needles, but routine for MULoc's
   2,000-char issue bodies, which is also the bed with ~71/680 unexplained
   run-to-run jitter. Pinned as `xfail(strict=True)` so the fix announces itself.
2. **`_NOISE_STEMS` swallows the most common code filenames** — `config`, `main`,
   `utils`, `index`, `setup`, `test`, `lib`, `package`, `__init__`. Part of why
   this lane never fires on ERB at all. It also makes the module's own docstring
   wrong: `filename_stem` advertises `".../config.py" -> "config"` while the code
   returns `None`.

The one-word fix (`sorted(...)`) changes which stems long queries hit, so it
moves ranking and needs its own paired receipt. Not made here.

---

## Shortlist — what to add next

### A1. ERB Document-Recall@10 against the published BM25 row — **top pick**

The house has **never recorded an external comparator on its own primary bed**.
The ERB paper's BM25 row is Document Recall **68.4** at Recall@10, defined over
*questions carrying expected document identifiers only* — and 30 of the 500 ERB
questions carry none, so **the house's n=470 is already the paper's own basis**.
Shipped delivered `.668` at k=12 against published plain-BM25 `.684` at k=10 is a
live comparison that has never been made.

- **Kill/pass:** doc-recall@10 ≥ .684 → the funnel beats published BM25 on its
  own bench and can say so. Below → the shipped funnel is at or under plain BM25
  on ERB, which re-prices every tail-scorer proposal: the headroom is not "beat
  our own .668", it is "beat BM25's .684 while also paying compression".
- **Cost ≈ 5 h**, not "free": no existing receipt can be rolled up, because
  per-query records carry no delivered gene ids and `rank_gold` returns
  unattributed ranks. Needs ~100 LOC of ladder patch (record `delivered_gene_ids`
  and `top10_gene_ids`), the existing `erb_dsid_adapter.py` for gene→document
  rollup, and one 470-needle pass (2.8 h + 1 h cold gate).
- **Report both bases or it is uncitable:** k=10 vs 12, fraction-of-gold-docs vs
  binary any-gold, document unit vs chunk unit, ranked list vs delivered-after-
  compression.

### A2. CQADupStack — the semantic-crater falsification bed

The only free, ERB-scale corpus where the paraphrase is **a second real human
asking the same question in their own words** (gold is a human-marked duplicate
thread; 457k docs, 13,145 queries). Every current paraphrase datapoint is
synthetic: the ERB semantic class is generated under an explicit anti-lexical
instruction, and EnronQA's rephrased split is machine paraphrase.

- **Kill/pass, pre-registered:** if the human-paraphrase deficit at k=12 is ≥ the
  ERB semantic deficit (≈ −32pp relative), the crater is a genuine capability gap
  and the write-time card program is funded. If it is ≤ half, **the 61 are
  declared a benchmark artefact and the entire Q-B budget redirects to Q-A.**
  A multi-week program decision for ~12 h.
- **Cost ≈ 11–14 h**: ~1 GB download, 3.8–7.9 h ingest, ~5–6 GB disk, ~200 LOC
  adapter, ~20 min/arm ladder. Smoke on one sub-forum (~40k docs) first.
- **Caveats to state up front:** 1.4 gold/query means BEIR judgment
  incompleteness will over-report interlopers — grade delivered, never mine this
  bed for a taxonomy. Twelve sub-forums = twelve indexes; pick one convention.
  It tests *paraphrase*, not enterprise *genre*.

### A3. The builder AST fix (precondition for any future code bed)

MULocBench is **regex-chunked**, and not by choice: `build_fixture_matrix.py`
passes no `metadata`, so `source_id` is `None`, `detect_language(None)` returns
`None`, and the code path lands on the regex splitter. Corroborated on the bed —
of 4,000 sampled `.py` genes, 1,978 start with a column-0 `def `/`class ` and
only 4 with an indented one, the signature of a `^(def |class |…)` split rather
than AST method chunks.

Independently, `_EXT_TO_LANG` detects ten languages while `lang_module_map` wires
five, so Go, Java, C, C++, Ruby and Lua fall back on **every** install regardless
of installed grammars, and `.cs`/`.kt` are not detected at all. Pinned by
`test_ast_support_is_a_subset_of_extension_detection`.

So `.449` prices the regex chunker with the symbol lane dark. Fixing the builder
is ~3 h; a rebuilt bed is a **new** BASELINES row (gene ids are content-derived),
not a delta against `.449`.

---

## Do not adopt

| Candidate | Deciding reason |
|---|---|
| **SWE-PolyBench / CoIR CSN Java-vs-Python** | **Defunded by S1.** The camelCase justification is dead; adopt only if deployment realism is wanted for its own sake. |
| **RepoBench-R** | No haystack — a per-instance candidate list, so the shortlist, RRF competition and the 12-seat cut are all structurally absent. |
| **LoCoBench** | Unreproducible gold: rubric-scored generated scenarios, no per-needle gold set, so paired accounting is impossible by construction. |
| **CORE-Bench L2/L3** | 9.4M items ≈ 10× ERB; L3 gold from an unpublished annotation pipeline. |
| **MIRACL** | 50–100 h/language for a finding already established by inspection: the ASCII-only extractor returns `[]` for CJK and Cyrillic queries. Buy the unit test, not the bed. |
| **SWE-bench Multilingual** | ~33 needles/language — a 5pp delta is invisible under Wilson bounds. |
| **Multi-SWE-bench** | No in-bed control arm, so every cross-language claim must reach outside the bed, which BASELINES bars. |
| **CodeRAG-Bench** | Licence and corpus sizes unverified; primary contract is generation pass@1, which the house does not run; Python-dominant. |
| **MultiHop-RAG** | 609 documents — a 50-deep shortlist over 609 docs never binds. |
| **LegalBench-RAG** | No licence file and the corpus sits behind a Dropbox link. Re-open the day that is confirmed; it is the only character-exact instrument available. |
| **FreshStack** | Corpus is already chunked by their pipeline, so cymatix would re-chunk pre-chunked text and the granularity finding is uninterpretable. |
| **BRIGHT** | 7 separate indexes for ~101–118 queries each, and its published lift comes from LLM query expansion, which is outside the neural-free charter. |
| **A 500k-chunk code bed** | ~10 h build plus a permanent per-flip tax; the marginal information over 108k is scale crowd-out, which the EnronQA 85k→597k pair already measured. |

---

## Two rules worth imposing on anything adopted

1. **Ship the capture artefact on the first baseline.** The 28 MB
   `pool_depth_capture_2026-09-01.sqlite` (both arms' full score maps, gold flags,
   query terms) is the only reason a tail scorer can be priced offline at all. A
   bed without one cannot answer the question it was adopted for.
2. **Record the language mix and the chunker path in the BASELINES row.** After
   A3 the same corpus can be AST- or regex-chunked, and after S1 we know the
   language mix is *not* the confound it looked like — but only because it was
   measured.

## What this review does not settle

Whether the shipped funnel beats plain BM25 on its own bench (A1). Whether the
crater survives outside an anti-lexically-generated benchmark (A2). What `.449`
prices once the builder is fixed (A3). Whether `filename_anchor`'s
nondeterminism actually moved any published receipt — that needs a grep of the
wave-1, floor-curve and gate-sweep runs for a `PYTHONHASHSEED` pin; only the
`2026-08-19-sema-ingest-ab` row mentions one. And MULocBench's HF card states no
licence, which is a live compliance item on an already-published bed, not a
hypothetical.
