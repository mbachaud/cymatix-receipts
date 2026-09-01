# Sol — Cymatix path to 70/80% ERB r@12 (received 2026-08-31, via Max)

Short version: Cymatix can plausibly cross 70% overall ERB r@12 with
deterministic retrieval work. Reaching 80%, or preserving 70-80% recall at
r@2-5, is a representation problem — not another ranking-knob problem. The
"ribosome" function probably is needed, but not the current LLM-heavy
Ribosome/Compressor. Better design: (1) a deterministic, provenance-preserving
ingest compiler now; (2) an optional document-side semantic abstraction lane
later, only where deterministic representations demonstrably plateau.

## Standing (947k ERB)
- score-map r@12 320/470 = 68.09%; post-rerank 321/470; delivered floor-12 314/470 = 66.81%
- r@2 210/470 = 44.7%; r@5 279/470 = 59.4%
- 70% r@12 = +9 hits; 80% r@12 = +56; 80% r@5 = +41 promotions +97 hits
- Metrics split: C_K (candidate-union recall at K) x H_r (head concentration | candidate) = R_r

## Class picture
- basic n=175: 44.6/58.9/68.6 at r@2/5/12 — +3 for 70%, +20 for 80%; deficit is HEAD CONCENTRATION; "basic" is an upstream label — decompose into literal fact, title/path, structured KV, passage-boundary, date, code-symbol, vocabulary failures.
- semantic n=125: 12.0/24.8/35.2 — +44 for 70%, +56 for 80%; structurally different: 61 pool-absent / 14 @13-30 / 6 @31-100 / 1 delivery-lost; coverage favored gold 16/21 reachable. Perfect reranking of the 21 leaves semantic ~51-52%. New representations must make absent gold retrievable. Split: entity/attribute descriptions (deterministically addressable) vs jargon/paraphrase + cue-trigger (needs re-expression).

## Ribosome verdict
Current Ribosome = legacy alias for Compressor (model-backed codon/tag/summary + second extraction call) — not the lightweight deterministic layer needed. CPU tagger is the beginning of a deterministic ribosome. Missing: a multi-view evidence compiler — raw body preserved; title/heading path; source path/filename components; entities + local aliases/acronyms; dates/ranges/relative-time normalization; IDs/URLs/paths/ports/versions/config KVs; sentence/event units; code symbols + AST units; typed relationships (parent, prev/next, reply-to, same-section, issue/file, explicit links); support_span + parent raw gene + source-set identity on every derived card. Derived evidence AUGMENTS raw evidence, never replaces it. Cymatix currently flattens source_id + tags + body into ONE FTS field; FTS5 supports phrases, NEAR, column filters, per-column BM25 weights, trigram — no new retrieval service required.

## Recommended path
1. Fielded evidence cards (highest priority) — separate legs, fuse with existing RRF/eps-band.
2. Structure-aware segmentation + parent delivery (retrieve unit, deliver parent/support span) — candidate quality AND r@2-5 concentration.
3. Phrase + proximity evidence (SDM-style ordered bigrams + bounded unordered windows).
4. Conservative normalization as an ADDITIONAL leg (aliases, acronyms, dates, filenames, stemmed view; keep originals).
5. Only explicit, typed adjacency (reply-to, same-heading, parent/child, temporal neighbor, issue/file), one hop, seed-gated, provenance retained. Generic COVER graph is dead (W2.1: 1 genuine rescue / 1,410 slots).
6. Gated query-time expansion only (RM3/Bo1 PRF, contained experiment, only on confident first pass; cannot fix gold-free blackouts; drift risk).
7. Learned deterministic-feature ranking later (LambdaMART over lexical/coverage/field/proximity/source/structural), needs clean dev split.

## When model-backed ingest becomes justified
LoCoMo-Plus cognitive 3/401 with all sparse+dense baselines ~1.5-2.7%; obs-doc three-way (.4348 -> .2645 turn-gold / .5189 union) = abstractions help but steal seats unless linked to raw evidence; MULoc shows candidate absence + delivery starvation. If deterministic cards plateau: opt-in "semantic observation" layer — async, content-hash cached, short claim/event/preference/constraint/concept cards, every card linked to exact supporting spans, retrieval may hit abstraction but source-set assembly delivers/accompanies raw evidence, backfillable, priced on the semantic pool-absent + LoCoMo cognitive cohorts. A ribosome in FUNCTION (doc-side lexicalization), not the current do-everything Compressor.

## Experiment ladder
1. Instrument per-leg candidate recall at K=50/100/500 + conditional head concentration + delivery separately.
2. Let the active W2.2 full run finish (only 30-query probe existed at writing).
3. Fielded FTS evidence-card table on a frozen development split.
4. Structure/parent, then phrase/proximity, then normalization — one paired cell at a time.
5. Tune concentration only after candidate-union recall improves.
6. Freeze weights before held-out ERB eval; confirm on LoCoMo/MULoc/FinanceBench/EnronQA.
7. Only then price provenance-linked semantic observations.

Gate: 70% overall r@12 = engineering gate, not success claim. Real graduation: per-class floors, r@5, candidate-union recall, delivery, latency, external confirmation.
