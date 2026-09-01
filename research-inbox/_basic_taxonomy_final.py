"""Pass 3: assign failure-mode flags + primary label; emit the two deliverables."""
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

BED = "file:F:/tmp/erb_blob_v09x.db?mode=ro"
OUT = r"F:/Projects/cymatix-context/research-inbox"
DF_CAP = 3001
WORD = re.compile(r"[a-z0-9]+")
TOK = re.compile(r"[a-z0-9_/\-]+")
STOP = {
    "the", "and", "for", "what", "was", "were", "did", "does", "are", "with", "that",
    "this", "from", "into", "how", "who", "when", "where", "which", "why", "his",
    "her", "its", "their", "our", "you", "your", "not", "but", "any", "all", "can",
    "has", "have", "had", "been", "being", "about", "after", "before", "during",
    "per", "via", "than", "then", "them", "they", "she", "him", "there", "here",
}


def stem(t):
    if t.endswith("ies") and len(t) > 5:
        return t[:-3] + "y"
    if t.endswith(("ses", "xes", "zes", "ches", "shes")) and len(t) > 5:
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        return t[:-1]
    return t


def words(s):
    return {t for t in WORD.findall((s or "").lower()) if len(t) > 2}


def toks(s):
    return {t for t in TOK.findall((s or "").lower()) if len(t) > 2}


