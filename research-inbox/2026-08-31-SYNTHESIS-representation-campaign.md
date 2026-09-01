# Synthesis — the representation campaign (2026-08-31)
Inputs: Sol's plan, Gemini 3.7 survey (graded), fielded-cards design memo
(Sonnet), red-team memo (Sonnet), basic-miss taxonomy (Opus, on-bed), plus
the day's receipts (muloc budget-14000 null, FinanceBench baseline blackout).
All in this directory. Author: Claude (Fable), session cutoff-paraphrase.

## The unified failure map (all receipted)

| cohort | n | mechanism | reachable by |
|---|---|---|---|
| ERB basic misses: literal-fact drowning | 31 | generic terms, best-term DF>=3001, but 37/37 "absent" golds RETURN on exact phrase probe (phrase DF ~166) | PHRASE/PROXIMITY leg |
| ERB basic misses: named-doc routing | 12 | query names a file/doc; filename match unique among 499k, yet gold scores 0 | TITLE/PATH leg |
| ERB basic misses: vocabulary gap | 11 | terms genuinely absent | normalization (4) / abstraction lane |
| ERB basic: delivery-lost | 5 | delivered_count=6 under floor 12 (hard-floor gating) | tier_hard_floor_frac cell |
| ERB rank-6-12 concentration (r@5 lever) | 17 | 12/17 carry a verbatim query phrase with DF<=50 | PHRASE leg (head) |
| ERB semantic: drowned | 61 | description->proper-noun register gap | abstraction lane (deterministic legs won't reach; LSA = plateau checkpoint) |
| ERB semantic: reachable band | 21 | gold out-covers interlopers 16/21 (ERB-scoped!) | W2.2 arm (running; ERB-only until cross-corpus confirm) |
| MULoc delivered_count=6 cohort | 226 | 15%-of-top hard floor, NOT tokens (14000 null receipt) | tier_hard_floor_frac cell |
| FinanceBench metrics class | 50 (0 hits) | doc-identity x concept intersection inexpressible in flat FTS | TITLE/DOC-IDENTITY + CLAIMS/KV legs |
| LoCoMo cognitive | 401 (3 hits) | cue-trigger disconnect; dense fails too | provenance-linked observation lane only |

## Verdicts on the inputs
- Sol's plan: adopted with amendments — item 6 (gated PRF) CUT (wave-2 kill:
  feedback set gold-free by definition on miss needles); gates must NAME
  their basis (map vs delivered — they diverge double-digit under delivery
  levers); holdout/dev-split discipline moves to BEFORE cell 1; add the
  hard-floor cell (missing from the ladder despite MULoc being its cited
  regime); structure-parent deprioritized on ERB (0/60 passage-boundary) but
  kept for LoCoMo/code corpora.
- Gemini survey: diagnosis holds (our semantic .352 sits in its .28-.35
  band); PPMI rewriting + graph walks already killed; VSA inapplicable
  (random atoms = orthogonal synonyms); ONE survivor = LSA as a banded
  ranking leg, parked at the plateau checkpoint.
- Design memo: fielded cards feasible but lopsided — detail= is per-table ->
  build a SEPARATE small evidence_fts (detail=full) rather than widening
  genes_fts; path/entities legs partially redundant with shipped tiers;
  claims column nearly free (key_values already extracted, never
  value-indexed); temporal cheap (spaCy DATEs currently discarded,
  tagger.py:449); migration = receipted DROP+rebuild (~3 min at 947k);
  base-rate warning: last three new-leg+RRF cells were null-to-negative.

## Revised ladder (each cell paired, frozen dev split FIRST)
0. Freeze dev/holdout split of the 470 (stratified by class) + name every
   gate's basis (delivered AND map reported; per-class floors).
1. PHRASE/PROXIMITY leg (separate evidence_fts, detail=full; ordered
   bigrams from adjacent non-stop query terms; NEAR fallback). Headroom:
   +9..13 basic r@12 + the r@5 concentration lever. Risk: re-ranks the
   whole class (86/115 hits also carry phrases) — paired-loss watch.
2. TITLE/PATH leg (doc-identity + filename/dir components as a column or
   dedicated leg; fixes the tokenizer fragmentation FinanceBench exposed).
   Headroom: +6..9 ERB basic; FinanceBench metrics-class is the sharp gate.
3. CLAIMS/KV column (design-memo Stage 0, nearly free). Gate on
   FinanceBench + EnronQA (ERB shows KV anti-correlated — do not gate on ERB).
4. HARD-FLOOR cell: tier_hard_floor_frac ladder (0.15 shipped / 0.10 /
   0.05 / 0) on muloc + ERB delivered_count=6 cohorts. Cheap config A/Bs.
5. W2.2 graduation decision when the 470 arm lands (ERB-scoped; needs
   cross-corpus confirm before any default flip).
6. Normalization leg (aliases/acronyms/dates) — small (4 ERB hits), ride
   along with cell 2's tagger touch.
7. PLATEAU CHECKPOINT: LSA banded leg (Gemini survivor) on the frozen
   split; then price the provenance-linked semantic-observation lane on
   the semantic-drowned-61 + LoCoMo-cognitive cohorts (displacement
   receipt mandates abstraction->source delivery linkage).

## Gate language (red-team finding 4 adopted)
"70% ERB r@12" is an engineering gate on the MAP basis (320/470 today);
delivered (314/470) is the product number; every receipt reports both plus
per-class floors, r@5, and pool-absent counts (C_K vs H_r separation).
