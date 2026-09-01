# Architecture hunt — external evidence pass

**Date:** 2026-09-01 · **Answers:** `research-inbox/2026-09-01-architecture-hunt-prompt.md`

**Method:** two adversarial deep-research passes (123 agents, 10.7M subagent tokens, ~68 min wall).
Pass 1: 24 primary sources, 119 claims extracted, 25 verified, 9 confirmed / 16 killed.
Pass 2: 8 areas (D–H + 3 recovery branches), verdict rubric split into
CONFIRMED / CORRECTED / UNVERIFIABLE / REFUTED so paywalls stop reading as refutations.
Plus local FTS5 receipts on SQLite 3.50.4 (below).

> **Status of every number in this document: prior, not receipt.** No source in eight
> areas measures recall at a shallow cutoff near k=12, and none measures anything on email.
> The recall canon is R@100/R@500/R@1000; the shallow canon is MRR@10/nDCG@10/P@5.
> `delivered_gold_rate@12` sits between them, and the two move in *opposite* directions
> under several key interventions.

---

## Bottom line

1. **The phrase/proximity lane is the best-evidenced cheap lever** — promoted above
   doc-level aggregation, on a rule the literature supplies and which also explains
   your two dead lane-reweighting receipts.
2. **Write-time question enrichment (lever 6) is a do-not-build.** The literature is
   strong, well-measured, and negative for exactly the component that would reach the
   drowned 61.
3. **The length-normalization family is smaller than the prompt assumes** — and
   FTS5's unreachable `b` is worth materially *less* than the document-level literature
   implies.
4. **Doc-level aggregation (lever 2) moved from "unevidenced" to "evidenced and
   genuinely undecidable."** Its sign flips three ways, and both structurally closest
   analogues point negative. Oracle-probe before building.
5. **A QPP/abstain gate (lever 7) cannot raise your metric by construction.**

**Mission arithmetic.** .80 needs +62 of 470. If the 61 pool-absent are unreachable —
and every lever surveyed here is structurally incapable of reaching them — then ~65% of
the remaining 95 misses must convert. Rank 8's probe is designed to settle whether the
honest ceiling is ~0.87 for the current corpus + chunking.

---

## The organizing rule (area G)

Beitzel et al. (JASIST 2004) is the cleanest natural experiment ever run on your
question: identical topics, corpus, parser, stemmer, stoplist — the *only* variable
being whether fused lanes came from one system or independent systems.

| lanes | Spearman | MAP vs best single lane | record |
|---|---|---|---|
| same system | 0.52–0.89 | −1.90 / −1.07 / −1.00 / −9.53 / −0.72 % | **lost 5 of 5 years** |
| independent systems | 0.37–0.61 | +7.86 / +4.51 / +2.91 / +12.28 / +9.66 % | **won 5 of 5 years** |

Their diagnosis: when systemic differences are held constant the strategies "are going
to be using the same terms to produce their ranked sets." Beitzel also cites Lee that
fusing different *query representations* in one system **does** gain, "since in this
case different sets of terms are used."

> **Operative rule: a new lane must change which UNITS are matched, not the arithmetic
> over the same term matches.**

Phrase/NEAR does (positions). Doc rollup does (union scope). Column weights do **not**.
Lane re-weighting does not — which is the published prediction that your two dead
reweighting experiments could not have worked.

**Two pre-flight gates are killed.** Lee's relevant-vs-non-relevant overlap
precondition was *satisfied* in Beitzel's losing runs (R-overlap 85.9–90.2% vs NR
68.9–72.9%) and fusion still lost every year. Vogt & Cottrell predict fused
*performance* at r²=0.95 held out but fused *gain* at r²=0.06. **No pre-flight statistic
will tell you whether a lane pays.** Build cheap lanes and measure.

---

## Ranked action ladder