def main():
    rows = json.load(open(os.path.join(OUT, "_basic_enriched_rows.json"), encoding="utf-8"))
    con = sqlite3.connect(BED, uri=True)
    cur = con.cursor()
    dfc = {}

    def tag_df(t):
        if t not in dfc:
            dfc[t] = cur.execute(
                "select count(*) from (select 1 from promoter_index where tag_value=? limit ?)",
                (t, DF_CAP),
            ).fetchone()[0]
        return dfc[t]

    for r in rows:
        gids = r["gold_ids"]
        blob = ""
        if gids:
            qm = ",".join("?" * len(gids))
            for (c,) in cur.execute(
                f"select content from genes where gene_id in ({qm})", gids
            ):
                blob += "\n" + (c or "")
        gold_raw = toks(blob)
        gold_stems = {stem(t) for t in gold_raw}
        qw = words(r["query"]) - STOP

        # normalization: query terms that only match gold AFTER stemming, and are selective
        norm_only = sorted(t for t in qw if t not in gold_raw and stem(t) in gold_stems)
        norm_only_selective = sorted(t for t in norm_only if tag_df(stem(t)) < 500)
        r["norm_only_matches"] = norm_only
        r["norm_only_selective_anchors"] = norm_only_selective

        f = {}
        f["delivery_lost"] = bool(
            not r["delivered_gold"] and r["map_rank"] is not None and r["map_rank"] <= 12
        )
        f["passage_boundary"] = r["sibling_best_gain"] >= 2
        f["vocabulary_mismatch"] = r["frac_qword_norm"] < 0.50
        f["title_path_addressable"] = (
            r["filename_stem_matched_terms"] >= 2 or r["filename_stem_cov_best"] >= 0.33
        )
        f["phrase_addressable"] = r["n_trigram_hits"] >= 1 or r["n_bigram_hits"] >= 6
        f["normalization_addressable"] = len(norm_only_selective) >= 1
        f["structured_kv_addressable"] = len(r["gold_kv_key_terms_matched"]) >= 2
        f["code_symbol_register"] = bool(r["q_has_code_symbol"]) and r["gold_code_density"] >= 0.20
        f["date_seeking"] = bool(r["q_has_date_cue"]) and r["gold_date_literals"] >= 1
        f["number_seeking"] = bool(r["q_has_num_cue"])
        f["anchor_selectivity_deficit"] = r["min_tag_df_of_kw_anchors"] >= 200
        f["no_selective_anchor_at_all"] = r["n_selective_anchors_df_lt500"] == 0
        r["flags"] = {k: bool(v) for k, v in f.items()}

        # primary label (priority order; evidence-strength descending)
        if f["delivery_lost"]:
            p = "delivery_lost"
        elif f["passage_boundary"]:
            p = "passage_boundary"
        elif f["vocabulary_mismatch"]:
            p = "vocabulary_mismatch"
        elif f["title_path_addressable"]:
            p = "title_path_signal_unused"
        elif f["phrase_addressable"]:
            p = "phrase_proximity_unused"
        elif f["normalization_addressable"]:
            p = "normalization_gap"
        elif f["structured_kv_addressable"]:
            p = "structured_kv_unused"
        elif f["anchor_selectivity_deficit"] or f["no_selective_anchor_at_all"]:
            p = "anchor_selectivity_deficit"
        else:
            p = "other_unclassified"
        r["primary_mode"] = p

    miss = [r for r in rows if not r["delivered_gold"]]
    hit = [r for r in rows if r["delivered_gold"]]
    cohort = [r for r in rows if r["map_rank"] and 6 <= r["map_rank"] <= 12]

    def bucket(r):
        m = r["map_rank"]
        if m is None:
            return "absent"
        return "<=12" if m <= 12 else "13-30" if m <= 30 else "31-100" if m <= 100 else ">100"

    agg = {
        "n_basic": len(rows),
        "n_delivered_hits": len(hit),
        "n_misses": len(miss),
        "map_recall": {
            "r@2": sum(1 for r in rows if r["map_rank"] and r["map_rank"] <= 2),
            "r@5": sum(1 for r in rows if r["map_rank"] and r["map_rank"] <= 5),
            "r@12": sum(1 for r in rows if r["map_rank"] and r["map_rank"] <= 12),
            "gold_found_anywhere": sum(1 for r in rows if r["map_rank"]),
        },
        "miss_rank_buckets": dict(Counter(bucket(r) for r in miss)),
        "primary_mode_counts_misses": dict(Counter(r["primary_mode"] for r in miss)),
        "primary_mode_counts_by_bucket": {
            b: dict(Counter(r["primary_mode"] for r in miss if bucket(r) == b))
            for b in ("absent", "13-30", "31-100", "<=12")
        },
        "flag_counts_misses": {
            k: sum(1 for r in miss if r["flags"][k]) for k in miss[0]["flags"]
        },
        "flag_counts_rank6_12": {
            k: sum(1 for r in cohort if r["flags"][k]) for k in cohort[0]["flags"]
        },
        "n_rank6_12": len(cohort),
        "rank6_12_needles": [r["needle"] for r in cohort],
        "rank6_12_phrase": {
            "with_exact_trigram": sum(1 for r in cohort if r["n_trigram_hits"] >= 1),
            "with_ge6_bigrams": sum(1 for r in cohort if r["n_bigram_hits"] >= 6),
            "with_ge1_bigram": sum(1 for r in cohort if r["n_bigram_hits"] >= 1),
            "with_filename_ge2_terms": sum(
                1 for r in cohort if r["filename_stem_matched_terms"] >= 2
            ),
            "with_selective_anchor_lt500": sum(
                1 for r in cohort if r["n_selective_anchors_df_lt500"] >= 1
            ),
        },
    }

    import statistics as st

    def med(g, k):
        v = [r[k] for r in g if r.get(k) is not None]
        return round(st.median(v), 3) if v else None

    metrics = [
        "frac_content", "frac_content_norm", "frac_qword_raw", "frac_qword_norm",
        "filename_stem_cov_best", "filename_stem_matched_terms",
        "min_tag_df_of_kw_anchors", "min_tag_df_of_qword_anchors",
        "n_selective_anchors_df_lt500", "frac_anchors_saturated",
        "n_bigram_hits", "n_trigram_hits", "gold_kv_line_density",
        "gold_code_density", "gold_table_row_count", "gold_date_literals",
        "sibling_best_gain",
    ]
    top5 = [r for r in rows if r["map_rank"] and r["map_rank"] <= 5]
    agg["medians"] = {
        m: {
            "delivered_hits": med(hit, m),
            "misses": med(miss, m),
            "misses_absent": med([r for r in miss if r["map_rank"] is None], m),
            "rank_le5": med(top5, m),
            "rank_6_12": med(cohort, m),
        }
        for m in metrics
    }

    slim_keys = [
        "needle", "query", "map_rank", "final_rank", "delivered_gold", "delivered_count",
        "primary_mode", "flags", "n_gold", "gold_ids", "source_ids", "gold_content_len",
        "n_kw", "frac_content", "frac_content_norm", "frac_qword_raw", "frac_qword_norm",
        "hit_content", "kw_missing_everywhere", "norm_only_matches",
        "norm_only_selective_anchors", "filename_stem_best", "filename_stem_cov_best",
        "filename_stem_matched_terms", "min_tag_df_of_kw_anchors",
        "min_tag_df_of_qword_anchors", "n_selective_anchors_df_lt500",
        "n_saturated_anchors", "frac_anchors_saturated", "kw_content_hits_saturated_df",
        "kw_content_hits_rare_df", "n_bigram_hits", "n_trigram_hits",
        "phrase_trigrams_verbatim", "phrase_bigrams_verbatim", "sibling_count",
        "sibling_best_gain", "sibling_recovered_kws", "gold_kv_key_terms_matched",
        "gold_kv_line_density", "gold_table_row_count", "gold_code_density",
        "gold_date_literals", "q_has_date_cue", "q_has_num_cue", "q_has_doc_cue",
        "q_has_code_symbol",
    ]
    out = {
        "tool": "basic-miss-taxonomy",
        "stamp": "2026-08-31",
        "bed": "F:/tmp/erb_blob_v09x.db (947k ERB)",
        "source_receipt": (
            "benchmarks/dogfood/erb/receipts/ladder_v09x_w24_min_delivered_2026-08-28.json"
            " (arm=baseline, shipped floor-12 config)"
        ),
        "needle_class": "basic (question_type == 'basic'), n=175",
        "method_note": (
            "Read-only point reads against the bed (gene_id / filename_stem / tag_value). "
            "Keyword signals from cymatix_context.accel.extract_query_signals. "
            "tag DF is capped at 3001 (promoter_index probe with LIMIT)."
        ),
        "aggregates": agg,
        "rows": [{k: r.get(k) for k in slim_keys} for r in rows],
    }
    p = os.path.join(OUT, "2026-08-31-basic-miss-taxonomy.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("wrote", p)
    print(json.dumps(agg["primary_mode_counts_misses"], indent=1))
    print(json.dumps(agg["flag_counts_misses"], indent=1))
    print(json.dumps(agg["primary_mode_counts_by_bucket"], indent=1))
    print(json.dumps(agg["rank6_12_phrase"], indent=1))
    print(json.dumps(agg["flag_counts_rank6_12"], indent=1))


if __name__ == "__main__":
    main()
