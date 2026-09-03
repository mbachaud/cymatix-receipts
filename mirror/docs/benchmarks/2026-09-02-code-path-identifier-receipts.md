# The code path — two receipts nobody had (2026-09-02)

Bed-free, seconds to run, and they bound every code corpus the project will ever
ingest. Both were prompted by a suspicion the receipts carried but never
measured: *"unicode61 never splits camelCase; MULocBench .449 silently benefits
from Python snake_case; zero non-Python code receipts exist."*

Receipts: `benchmarks/dogfood/code/receipts/identifier_reach_2026-09-02.json`
(+ its `_prereg`). Tests: `tests/test_identifier_tokenization.py` (16),
`tests/test_code_ingest_path.py` (37). Probe:
`benchmarks/dogfood/code/probe_identifier_reach.py`.

---

## 1. What camelCase costs

**Substrate fact, measured from FTS5's own vocabulary table, not reimplemented:**

| identifier | index tokens |
|---|---|
| `get_user_by_id`, `get-user-by-id`, `user.get.by.id`, `GET_USER_BY_ID`, `get/user/by/id` | `by`, `get`, `id`, `user` |
| `getUserById`, `GetUserById`, `GetUserByID` | `getuserbyid` |

`genes_fts` declares no `tokenize=` (`storage/ddl.py:440-447`), so FTS5 uses
`unicode61`: it splits on every non-alphanumeric character and lowercases, and
it does not split camelCase. The query extractor cannot compensate — it
lowercases *before* it splits (`accel.py:186`), and `expand_query_terms` splits
only on `_`, `-` and `/`. Case information is gone before any splitting happens
on either side.

**What that costs depends entirely on whether prose is present.** The first
version of this probe measured reach on realistic, well-commented functions and
came back with 1.0 for both naming families — which is a real result, and it
relocated the question. Three arms separate what the comment was hiding:

| arm | what it models | NL reach: separator convs | NL reach: camel/Pascal | NL mean rank: separator | camel |
|---|---|---:|---:|---:|---:|
| `prose_rich` | well-commented library code | 1.00 | 1.00 | 7.0 | 11.25 |
| `identifier_only` | minified/dense code, symbol tables, generated bindings, config keys | **1.00** | **0.25** | 6.83 | 9.0 |
| `prose_shared` | a family of functions sharing boilerplate — the common real case | 1.00 | 1.00 | **5.83** | **11.83** |

Read it as three findings:

1. **With a natural comment, camelCase costs nothing for reach.** English prose
   carries the chunk. This is why the effect is invisible on well-commented
   corpora and why it has gone unmeasured.
2. **Without prose, a natural-language query reaches snake_case 100% of the time
   and camelCase 25%.** The identifier is the only evidence and it shares no
   term with the query.
