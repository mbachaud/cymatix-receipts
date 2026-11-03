# BRIGHT (12 domains) and pooled multi-hop sets on a Linux cloud VM (2026-11-03)

Recall benchmarks run outside the BEIR set. BRIGHT tests reasoning-heavy queries.
HotpotQA, 2WikiMultihopQA and MuSiQue test whether retrieval collects **every**
supporting paragraph a question needs, rather than just one.

**Not a ledger row.** Nothing here is citable until it has a row in
`docs/benchmarks/BASELINES.md`.

## Conditions

The engine, host, config, builder (SPLADE-off, ingest_c=4), ladder flags and child env
match `../beir_linux_vm_2026-11-02/` (engine `bd3c541f`). The same driver,
`run_beir_linux.py`, runs here. The only change is that it calls `tools/mh_score.py`
on the `beir_mh_*` tags. The corpora are converted to the BEIR file layout first and
then go through the stock `build_beir_corpus.py` emitter:

- **BRIGHT:** `tools/bright_to_beir.py` converts the HF `xlangai/BRIGHT` short-document
  configs, using `documents` and the original `examples` queries with no reasoning
  augmentation. BRIGHT's per-query `excluded_ids` (leetcode, aops, theoremqa_questions)
  become `excluded_<tag>.json`. The local scorer copy `tools/beir_ndcg_multi.py` drops
  those documents from both the ranking and the gold before scoring.
- **Multi-hop:** `tools/multihop_to_beir.py` builds one **pooled dev corpus** per
  dataset. Every context paragraph across all dev questions becomes one document, with
  id `sha1(title\0text)[:16]`. The gold is the supporting paragraphs. Sources:
  - HotpotQA: distractor validation, 66,635 docs and 7,405 questions.
  - 2Wiki (`framolfese/2WikiMultihopQA`): validation, 56,687 docs and 12,576 questions.
  - MuSiQue: `musique_ans_v1.0_dev`, 21,100 docs and 2,417 questions.

  Because the corpus is pooled, these numbers do not compare with the standard
  per-question distractor setting.

## Baselines

- **Paper BM25** is Table 2 of the BRIGHT paper (arXiv 2407.12883), which used gensim
  LuceneBM25Model with the pyserini analyzer. Its corpus and qrels are the same as
  here, but its BM25 implementation is not.
- **bm25s same-corpus** is `tools/bright_bm25.py` and the BM25 part of
  `tools/mh_score.py`: bm25s 0.3.16 in lucene mode, k1=1.5, b=0.75, English stopwords
  and the PyStemmer english stemmer, run over the same documents and exclusions. On
  BRIGHT it scores well below the paper's BM25 (mean 0.092 against 0.145). Treat it
  as a weak BM25. Because the multi-hop BM25 columns use the same implementation, a
  faithful BM25 would most likely widen the multi-hop gaps below, not close them.

## Results

See `TABLE.md`. `*` marks the Cymatix all@100 column, which is a lower bound: the
Cymatix ranked list is short, with a median of about 48 documents.

- **BRIGHT:** mean nDCG@10 is 0.116 for Cymatix and 0.145 for the paper's BM25.
  Cymatix leads only on robotics (0.147 against 0.136). The biggest gaps are
  theoremqa_questions (−0.063), biology (−0.065) and stackoverflow (−0.049).
- **Multi-hop:** the packet nearly always carries at least one supporting paragraph:
  - any_delivered is 0.91 to 0.92 on HotpotQA and 2Wiki, and 0.78 on MuSiQue;
  - all-hops-delivered trails the weak BM25 top 12 everywhere: HotpotQA 0.405 against 0.644, 2Wiki 0.249 against 0.364, MuSiQue 0.080 against 0.154;
  - the fraction of supporting paragraphs delivered is 0.12 to 0.15 lower than BM25 on every set.

  The miss is in completing the set of hops, not in finding the first one.
- **mh_score check:** on MuSiQue the scorer's doc-level grouping was checked against
  the repo nDCG scorer, and its recall@10 and recall@100 agree.

## Layout

Each `<tag>/` directory holds:
- the ladder receipt (with per-query ranked lists and the delivered packet);
- the nDCG receipt;
- `mh_score_*.json` (multi-hop tags only);
- the resolved needles and gold;
- `excluded_<tag>.json` (BRIGHT tags where it applies);
- `bed_manifest.json` and `build_log_tail.txt`.

The beds and corpora were deleted after scoring.