| # | Action | Targets | Cost | Evidence | Kill criterion |
|---|---|---|---|---|---|
| 1 | R-Loss@12 + signed per-query ledger; split bed into fit / held-out | prerequisite | hours | strong (instrument), indirect (corpus) | n/a |
| 2 | **Phrase + `NEAR(...,N)` lane** into existing RRF | **37 phrase-holder**, some near-band | low | moderate-indirect, 2 independent tables | <½ of 37 phrase-match under live tokenizer → dies before you write it |
| 3 | Validate `rrf_k=20` on held-out; test off-diagonal per-lane k | 41 near-band | ~zero | direct on mechanism, wrong setting | fails held-out → revert to 60, that's the finding |
| 4 | Sweep `fts5_candidate_depth` **in isolation** | 41 near-band | config | weak; a confound turned into a hypothesis | flat across 2×/4×/8× → near-band isn't depth-limited |
| 5 | **Doc-union ORACLE PROBE**, then MaxP/top-k-sum rollup lane | **65 chunk-split** | probe: hours | best recall-metric evidence, still split | oracle ceiling <~20 queries → lane can't pay |
| 6 | Chunk scope/verbosity diagnostic over corpus + 156 slates | confirms/kills area B | a script | literature self-contradicts → must be local | distinct-term count doesn't separate gold → whole family dead |
| 7 | Split FTS5 content column, fit `bm25()` weights | 41 near-band only | low | mechanism CONFIRMED, effect near-null on recall | flat log-sweep 1→1000 → lever isn't there |
| 8 | Query-variation UNION **probe** on the 61 (probe, not lane) | **61 paraphrase** | offline only | split; closer source negative | probe *is* the kill, decisive either way |
| 9 | Cluster-structure rerank — oracle probe only; skipping is defensible | 41 near-band | high | cleanest lexical evidence in F, but W2.1 prior against | ceiling not >> ~30% realization → kill |

### Why rank 2 beats rank 5

Cheap proximity beat the elaborate structural machinery **twice, independently, on the
noisy collections**:

- Sheetrit/Shtok/Kurland: plain SDM beat length-adaptive document+max-passage
  interpolation on MAP on **4 of 5** collections, by **+14.3% relative** on ClueWeb09-B
  (.192 vs .168) — the largest and noisiest.
