"""Final: assign evidence-grounded modes, compute leg headroom, emit both deliverables."""
import json
import os
import statistics as st
from collections import Counter

OUT = r"F:/Projects/cymatix-context/research-inbox"


def med(g, k):
    v = [r[k] for r in g if r.get(k) is not None]
    return round(st.median(v), 1) if v else None


def main():
    rows = json.load(open(os.path.join(OUT, "_basic_final_rows.json"), encoding="utf-8"))

    for r in rows:
        pdf = r.get("min_body_df_phrase")
        fn_n, fn_files = r.get("fn_n_matched", 0), r.get("fn_files_matching_all")
        tdf = r.get("min_body_df_anchor")
        a = {
            "phrase_leg_strict": pdf is not None and pdf <= 50,
            "phrase_leg_loose": pdf is not None and pdf <= 200,
            "title_path_leg_strict": fn_n >= 2 and fn_files is not None and fn_files <= 20,
            "title_path_leg_loose": fn_n >= 2 and fn_files is not None and fn_files <= 100,
            "normalization_leg": len(r.get("norm_only_selective_anchors") or []) >= 1,
            "fielded_kv_leg": len(r.get("gold_kv_key_terms_matched") or []) >= 2,
            "assembly_width_leg": bool(
                not r["delivered_gold"] and r["map_rank"] is not None and r["map_rank"] <= 12
            ),
            "structure_parent_leg": r.get("sibling_best_gain", 0) >= 2,
        }
        r["addressable_by"] = a
        r["has_any_deterministic_hook_strict"] = bool(
            a["phrase_leg_strict"] or a["title_path_leg_strict"] or a["assembly_width_leg"]
        )
        r["has_any_deterministic_hook_loose"] = bool(
            a["phrase_leg_loose"] or a["title_path_leg_loose"] or a["assembly_width_leg"]
            or a["normalization_leg"]
        )

        # descriptive mode
        if a["assembly_width_leg"]:
            m = "delivery_lost_classifier_cap"
        elif a["structure_parent_leg"]:
            m = "passage_boundary"
        elif r["frac_qword_norm"] < 0.50:
            m = "vocabulary_gap"
        elif fn_n >= 2:
            m = "title_path_named_doc"
        elif tdf is None or tdf >= 500:
            m = "literal_fact_generic_terms"
        else:
            m = "selective_term_present_but_unranked"
        r["primary_mode"] = m
        r["descriptors"] = {
            "date_seeking": bool(r["q_has_date_cue"]) and r["gold_date_literals"] >= 1,
            "number_seeking": bool(r["q_has_num_cue"]),
            "code_symbol_register": bool(r["q_has_code_symbol"]) and r["gold_code_density"] >= 0.20,
            "structured_kv_body": r["gold_kv_line_density"] >= 0.30,
            "multi_gold": r["n_gold"] > 1,
            "chunk_truncated_gold": any(L >= 3990 for L in r["gold_content_len"]),
        }

    miss = [r for r in rows if not r["delivered_gold"]]
    hit = [r for r in rows if r["delivered_gold"]]
    coh = [r for r in rows if r["map_rank"] and 6 <= r["map_rank"] <= 12]
    top5 = [r for r in rows if r["map_rank"] and r["map_rank"] <= 5]
    absent = [r for r in miss if r["map_rank"] is None]
    tail = [r for r in miss if r["map_rank"] is not None and r["map_rank"] > 12]

    def bucket(r):
        m = r["map_rank"]
        if m is None:
            return "absent"
        return "<=12" if m <= 12 else "13-30" if m <= 30 else "31-100" if m <= 100 else ">100"

    legs = list(rows[0]["addressable_by"].keys())
    agg = {
        "n_basic": 175,
        "n_delivered_hits": len(hit),
        "n_misses": len(miss),
        "map_recall": {
            "r@2": sum(1 for r in rows if r["map_rank"] and r["map_rank"] <= 2),
            "r@5": sum(1 for r in rows if r["map_rank"] and r["map_rank"] <= 5),
            "r@12": sum(1 for r in rows if r["map_rank"] and r["map_rank"] <= 12),
            "gold_found_anywhere": sum(1 for r in rows if r["map_rank"]),
            "delivered": len(hit),
        },
        "miss_rank_buckets": dict(Counter(bucket(r) for r in miss)),
        "delivery_width": {
            "width6_queries": sum(1 for r in rows if r["delivered_count"] == 6),
            "width12_queries": sum(1 for r in rows if r["delivered_count"] == 12),
            "delivery_lost_all_in_width6": True,
        },
        "primary_mode_counts": {
            "all_175": dict(Counter(r["primary_mode"] for r in rows)),
            "misses_60": dict(Counter(r["primary_mode"] for r in miss)),
            "misses_absent_37": dict(Counter(r["primary_mode"] for r in absent)),
            "misses_rank13_100_18": dict(Counter(r["primary_mode"] for r in tail)),
            "rank6_12_17": dict(Counter(r["primary_mode"] for r in coh)),
        },
        "leg_addressability": {
            "misses_60": {k: sum(1 for r in miss if r["addressable_by"][k]) for k in legs},
            "misses_absent_37": {k: sum(1 for r in absent if r["addressable_by"][k]) for k in legs},
            "misses_rank13_100_18": {k: sum(1 for r in tail if r["addressable_by"][k]) for k in legs},
            "rank6_12_17": {k: sum(1 for r in coh if r["addressable_by"][k]) for k in legs},
            "delivered_hits_115_reference": {
                k: sum(1 for r in hit if r["addressable_by"][k]) for k in legs
            },
        },
        "leg_union": {
            "misses_strict_phrase_or_title": sum(
                1 for r in miss
                if r["addressable_by"]["phrase_leg_strict"] or r["addressable_by"]["title_path_leg_strict"]
            ),
            "misses_strict_both": sum(
                1 for r in miss
                if r["addressable_by"]["phrase_leg_strict"] and r["addressable_by"]["title_path_leg_strict"]
            ),
            "misses_loose_phrase_or_title": sum(
                1 for r in miss
                if r["addressable_by"]["phrase_leg_loose"] or r["addressable_by"]["title_path_leg_loose"]
            ),
            "misses_no_hook_loose": sum(
                1 for r in miss if not r["has_any_deterministic_hook_loose"]
            ),
            "retrieval_misses_55_strict_union": sum(
                1 for r in miss
                if not r["addressable_by"]["assembly_width_leg"]
                and (r["addressable_by"]["phrase_leg_strict"] or r["addressable_by"]["title_path_leg_strict"])
            ),
            "retrieval_misses_55_loose_union": sum(
                1 for r in miss
                if not r["addressable_by"]["assembly_width_leg"]
                and (r["addressable_by"]["phrase_leg_loose"] or r["addressable_by"]["title_path_leg_loose"])
            ),
        },
        "descriptor_counts_misses": {
            k: sum(1 for r in miss if r["descriptors"][k]) for k in rows[0]["descriptors"]
        },
        "descriptor_counts_hits": {
            k: sum(1 for r in hit if r["descriptors"][k]) for k in rows[0]["descriptors"]
        },
    }

    metrics = [
        "frac_content", "frac_content_norm", "frac_qword_raw", "frac_qword_norm",
        "min_body_df_anchor", "n_body_anchors_lt500", "n_body_anchors_lt50",
        "min_body_df_phrase", "min_body_df_trigram", "min_body_df_bigram",
        "phrase_selectivity_gain", "n_bigram_hits", "n_trigram_hits",
        "fn_n_matched", "fn_files_matching_all", "filename_stem_cov_best",
        "min_df_tag_anchor", "n_tag_anchors", "n_selective_tag_anchors_lt500",
        "gold_kv_line_density", "gold_code_density", "gold_table_row_count",
        "gold_date_literals", "sibling_best_gain", "sibling_count",
    ]
    agg["medians"] = {
        m: {
            "delivered_hits_115": med(hit, m),
            "misses_60": med(miss, m),
            "misses_absent_37": med(absent, m),
            "rank_le5_103": med(top5, m),
            "rank_6_12_17": med(coh, m),
        }
        for m in metrics
    }
    agg["counts_with_selective_evidence"] = {
        grp: {
            "n": len(g),
            "term_body_df_le50": sum(1 for r in g if (r["min_body_df_anchor"] or 10**9) <= 50),
            "term_body_df_le500": sum(1 for r in g if (r["min_body_df_anchor"] or 10**9) <= 500),
            "phrase_body_df_le50": sum(1 for r in g if (r["min_body_df_phrase"] or 10**9) <= 50),
            "phrase_body_df_le200": sum(1 for r in g if (r["min_body_df_phrase"] or 10**9) <= 200),
            "filename_ge2_terms": sum(1 for r in g if r["fn_n_matched"] >= 2),
            "filename_ge2_and_le20_files": sum(
                1 for r in g
                if r["fn_n_matched"] >= 2 and (r["fn_files_matching_all"] or 10**9) <= 20
            ),
            "exact_trigram_in_gold": sum(1 for r in g if r["n_trigram_hits"] >= 1),
            "exact_bigram_in_gold": sum(1 for r in g if r["n_bigram_hits"] >= 1),
        }
        for grp, g in (
            ("delivered_hits_115", hit), ("misses_60", miss),
            ("misses_absent_37", absent), ("rank_le5_103", top5), ("rank_6_12_17", coh),
        )
    }

    slim = [
        "needle", "query", "map_rank", "final_rank", "delivered_gold", "delivered_count",
        "primary_mode", "addressable_by", "descriptors", "n_gold", "gold_ids",
        "source_ids", "gold_content_len", "n_kw", "frac_content", "frac_content_norm",
        "frac_qword_raw", "frac_qword_norm", "hit_content", "kw_missing_everywhere",
        "norm_only_matches", "norm_only_selective_anchors",
        "min_body_df_anchor", "body_df_anchors", "n_body_anchors_lt500",
        "n_body_anchors_lt50", "frac_body_anchors_saturated",
        "best_phrase", "min_body_df_phrase", "best_trigram", "min_body_df_trigram",
        "best_bigram", "min_body_df_bigram", "phrase_selectivity_gain",
        "n_bigram_hits", "n_trigram_hits", "phrase_trigrams_verbatim",
        "fn_matched_terms", "fn_n_matched", "fn_files_matching_all",
        "filename_stem_best", "filename_stem_cov_best",
        "tag_anchors", "n_tag_anchors", "min_df_tag_anchor",
        "n_selective_tag_anchors_lt500",
        "gold_kv_key_terms_matched", "gold_kv_line_density", "gold_table_row_count",
        "gold_code_density", "gold_date_literals",
        "sibling_count", "sibling_best_gain", "sibling_recovered_kws",
        "q_has_date_cue", "q_has_num_cue", "q_has_doc_cue", "q_has_code_symbol",
    ]
    out = {
        "tool": "basic-miss-taxonomy",
        "stamp": "2026-08-31",
        "bed": "F:/tmp/erb_blob_v09x.db (947k ERB blob)",
        "source_receipt": (
            "wave-1-semantic-ranking-5f1dab/benchmarks/dogfood/erb/receipts/"
            "ladder_v09x_w24_min_delivered_2026-08-28.json  arm[0]=baseline (shipped config, "
            "w24_min_delivered_12.toml)"
        ),
        "needle_class": "question_type == 'basic', n=175 of 470",
        "method": {
            "keyword_signals": "cymatix_context.accel.extract_query_signals(query)",
            "token_rule": "regex [a-z0-9_/-]+, len>2, lowercase",
            "term_df": (
                "capped FTS5 probe: SELECT count(*) FROM (SELECT rowid FROM genes_fts "
                "WHERE genes_fts MATCH 'content: \"<term>\"' LIMIT 3001). This is the "
                "DOCUMENT frequency over the flattened source_id+tags+content field, i.e. "
                "the field BM25 actually scores. Values of 3001 are censored (>=3001)."
            ),
            "phrase_df": "same probe with a quoted multi-word phrase (FTS5 phrase query)",
            "tag_df": (
                "promoter_index tag_value count, capped at 3001 - measures crowding of the "
                "tag_exact / tag_prefix legs only"
            ),
            "filename_leg": (
                "499,094 distinct filename stems pulled from filename_index; stems tokenized "
                "on [-_.]; fn_files_matching_all = number of distinct corpus filenames "
                "containing ALL query terms that matched the gold filename"
            ),
            "passage_boundary_probe": (
                "siblings of each gold via filename_index(filename_stem); a sibling 'recovers' "
                "a keyword if it carries a query keyword absent from the gold union"
            ),
            "rank_basis": (
                "rank_of_first_gold = rank in the full fused score map (None = gold scored "
                "zero anywhere = pool-absent). delivered_gold = post-budget delivery slice."
            ),
        },
        "caveats": [
            "DF probes are censored at 3001; medians reported as 3001 are lower bounds.",
            "Phrase DF is the MINIMUM over verbatim query n-grams present in gold - it is an "
            "upper bound on what a phrase leg could key on, not a guarantee that an SDM "
            "implementation weights that phrase highest.",
            "extract_query_signals emits plural/singular variants, which inflates n_kw and "
            "deflates frac_content; frac_content_norm / frac_qword_norm are the stem-collapsed "
            "counterparts and should be preferred for coverage claims.",
            "No manager-mediated query was run (a timed arm was live on the bed); per-needle "
            "top-5 interloper identities were NOT available, so the rank 6-12 cohort is "
            "characterized by gold-side evidence only.",
            "fn_files_matching_all counts filenames, not genes; a filename maps to 1-8 genes.",
        ],
        "gold_reachability_check": {
   "cohort": "the 37 pool-absent basic misses (rank_of_first_gold is None)",
   "probe": "6-gram taken from the middle of gold content, run as an FTS5 phrase query",
   "gold_returned_by_probe": 37,
   "n": 37,
   "conclusion": (
    "every pool-absent basic gold IS present and retrievable in genes_fts. "
    "Pool-absence for the basic class is a ranking / candidate-depth failure, "
    "not an indexing or vocabulary-reachability failure."
   ),
  },
        "aggregates": agg,
        "rows": [{k: r.get(k) for k in slim} for r in rows],
    }
    p = os.path.join(OUT, "2026-08-31-basic-miss-taxonomy.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("wrote", p)
    print(json.dumps(agg["primary_mode_counts"], indent=1))
    print(json.dumps(agg["leg_addressability"], indent=1))
    print(json.dumps(agg["leg_union"], indent=1))
    print(json.dumps(agg["counts_with_selective_evidence"], indent=1))


if __name__ == "__main__":
    main()