3. **When siblings share the boilerplate — the case that actually decides
   delivery — the identifier is the only discriminator, and the camelCase gold
   falls six positions** (5.83 → 11.83). This is the house's own M1 mechanism
   (winners speak the query's vocabulary) reproduced at the tokenizer level.

The failure is asymmetric: a *pasted* identifier query (`getUserById`) matches
its camelCase definition fine, because both sides collapse to the same token.
Only the natural-language direction is broken — which is exactly the direction
CodeSearchNet-style benchmarks query in.

### The consequence I expected — and the measurement that killed it

The obvious reading of the above is that MULocBench's `.449` is partly a
snake_case subsidy and that a Java / Go / C# corpus inherits a gap no ranking
change can reach. **That reading is wrong, and a second probe on real code kills
it.** Recording it because the synthetic result invited exactly this inference.

`benchmarks/dogfood/code/probe_casing_twin.py` takes the gold files of the 680
MULocBench needles (45 repos on disk), rewrites every `snake_case` identifier to
`camelCase` — 446,123 of them — and re-measures query-term overlap. The bytes,
the prose, the comments, the structure and the query are all held constant; only
the casing convention moves, which removes the corpus confound that any
cross-language bed comparison carries.

| arm | median overlap loss | needles losing ≥30% | needles losing nothing |
|---|---:|---:|---:|
| whole gold file | **0.031** | 3.4% | 40.7% |
| best-matching 4,000-char chunk (the unit retrieval delivers) | **0.067** | 5.4% | 36.8% |

Pre-registered kill line was *median loss < 0.10*. Both arms clear it.
Verdict: **KILLED** (`benchmarks/dogfood/code/receipts/casing_twin_2026-09-02.json`).

**Why the mechanism is real and the cost is not.** Real source files are not in
the identifier-only regime. They carry comments, docstrings, string literals,
error messages, imports and dozens of other identifiers, so a query term the
camelCase spelling hides is almost always present somewhere else in the same
file — and, at 6.7% median loss, usually in the same 4,000-char chunk. The
synthetic probe's `identifier_only` arm (reach 1.00 → 0.25) is a real regime, but
repository code is rarely in it.

**What this buys.** A non-Python code bed can no longer be justified *on
tokenizer grounds*: the ~16–20 h build and its recurring per-flip cost are saved
unless some other reason funds them. It also means the shipped `.449` is not
meaningfully inflated by Python's naming convention, so it stands as a code-regime
number rather than a best case.

**What it does not settle.** Overlap is reachability, not delivered recall — a
term that survives can still be outranked. The twin rewrites only the gold; a
genuinely camelCase repository also has a camelCase *corpus*, which shifts
document frequencies and therefore BM25 weights, and that is out of scope here.
And MULocBench queries are filled GitHub issue forms, i.e. long natural language;
a corpus queried by pasted identifiers would show a smaller loss still, since an
exact identifier matches either spelling.

---

## 2. The code ingest path, and where it silently degrades

`cymatix ingest` infers `content_type` from the file extension (#224,
`cli/cmd_ingest.py:51-58`); before that fix, code took the prose path and the
AST chunker was never reached. `CodonChunker._chunk_code` then uses tree-sitter
when a grammar for the language is importable and falls back to a regex splitter
otherwise (`encoding/fragments.py:149-240`). The fallback is instrumented
(`chunk_ast` vs `chunk_regex` counters) and logged, so a bed built without the
grammars is detectable after the fact — that loudness is now pinned by a test.

**Language coverage** (printed by `test_grammar_coverage_diagnostic`):

| extension | detected language | chunking |
|---|---|---|
| `.py` | python | AST |
| `.js` | javascript | AST |
| `.ts` | typescript | AST |
| `.rs` | rust | AST |
| `.java` | java | **regex fallback** |
| `.go` | go | **regex fallback** |
| `.cs` | **not detected** | **regex fallback** |

**This is a code limitation, not an environment one — and that is the sharper
finding.** `_EXT_TO_LANG` (`encoding/tree_chunker.py:43-64`) detects ten
languages: python, rust, javascript, typescript, tsx, **go, java, c, cpp, ruby,
lua**. But `lang_module_map` inside `_get_parser` (`:102-111`) is hardcoded to
five — python, rust, javascript, typescript, tsx — and anything else raises
`ImportError(f"No tree-sitter package configured for {language}")`, which
`fragments.py` catches as the regex fallback. So Go, Java, C, C++, Ruby and Lua
take the regex path on **every** install, no matter which grammar packages are
present. Installing `tree-sitter-java` would not change it; the map would have
to gain the entry.

C# is a third case again: `.cs` is in the CLI's `_CODE_EXTENSIONS` but not in
`_EXT_TO_LANG`, so it routes to the code path and `detect_language` returns
`None` — the code branch with no language at all.

The regex fallback splits on `RE_CODE_BOUNDARY`
(`accel.py:212-215`): `^(?:def |class |async def |struct |interface |type |export )`.
Java methods (`public void …`, indented), Go functions (`func …`), C# and Kotlin
match none of those alternatives, so those files are cut into arbitrary
4,000-char windows with no structural boundary at all.

**The two gaps compound on the same languages.** Java, Go and C# lose AST
chunking *and* identifier decomposition. The languages the tokenizer already
disadvantages are the ones most likely to be chunked by regex as well. Any
non-Python code bed built on this environment would be measuring both at once,
and a receipt that does not name the installed grammars cannot separate them.

---

## 3. What these receipts do and do not settle

**Settled.** The tokenization asymmetry and its size in three regimes; that
comment density is the hidden variable; that the extractor cannot split case;
that routing works post-#224; that the regex fallback is loud; which grammars
this environment has.

**Not settled.** How often real code queries are natural language versus pasted
identifiers — that is a corpus property a real code bed answers, and it decides
whether the measured gap matters in practice. Nor whether an alternative
tokenizer would pay for itself: FTS5 offers `trigram`, and a custom tokenizer or
an identifier-splitting ingest-side field are both possible, but each is a
schema change with its own receipt burden and none has been priced. The probe
measures reachability, not delivery: it says what the funnel *cannot* see, not
what a widened funnel would deliver.

**The cheapest next step if a code bed is funded:** ingest the same repository
twice, once as-is and once with identifiers split at case boundaries into a
side field, and measure delivered gold on the same needles. That isolates the
tokenizer from everything else on a real corpus, and it needs no new benchmark.
