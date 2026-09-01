"""Pass 2: enrich the basic-class rows with leg-specific evidence."""
import json
import os
import re
import sqlite3

BED = "file:F:/tmp/erb_blob_v09x.db?mode=ro"
OUT = r"F:/Projects/cymatix-context/research-inbox"
W_NEW = r"F:/Projects/cymatix-context/.claude/worktrees/nostalgic-elion-5304a1"
GOLD = W_NEW + "/benchmarks/dogfood/erb/gold_by_needle_v09x.json"
DF_CAP = 3001
TOK = re.compile(r"[a-z0-9_/\-]+")
WORD = re.compile(r"[a-z0-9]+")
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


def stem_tokens(source_id):
    base = (source_id or "").replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return {t for t in re.split(r"[-_.]", base.lower()) if len(t) > 2}


CODE_RE = re.compile(
    r"```|^\s*\$ |\bgit \w+|\bgh \w+|\bcurl \b|--[a-z][a-z-]+|\b[a-z_]+\([^)]*\)"
    r"|\b[A-Z][A-Z0-9_]{3,}\b|\bv?\d+\.\d+\.\d+\b|\b[a-z]+_[a-z]+_[a-z]+\b",
    re.M,
)
KVLINE_RE = re.compile(r"^\s*[\"']?[A-Za-z_][\w .\-]{0,40}[\"']?\s*[:=]\s*\S", re.M)
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$", re.M)
DATE_LIT_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b",
    re.I,
)


def main():
    rows = json.load(open(os.path.join(OUT, "_basic_raw_rows.json"), encoding="utf-8"))
    gold = json.load(open(GOLD, encoding="utf-8"))
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
        q = r["query"]
        qw = words(q) - STOP
        qw_stem = {stem(t) for t in qw}
        kws = r["kws"]
        kw_stems = {stem(k) for k in kws}

        best_cov, best_n, best_name, covs = 0.0, 0, "", []
        for sid in r["source_ids"]:
            st = stem_tokens(sid)
            if not st:
                continue
            cov = len(st & qw) / len(st)
            covs.append(round(cov, 3))
            if cov > best_cov:
                best_cov, best_n = cov, len(st & qw)
                best_name = sid.replace("\\", "/").rsplit("/", 1)[-1]

        gids = gold.get(r["needle"], [])
        blob, kvs = "", []
        if gids:
            qmarks = ",".join("?" * len(gids))
            for _gid, content, kv in cur.execute(
                f"select gene_id, content, key_values from genes where gene_id in ({qmarks})",
                gids,
            ):
                blob += "\n" + (content or "")
                try:
                    kvs += json.loads(kv) if kv else []
                except Exception:
                    pass

        nlines = max(1, blob.count("\n"))
        kv_keys = set()
        for e in kvs:
            k, _, _v = str(e).partition("=")
            kv_keys |= words(k)
        gold_toks = toks(blob)
        gold_stems = {stem(t) for t in gold_toks}

        anchors = sorted(k for k in kws if k in gold_toks)
        dfs = {k: tag_df(k) for k in anchors}
        min_df = min(dfs.values()) if dfs else DF_CAP
        # selectivity of the *query-word* anchors too (extractor-independent)
        qanchors = sorted(t for t in (qw & gold_toks))
        qdfs = {t: tag_df(t) for t in qanchors}
        q_min_df = min(qdfs.values()) if qdfs else DF_CAP

        r.update(
            {
                "gold_ids": gids,
                "qword_count": len(qw),
                "frac_qword_raw": round(len(qw & gold_toks) / max(1, len(qw)), 3),
                "frac_qword_norm": round(len(qw_stem & gold_stems) / max(1, len(qw_stem)), 3),
                "frac_content_norm": round(len(kw_stems & gold_stems) / max(1, len(kw_stems)), 3),
                "norm_gain_vs_raw": round(
                    len(kw_stems & gold_stems) / max(1, len(kw_stems)) - r["frac_content"], 3
                ),
                "filename_stem_cov_best": round(best_cov, 3),
                "filename_stem_matched_terms": best_n,
                "filename_stem_best": best_name,
                "filename_stem_cov_all": covs,
                "min_tag_df_of_kw_anchors": min_df,
                "min_tag_df_of_qword_anchors": q_min_df,
                "n_selective_anchors_df_lt500": sum(1 for v in dfs.values() if v < 500),
                "n_saturated_anchors": sum(1 for v in dfs.values() if v >= DF_CAP),
                "frac_anchors_saturated": round(
                    sum(1 for v in dfs.values() if v >= DF_CAP) / max(1, len(dfs)), 3
                ),
                "gold_kv_key_terms_matched": sorted(qw & kv_keys),
                "gold_kv_line_count": len(KVLINE_RE.findall(blob)),
                "gold_kv_line_density": round(len(KVLINE_RE.findall(blob)) / nlines, 3),
                "gold_table_row_count": len(TABLE_RE.findall(blob)),
                "gold_code_density": round(len(CODE_RE.findall(blob)) / nlines, 3),
                "gold_date_literals": len(DATE_LIT_RE.findall(blob)),
                "gold_blob_chars": len(blob),
            }
        )

    json.dump(rows, open(os.path.join(OUT, "_basic_enriched_rows.json"), "w",
                         encoding="utf-8"), indent=1, ensure_ascii=False)
    print("enriched", len(rows), "df cache", len(dfc))


if __name__ == "__main__":
    main()
