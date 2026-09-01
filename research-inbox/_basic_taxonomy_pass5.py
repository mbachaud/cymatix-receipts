"""Pass 5: true corpus body-DF (FTS, capped) for term anchors and for verbatim query
phrases present in gold. This is the selectivity measure that actually matches the
dominant retrieval leg (FTS5 BM25 over the flattened source_id+tags+content field)."""
import json
import os
import re
import sqlite3
import statistics as st
import time
from collections import Counter

BED = "file:F:/tmp/erb_blob_v09x.db?mode=ro"
OUT = r"F:/Projects/cymatix-context/research-inbox"
CAP = 3001
MAX_TRI, MAX_BI = 12, 16
FTS_SAFE = re.compile(r"^[a-z0-9 \-_]+$")


def main():
    rows = json.load(open(os.path.join(OUT, "_basic_final_rows.json"), encoding="utf-8"))
    con = sqlite3.connect(BED, uri=True)
    cur = con.cursor()
    cache = {}
    t0 = time.time()

    def body_df(expr):
        if expr in cache:
            return cache[expr]
        if not FTS_SAFE.match(expr):
            cache[expr] = None
            return None
        try:
            n = cur.execute(
                "select count(*) from (select rowid from genes_fts where genes_fts match ?"
                " limit ?)",
                ('content: "' + expr + '"', CAP),
            ).fetchone()[0]
        except Exception:
            n = None
        cache[expr] = n
        return n

    for i, r in enumerate(rows):
        anchors = sorted(set(r["hit_content"]))
        adf = {a: body_df(a) for a in anchors}
        adf = {k: v for k, v in adf.items() if v is not None}
        r["body_df_anchors"] = dict(sorted(adf.items(), key=lambda x: x[1])[:10])
        r["min_body_df_anchor"] = min(adf.values()) if adf else None
        r["n_body_anchors_lt500"] = sum(1 for v in adf.values() if v < 500)
        r["n_body_anchors_lt50"] = sum(1 for v in adf.values() if v < 50)
        r["frac_body_anchors_saturated"] = (
            round(sum(1 for v in adf.values() if v >= CAP) / len(adf), 3) if adf else None
        )

        tris = r["phrase_trigrams_verbatim"][:MAX_TRI]
        bis = r["phrase_bigrams_verbatim"][:MAX_BI]
        tdf = {t: body_df(t) for t in tris}
        tdf = {k: v for k, v in tdf.items() if v is not None}
        bdf = {b: body_df(b) for b in bis}
        bdf = {k: v for k, v in bdf.items() if v is not None}
        r["min_body_df_trigram"] = min(tdf.values()) if tdf else None
        r["min_body_df_bigram"] = min(bdf.values()) if bdf else None
        r["best_trigram"] = min(tdf, key=tdf.get) if tdf else None
        r["best_bigram"] = min(bdf, key=bdf.get) if bdf else None
        best_phrase = None
        for dd in (tdf, bdf):
            for k, v in dd.items():
                if best_phrase is None or v < best_phrase[1]:
                    best_phrase = (k, v)
        r["best_phrase"] = best_phrase[0] if best_phrase else None
        r["min_body_df_phrase"] = best_phrase[1] if best_phrase else None
        r["phrase_selectivity_gain"] = (
            round(r["min_body_df_anchor"] / max(1, best_phrase[1]), 1)
            if (best_phrase and r["min_body_df_anchor"] is not None)
            else None
        )
        if i % 25 == 0:
            print(i, round(time.time() - t0, 1), "s, cache", len(cache), flush=True)

    json.dump(rows, open(os.path.join(OUT, "_basic_final_rows.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)

    miss = [r for r in rows if not r["delivered_gold"]]
    hit = [r for r in rows if r["delivered_gold"]]
    coh = [r for r in rows if r["map_rank"] and 6 <= r["map_rank"] <= 12]
    top5 = [r for r in rows if r["map_rank"] and r["map_rank"] <= 5]

    def med(g, k):
        v = [r[k] for r in g if r.get(k) is not None]
        return round(st.median(v), 1) if v else None

    for lbl, g in (("HIT", hit), ("MISS", miss), ("R<=5", top5), ("R6-12", coh)):
        print(
            f"{lbl:6s} n={len(g):3d} minBodyDFterm={med(g,'min_body_df_anchor')}"
            f" nLt500={med(g,'n_body_anchors_lt500')} nLt50={med(g,'n_body_anchors_lt50')}"
            f" minBodyDFphrase={med(g,'min_body_df_phrase')}"
            f" gain={med(g,'phrase_selectivity_gain')}"
        )
    print()
    for lbl, g in (("HIT", hit), ("MISS", miss), ("R6-12", coh)):
        print(
            lbl,
            "phrase<=50:", sum(1 for r in g if (r["min_body_df_phrase"] or 10**9) <= 50),
            "phrase<=200:", sum(1 for r in g if (r["min_body_df_phrase"] or 10**9) <= 200),
            "term<=50:", sum(1 for r in g if (r["min_body_df_anchor"] or 10**9) <= 50),
            "n:", len(g),
        )
    print("elapsed", round(time.time() - t0, 1))


if __name__ == "__main__":
    main()
