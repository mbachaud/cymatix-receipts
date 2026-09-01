"""Pass 4: tag-leg anchor selectivity + pairwise topical-crowding probe; final labels."""
import json
import os
import re
import sqlite3
import statistics as st
from collections import Counter

BED = "file:F:/tmp/erb_blob_v09x.db?mode=ro"
OUT = r"F:/Projects/cymatix-context/research-inbox"
DF_CAP = 3001
PAIR_CAP = 3001


def main():
    rows = json.load(open(os.path.join(OUT, "_basic_enriched_rows.json"), encoding="utf-8"))
    prev = {
        r["needle"]: r
        for r in json.load(
            open(os.path.join(OUT, "2026-08-31-basic-miss-taxonomy.json"), encoding="utf-8")
        )["rows"]
    }
    for r in rows:
        p = prev[r["needle"]]
        r["flags"] = dict(p["flags"])
        r["gold_ids"] = p["gold_ids"]
        r["norm_only_matches"] = p["norm_only_matches"]
        r["norm_only_selective_anchors"] = p["norm_only_selective_anchors"]
    con = sqlite3.connect(BED, uri=True)
    cur = con.cursor()
    dfc, pairc = {}, {}

    def tag_df(t):
        if t not in dfc:
            dfc[t] = cur.execute(
                "select count(*) from (select 1 from promoter_index where tag_value=? limit ?)",
                (t, DF_CAP),
            ).fetchone()[0]
        return dfc[t]

    def pair_df(a, b):
        k = (a, b) if a < b else (b, a)
        if k not in pairc:
            pairc[k] = cur.execute(
                "select count(*) from (select gene_id from promoter_index where tag_value=?"
                " intersect select gene_id from promoter_index where tag_value=? limit ?)",
                (k[0], k[1], PAIR_CAP),
            ).fetchone()[0]
        return pairc[k]

    for r in rows:
        # anchors that are actually gold PROMOTER TAGS (the tag_exact / tag_prefix legs)
        tag_anchors = sorted(set(r["hit_tags"]))
        tdf = {t: tag_df(t) for t in tag_anchors}
        r["tag_anchors"] = tag_anchors
        r["n_tag_anchors"] = len(tag_anchors)
        r["min_df_tag_anchor"] = min(tdf.values()) if tdf else None
        r["n_selective_tag_anchors_lt500"] = sum(1 for v in tdf.values() if v < 500)
        r["tag_anchor_dfs"] = {k: v for k, v in sorted(tdf.items(), key=lambda x: x[1])[:8]}

        # topical crowding: how many genes carry BOTH of the two most selective
        # query terms that are present in the gold body?
        body = sorted(set(r["hit_content"]))
        bdf = sorted(((tag_df(t), t) for t in body))
        best = [t for _d, t in bdf[:4]]
        pairs = []
        for i in range(len(best)):
            for j in range(i + 1, len(best)):
                pairs.append((pair_df(best[i], best[j]), best[i], best[j]))
        pairs.sort()
        r["best_anchor_pair"] = list(pairs[0][1:]) if pairs else []
        r["best_anchor_pair_cooccurrence"] = pairs[0][0] if pairs else None
        r["top4_anchor_dfs"] = {t: d for d, t in bdf[:4]}

    # ---------------- final labelling ----------------
    for r in rows:
        f = r["flags"]
        co = r["best_anchor_pair_cooccurrence"]
        f["topical_collision"] = bool(co is not None and co >= 50)
        f["tag_leg_blind"] = r["n_selective_tag_anchors_lt500"] == 0
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
        else:
            p = "topical_collision_no_lexical_hook"
        r["primary_mode"] = p

    miss = [r for r in rows if not r["delivered_gold"]]
    hit = [r for r in rows if r["delivered_gold"]]
    cohort = [r for r in rows if r["map_rank"] and 6 <= r["map_rank"] <= 12]
    top5 = [r for r in rows if r["map_rank"] and r["map_rank"] <= 5]

    def med(g, k):
        v = [r[k] for r in g if r.get(k) is not None]
        return round(st.median(v), 3) if v else None

    for lbl, g in (("HIT", hit), ("MISS", miss), ("R<=5", top5), ("R6-12", cohort)):
        print(
            f"{lbl:6s} n={len(g):3d} minDFtag={med(g,'min_df_tag_anchor')}"
            f" nTagAnch={med(g,'n_tag_anchors')} selTag={med(g,'n_selective_tag_anchors_lt500')}"
            f" pairCo={med(g,'best_anchor_pair_cooccurrence')}"
        )
    print()
    print("MISS primary:", dict(Counter(r["primary_mode"] for r in miss)))
    print("MISS flags:", {k: sum(1 for r in miss if r["flags"][k]) for k in miss[0]["flags"]})
    print("R6-12 flags:", {k: sum(1 for r in cohort if r["flags"][k]) for k in cohort[0]["flags"]})
    print("pairCo>=50 rate: hit", round(sum(1 for r in hit if (r['best_anchor_pair_cooccurrence'] or 0) >= 50)/len(hit), 3),
          "miss", round(sum(1 for r in miss if (r['best_anchor_pair_cooccurrence'] or 0) >= 50)/len(miss), 3))

    json.dump(rows, open(os.path.join(OUT, "_basic_final_rows.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print("cached pair probes:", len(pairc), "df:", len(dfc))


if __name__ == "__main__":
    main()