- Hasibi (SIGIR'17): flat SDM **0.3259 MAP** beat *every* unsupervised fielded model
  (PRMS 0.2895, MLM-all 0.3031).

Unlike FSDM it needs no labelled training. Both MAP, neither recall, neither email.
What earns it the top slot is not effect size — it is that it is the only candidate
satisfying Beitzel's rule at near-zero build cost.

**Two cautions.** (a) Latency at 947k on `detail=full` is unmeasured and is the one
place a cheap lever could turn expensive — measure p50/p99 before shipping. (b) The
pre-kill costs one script: verify the query phrase actually produces an FTS5 phrase
match against gold **under your live tokenizer** — stemming, punctuation, stopwords can
silently break it.

---

## Area-by-area

### A/B — corrections to the prompt's own framing

**OVERTURNED (biggest change):** pass 1 concluded aggregation evidence is all *neural*
reranking measured in nDCG, never recall. **That is false.** Four corpora carry purely
lexical, recall-metric doc-vs-chunk contrasts: PARM's BM25-only rows on COLIEE and
CaseLaw (paired t-tests, effect sizes >0.2), Pyserini 2CR BM25 doc-vs-segmented on
MS MARCO v1 (5,193 dev queries) and v2 (12M docs), and COLIEE's recall at a tuned
**k=7–8** — the only shallow-k recall figure anywhere near your k=12. The "never on
email" half stands.

**CORROBORATED:** the scope mechanism is thirty years old. Singhal (1996) derives match
probability as **linear in a document's distinct-term count** (vocabulary T, k distinct
terms → k/T) while measuring cosine normalizing as only (#unique)^0.6. Doc2Query++
names it from the expansion side: "BM25's term-frequency weighting amplif[ies]
mismatches from coverage-induced novel vocabulary, diluting original document signals in
the inverted index." Pass 1's mechanism claim was right.

**DEFLATED:** FTS5's unreachable `b` is worth *less* than it looks. Optimal b shifts
with the indexing unit in two independent corpora — COLIEE 0.99→0.59, MS MARCO
0.82→0.61 — and **both segmented optima land near 0.6**, so FTS5's fixed 0.75 is much
closer to where a chunk index wants to be than to the document-level optimum. Na
(TOIS 2015) carries the scope insight to BM25 and gets **+0.9% to +4.5% MAP, 3 of 9
cells not significant**, because BM25's `tfn/(tfn+1)` saturation already performs
verbosity normalization.

**EXTENDED:** if you build aggregation, use **max or top-k sum, never a mean**.
Bendersky's MeanPsg: WSJ MAP 28.38 → 20.42 / 14.03 / 10.72.

### D — fielded / BM25F: MIXED

Mechanism **confirmed against your exact engine by source inspection**: in
`ext/fts5/fts5_aux.c` the per-instance column weight accumulates into `aFreq[ip]`
*before* the saturation term (pseudo-tf = Σ w_c·tf_c) — Robertson's correct
pre-saturation ordering, the form that avoids the IDF double-counting and broken
saturation that make additive per-field scoring wrong. So a column split + weights
genuinely is "BM25F for free," and column weights strictly dominate token duplication
(duplication inflates D; a weight does not).

**Two hard structural limits, also confirmed:** D comes from `xColumnSize(pFts,-1)` —
whole-row token count against one global avgdl, no per-column b_s — and IDF is computed
once per phrase over row-level DF, column-blind. **A split leaves the at-cap penalty
byte-identical.** This is a term-weighting change, never a length-normalization change.

The strongest email result is a *ranking* result whose fitted weights point the wrong
way for you: TREC-14 W3C, uniform→tuned BM25F lifted known-item **MRR 0.458→0.522
(+14.0%)**, best run 0.613 — but the winner set **b_body=0.03**, switching body length
normalization essentially *off*, making long bodies more competitive. Ogilvie & Callan
on the same corpus: MRR 0.524→0.588 while **found@100 moved 112→113 of 125** — one item,
noise at n=470. On DBpedia the fielded increment over a properly tuned flat run is
**+2.9% MAP vs +72.5% for tuning k1/b**, the lever you cannot reach.

**No fielded/BM25F work anywhere reports recall@k.** The one fielded source reporting
recall at all is the COLIEE counter-evidence, where recall moved **down on 3 of 3 splits**.

### E — write-time expansion: NULL-OR-HARMFUL

Three independent decompositions agree the doc2query gain is dominated by term
**re-weighting** (copied terms = 67–69% of non-stopword output), not vocabulary
injection — and vocabulary injection is precisely what the 61 need.

| isolation | R@1000 | RR@10 |
|---|---|---|
| new-terms component alone | **+0.017 (+2.0%)** | **0.187 → 0.174 (drops below baseline)** |

| setting | result |
|---|---|
| in-domain MS MARCO | R@1000 .853→.947 (+11.0%), MRR@10 .184→.277, 55→64 ms |
| **off-domain BEIR, 18 zero-shot sets** | **mean R@100 +0.0056 abs, +0.94% rel, 11 wins / 7 LOSSES** |
| Robust04 (newswire) | −0.018 |
| Signal-1M (short informal msgs) | −0.019 |
| Touche-2020 | nDCG@10 −35.5%, R@100 −6.5%, BM25 significantly better |
| index cost | **+98.6% (0.74→1.47 GiB)**, MRT +55% |

Doc2Query++ measures the mechanism directly against you: novel vocabulary correlates
positively with *dense* gain and "weaken[s] or turn[s] negative" for sparse.
Doc2Query−− filtering optimizes the wrong axis — buys early precision by preferentially
discarding **new** terms (87% copied vs 76% unfiltered), fails zero-shot on 4 of 5 BEIR
sets.

**Two blockers specific to you:** docTTTTTquery runs T5 with a 512-token window and
notes MS MARCO never truncates — a 4,000-char chunk *does*, so expansion would generate
from a truncated prefix and the chunk **tail would go unexpanded**. And appending
lengthens every entry toward your cap while b=0.75 is a hard-coded C literal: you would
be **feeding the at-cap pathology with no knob to compensate**.

*Supported design constraint if you ever revisit: append beats replace (+0.044 to +0.087
R@1000) and needs no delimiter. Dose saturates then degrades, optimum corpus-specific
(10 / 40 / 100 in three papers) — a full reindex per sweep point.*

### F — metadata/tag feedback: MIXED

The actual sub-question — **PRF over tags as a substitute for term feedback** — is
genuinely thin, and that is a finding, not a search failure. No primary source runs
tag-PRF against term-PRF on a shared corpus with a shared metric; the social-tagging
line (Bao WWW'07, Xu CIKM'07) is entirely paywalled.

Nearest rigorous evidence is **entity**-based and **negative for substitution**:
RM3-Entity 0.776 vs RM3 0.812 R@1000; LCE-Entity 0.793 vs LCE 0.825. Only the hybrid
wins. Coverage ceiling caps it before ranking quality binds: of relevant docs holding
any entity, **only 43% hold a query entity**.

What does hold is **cluster-structure feedback** — feeding back list *structure* with no
term expansion — fully lexical and neural-free: WT10g MAP .1861→.2044 (+9.8%, beating
RM3's .1966), AP +13.7%, ROBUST +9.8%, WSJ +10.8%, GOV2 +4.5%, all significant. But
Kurland & Krikon bound it: realized p@5 39.8 against an optimal-cluster ceiling of 65.9
— **~70% of the structure signal is unreachable**. And your own W2.1 COVER-walk kill
("mass → hubs not gold") is a direct local prior against the same failure class.

**Independent corroboration of your abstain kill:** Billerbeck & Zobel swept top-doc
score, distinctness, term specificity and query clarity as predictors of when expansion
helps, found none worked, and explicitly rejected score-binned gating.

**Take the measurement, not the technique.** Collins-Thompson's **R-Loss@k** (net
relevant docs present in top-k before a change and absent after) and **RI** (helped
minus hurt) are recall-shaped per-query harm accountings — exactly the instrument you
need given two prior reweighting kills. That is rank 1.

### G — fusion: MIXED (strongest explanatory value, weakest effect sizes)

See the organizing rule above. Additional settled points:

- **Bruch (TOIS 2023) refutes "RRF k is a parameter-free robust default."** Tuned k
  gains up to +0.026 NDCG in-domain and loses up to **−0.072 out-of-domain** — the loss
  exceeds the gain. Off-diagonal per-lane k beat shared k.
- **Cormack's own sweep**: k=60 was never his optimum (k=80, MAP .2147 vs .2145); the
  k=10..100 band spans only 1.1%; cliffs at k=0 (−3.5%) and k=500 (−2.3%). A plateau
  with cliffs — consistent with your 60→20 receipt even though the direction differs.
- **Don't swap the combiner.** CombSUM 0.331 *ties* RRF 0.331 exactly on Robust04 AP.
  Bruch: combiner swap moves NDCG@1000 +0.015..+0.032 but Recall@1000 −0.004..+0.011,
  **sign-indeterminate**. *Honest caveat:* at depth 1000 ranking and recall are nearly
  decoupled, whereas at k=12 a rank-13→11 move **is** a recall gain — so the null is
  weaker for your near-band bucket than the R@1000 numbers suggest.
- **~30% of queries are harmed under every fusion method tested** (Benham & Culpepper).
  Expect a meaningful minority of your 314 working queries to regress under any change.
- **Correction to a widely-misread source:** the RAG-Fusion deployment is *not* evidence
  that adding a lane lowers accuracy. Fusion consistently **raised** upstream recall;
  the 3.5–6.1pp Hit@10 loss appeared only after a cross-encoder reranker truncated the
  enlarged pool — a component you don't have. Keep it as a warning that pool gains can
  evaporate at a truncation boundary (**your metric IS a truncation boundary at 12**).

### H — QPP / abstention: NULL-OR-HARMFUL

**The decisive argument is structural, not empirical:** `delivered_gold_rate@12` is
scored on the delivered set, so a gate reduces coverage and **cannot raise it by
construction**. At best it improves correct-among-answered — a different metric.

Empirically it's also dead. On MS MARCO with BM25 (closest published analogue):
**WIG r=0.027, NQC r=−0.010, UQC r=−0.123, none significant** — your score-threshold
kill, arrived at independently. Pre-retrieval ceiling r=0.44/ρ=0.37 (He & Ounis), and
they **specifically kill the IDF-spread feature before you build it**: γ₂ = idf_max/idf_min
gives r=.0405 (p=.52), never significant in any of six cells.

Zhao & Callan is the direct warning against your most natural anchor feature: **IDF is a
worse-than-constant predictor** of whether a term appears in relevant documents
(L1 0.3078 vs 0.2936 constant baseline); "There is also no simple correlation between
necessity and idf."

Your hypothesis *does* have a published ancestor — **Yom-Tov's sub-query overlap**,
which beats the score-magnitude family you already killed (Kendall τ .439/.571 vs .278/.379
for top-doc score and .186/.243 for std-IDF). Pure lexical bookkeeping: run each query
term as its own FTS5 query, intersect its top-10 with the full query's top-10, histogram
by log(DF). Motivated by *literally your phrase-holder failure mode*. **But**: measured
in τ against MAP never recall; TREC-8 newswire; **supervised**; and it collapses to
τ .118–.202 on the heterogeneous web collection — the analogue for your corpus.

**Use it diagnostically** — label the 156 misses by anchor-coverage to sharpen the
taxonomy — **not as a gate.**

### R1 — fused dual-granularity: recovered, then NULL-OR-HARMFUL

The access-driven kill was wrong; the ECIR 2008 numbers verify. But recovering them
doesn't rescue the technique. Max-passage wins big on long heterogeneous docs
(FR12 MAP 22.0→30.1, +36.8%) and **significantly loses** on short homogeneous ones
(AP89 20.0→18.8/17.7; WSJ 28.4→26.1, all significant).

The killer is **Kurland's own group ten years later**: the exact length-adaptive
document+max-passage interpolation, on five collections up to 50.2M docs, is a near-null
vs plain whole-document LM (**4 wins, 1 tie, 5 losses** across 10 cells) and clearly
harmful on ClueWeb09-B, the largest and noisiest (**−10.2% MAP, −9.7% p@10**), with no
significance markers on that row. The 2008 authors' own framing says it quietly: the
interpolation beats the *passage* lane in 90–96% of comparisons but the *document* lane
in only 50–67%. **Insurance against a failing passage lane, not lift.**

If you ever build a document+chunk mixture: **tune ONE global weight and stop.** The
adaptive weight's demonstrated value is only that it dodges a catastrophically bad
constant.

### R2 — pivoted unique normalization: recovered, MIXED

Kill was wrong on 3 of 4 claims. Pivoted **unique** normalization beat plain cosine
+18.3% AP and best pivoted cosine +6.0%, with a real recall gain (+338 relevant docs,
3.3× the +103 from best pivoted-cosine). **Directly on-point for a character cap:** the
same paper ran identical machinery with **byte size** and byte size **lost** on both AP
and recall.

**Two harm results transfer as warnings.** At slopes 0.60/0.65 pivoted cosine *improves
AP while reducing relevant-retrieved below baseline* — **the AP-optimal slope is not the
recall-optimal slope**, and they peak one step apart. And the extreme-length tail:
pivoting *aggravates* over-retrieval of very long docs into "strongly favouring" them;
the authors couldn't tune out of it and had to change the length **variable**.

**The deflator:** Na (TOIS 2015) carries it to BM25 → +0.9%..+4.5% MAP, 3 of 9 cells not
significant, and a rival entropy-based scope measure beats UniqLength on 5 of 9.
Plus the **email hazard the paper names itself**: unique-term counts inflate under text
noise, and Enron-style mail (signature blocks, quoted-reply chains, message-ids,
disclaimers, base64) is a vocabulary-inflation minefield — while Singhal's own remedy for
noisy text is byte size, the *worse* variable. **That contradiction is unresolved for
email**, and only rank 6 resolves it.

*Structural note: none of these papers studied a **truncated** length distribution. Their
pathology lives in the >6×-average tail; a hard 4,000-char cap deletes that tail while
leaving distinct-term variance at the cap intact.*

### R3 — passage-index + RRF recall: recovered, MIXED (best recall evidence here)

Paper is real (Fink/Recski/Kusa/Hanbury, JURISIN 2022); all three disputed claims verify.

**The mechanism caveat that limits transfer most:** in both COLIEE and PARM the multiple
rankings fed to RRF come from splitting the **query document** into passage queries
(|R| = n_q), because the query is a whole court case. **You have ONE short query.** With
|R|=1, RRF over one ranking is a monotone transform of best-chunk rank — plain MaxP.
*The fusion mechanism that produced those gains does not exist in your setting.* The
Pyserini doc-vs-segmented rows are the correct analogue instead (short NL queries).

| result | recall | early precision |
|---|---|---|
| COLIEE BM25, tuned k=7–8 | +2.82pp train, +2.91pp dev | — |
| PARM COLIEE (BM25, sig, ES>0.2) | R@100 +2.66pp, R@500 +5.94, R@1K +5.18 | nDCG@10 **−32.6%** |
| **PARM CaseLaw**, same method/scorer | **R@100 −8.56pp (−20.3%)**, R@500 +6.58, R@1K +9.40 | nDCG@10 −77.8% |
| Pyserini MS MARCO v1 dev (5,193 q) | R@1000 .8856→.9178 (+3.22pp) | MRR@10 +3.85pp |
| **same pair, DL19 / DL20** | **R@1K −0.95pp / −3.30pp** | — |
| MS MARCO v2 (12M docs) | 15/15 cells positive | nDCG@10 +12.9–20.9% |

**Three independent sign reversals** — with depth, with corpus, with query set. Read the
corpus reversal carefully: the collection where chunk+RRF **hurt** shallow recall used
**fixed-length ~200-word chunks with 7.5 chunks/doc — structurally your setup** — while
the one where it helped had native structural paragraphs at 47.5 chunks/doc. And the
query-set reversal puts the losses on the **deeply-judged sets with many relevant docs
per topic — exactly your 65 chunk-split bucket**. Both closer analogues point the wrong way.

**Free lever discovered:** the Pyserini comparison is **not** a granularity-only
ablation — the segmented arm also passes `--hits 10000 --max-passage-hits 1000`, so pool
depth and MaxP change together. You already own `fts5_candidate_depth`. That confound
becomes rank 4, testable for a config line.

**Carry verbatim:** passage-level+RRF beat document-level on recall by +15.9% to +23.7%
relative — which argues **against rolling chunks up to documents as a replacement**. Any
rollup should be an **additional lane over the existing chunk delivery, not a substitute**.

---

## Do-not-spend ledger

| Don't build | Because |
|---|---|
| doc2query / docT5query, any variant | new-terms component = +2.0% R@1000 and *drops* RR@10; off-domain +0.94% mean R@100 with 7/18 losses; ~2× index inflation into a 4,000-char cap with b unreachable |
| Doc2Query−− filtering | optimizes the wrong axis — discards new terms (87% vs 76% copied), fails zero-shot on 4/5 BEIR |
| QPP / score-distribution abstain gate | cannot raise a metric scored on the delivered set; WIG/NQC/UQC all ~0 and non-significant on MS MARCO BM25 |
| IDF-spread feature (max/min or variance) | γ₂ r=.0405 (p=.52), never significant in 6 cells |
| Stacking cheap difficulty signals into one score | combining is null-to-harmful; degradation regime is mutually-correlated inputs — which IDF-family features are (ClueWeb09B .2914→.1707) |
| Anchor/rare-term coverage keyed on IDF alone | IDF is *worse than constant* at predicting term presence in relevant docs (L1 .3078 vs .2936) |
| Replacing RRF with normalized score fusion | CombSUM ties RRF exactly on Robust04; recall delta sign-indeterminate |
| Column split shipped with equal weights as "neutral refactor" | measured negative: flat LM beat equal-weight MLM-all in both judgment sets (−3.6%, −5.3%) |
| Query-independent priors (recency, thread depth, chunk length) without re-fitting | Craswell: −10.7%..−14.1% MAP on discussion search from the same features that helped known-item; Ogilvie: thread-depth prior cost 5 known-items of 125 at test |
| Tag-only / entity-only lane substituting for the term lane | entity-only underperforms the channel it replaces; 57% of relevant docs can't be matched by it at all |
| **Mean**-of-chunk-scores aggregation | catastrophic everywhere: WSJ 28.38 → 20.42 / 14.03 / 10.72 |
| LLM query rewriting as an online lane | **EnronQA, real Enron email, Pyserini BM25, real recall: R@5 87.5 → 82.5 / 86.6 / 88.5** — 2 of 3 hurt, best +1.0pp, prompts DSPy-optimized |
| Custom scorer over FTS5 postings to reach b | both segmented optima ≈0.6, so fixed 0.75 is already close; Na: +0.9–4.5% MAP, 3/9 n.s. |
| Lee's overlap ratio as a pre-flight lane gate | measured as a *false green light* — satisfied in Beitzel's losing runs all 5 years |

---

## Residual unknowns — local A/B only

1. **Whether any lever moves recall at k=12.** Nobody measures it. Closest is COLIEE's
   tuned k=7–8, 198 legal queries, no significance test.
2. **Whether chunk indexing + doc aggregation help on EMAIL.** No published receipt
   exists; the one paper proposing the Enron study defers it to future work.
3. **Whether your 470 queries are human-authored or generated.** *Answerable in minutes
   and it conditions several levers.* Kim & Croft: a fielded model beat flat by **+78%
   MRR on synthetic queries whose terms were drawn from randomly chosen fields**, and
   the same models collapsed to within ±2% of flat on **456 real human queries** over a
   comparable heterogeneous enterprise collection. If your bed is generated, a fielded
   lane — and possibly a phrase lane, if the generator quoted the source — could score
   well on the bed and be worth nothing in production.
4. **Overlap structure of the 156.** 61+37+41 = 139, plus 65 chunk-split = 204 > 156, so
   buckets overlap and chunk-split is cross-cutting. Only you can say how much of the
   reachable 95 the 65 covers — i.e. whether one rollup lane could carry most of the
   required +62 or only a fraction.
5. **Is the at-cap advantage monotone in length, or a STEP FUNCTION at 4,000 chars?**
   Every literature result is measured on a naturally-occurring long tail; a hard cap
   deletes that tail.
6. **Does distinct-term count actually separate gold from interlopers on your bed?**
   Literature self-contradicts. Rank 6 resolves it — cheapest large kill available.
7. **Oracle headroom of doc-union rollup on the 65.** Sign not predictable a priori.
8. **Does `rrf_k=20` survive a disjoint held-out slice?** Bruch's warning is on
   BM25+dense at NDCG@1000; your 3-lexical-lane k=12 regime is untested by anyone.
9. **FTS5 phrase/NEAR latency at 947k on detail=full.** No published receipt. The one
   place the top lever could turn expensive.
10. **Are the 61 reachable by any lexical generator at all?** T2-RAGBench found 71.0% of
    residual failures had gold in *neither* lane's top-5 — same shape as your
    decomposition. If rank 8's probe agrees, honest ceiling ≈0.87, .80 is still reachable
    without touching the 61, and the paraphrase bucket re-plans as an **ingest/chunking**
    question, not a retrieval one.
11. **Is the 85%-vs-43% at-cap asymmetry causal or a confound?** Gold may be shorter for
    an unrelated reason (position in message, chunker boundary on quoted text, thread
    structure). Bucketing the 156 by winner char-length and by whether the winner is
    quoted/boilerplate would distinguish these.

---

## Local receipts (SQLite 3.50.4, this worktree)

**BM25F-style per-column weighting works** — pass 1 refuted this; the refutation was wrong.

```
bm25(t, w_title, w_body)   doc A (term in title)   doc B (term in body)   winner
  (1.0,  1.0)                    -3.1233                -2.9969             A
  (5.0,  1.0)                    -5.1386                -2.9969             A
  (10.0, 1.0)                    -5.5895                -2.9969             A
  (1.0,  5.0)                    -3.1233                -5.0683             B
  (1.0, 10.0)                    -3.1233                -5.5476             B
  (0.0,  1.0)                    -0.0                   -2.9969             B
```

Scores change and rank order flips. Column filters all work: `title : term`,
`{title body} : term`, `- title : term`, and `content : "alpha beta"` (fielded phrase).

**`NEAR` counts tokens BETWEEN clumps** — with 2 intervening tokens, `NEAR(a d, 2)`
matches and `NEAR(a d, 1)` does not. Phrase order is enforced (`"alpha beta"` is not
`"beta alpha"`). `bm25()` scores NEAR-matched rows without error.

**But you have no fields to weight.** `genes_fts` is `(gene_id, content, complement)`
(`ddl.py:440` external-content, `ddl.py:572` fallback; neither sets `detail=`, so both
are `detail=full`) and `content` concatenates source_id + promoter tags + gene content.
**A BM25F lane is a schema change, not a weighting change** — that is why lever 3 is
repriced to rank 7.

---

## Sources

Dai & Callan SIGIR'19 · Zhang/Yates/Lin ECIR'21 · PARADE (TOIS 2023) · Kamphuis et al.
ECIR'20 · SQLite FTS5 docs + `ext/fts5/fts5_aux.c` · Metzler & Croft SIGIR'05 ·
Beitzel et al. JASIST 2004 · Vogt & Cottrell · Cormack/Clarke/Buettcher SIGIR'09 ·
Bruch TOIS 2023 · Benham & Culpepper ADCS'17 · Nogueira & Lin (doc2query,
docTTTTTquery) · Doc2Query−− ECIR'23 · Doc2Query++ · BEIR · Singhal/Buckley/Mitra
SIGIR'96 · Na TOIS 2015 · Robertson/Zaragoza/Taylor CIKM'04 · Craswell/Zaragoza/Robertson
(TREC-14 W3C) · Ogilvie & Callan · Hasibi SIGIR'17 (FSDM/DBpedia-Entity v2) · Kim & Croft
SIGIR'10 · Bendersky & Kurland ECIR'08 + thesis · Sheetrit/Shtok/Kurland ·
Ai/O'Connor/Croft · Lee/Croft/Allan SIGIR'08 · Kurland & Krikon · Liu & Croft ·
Collins-Thompson CIKM'09 · He & Ounis · Zhao & Callan · Yom-Tov et al. ·
Billerbeck & Zobel · Fink/Recski/Kusa/Hanbury JURISIN'22 · PARM · Pyserini 2CR ·
EnronQA · T2-RAGBench
