"""Decompose ERB 'basic'-class misses (947k bed) into concrete failure modes.

Read-only: point reads by gene_id / filename_stem / tag_value only.
Outputs to research-inbox/ only.
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"F:/Projects/cymatix-context/.claude/worktrees/nostalgic-elion-5304a1")
from cymatix_context.accel import extract_query_signals  # noqa: E402

W_NEW = r"F:/Projects/cymatix-context/.claude/worktrees/nostalgic-elion-5304a1"
RECEIPT = (
    r"F:/Projects/cymatix-context/.claude/worktrees/wave-1-semantic-ranking-5f1dab"
    r"/benchmarks/dogfood/erb/receipts/ladder_v09x_w24_min_delivered_2026-08-28.json"
)
NEEDLES = W_NEW + "/benchmarks/dogfood/erb/needles_resolved_v09x_full.json"
GOLD = W_NEW + "/benchmarks/dogfood/erb/gold_by_needle_v09x.json"
BED = "file:F:/tmp/erb_blob_v09x.db?mode=ro"
OUT = r"F:/Projects/cymatix-context/research-inbox"

TOK = re.compile(r"[a-z0-9_/\-]+")
WORD = re.compile(r"[a-z0-9]+")
DF_CAP = 3001

MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "jan", "feb", "mar", "apr",
    "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}
DATE_CUES = {
    "when", "date", "dated", "deadline", "due", "timeline", "schedule", "scheduled",
    "eta", "expires", "expiry", "expiration", "effective", "start", "end", "cutoff",
    "window", "timestamp", "quarter", "fy", "day", "week", "month", "year",
}
NUM_CUES = {
    "how", "many", "much", "limit", "limits", "size", "count", "number", "percent",
    "percentage", "threshold", "rate", "price", "cost", "amount", "total", "value",
    "quota", "max", "maximum", "min", "minimum", "budget", "seats", "headcount",
    "discount", "duration", "timeout", "ms", "gb", "mb",
}
DOC_CUES = {
    "file", "document", "doc", "ticket", "issue", "thread", "channel", "email",
    "message", "note", "notes", "report", "deck", "pdf", "spreadsheet", "sheet",
    "record", "page", "attachment", "runbook", "playbook", "memo", "readme",
    "changelog", "log", "transcript", "meeting", "call", "review", "postmortem",
}


def toks(s):
    if not s:
        return set()
    return {t for t in TOK.findall(s.lower()) if len(t) > 2}


def words(s):
    if not s:
        return set()
    return {t for t in WORD.findall(s.lower()) if len(t) > 2}


def path_tokens(source_id):
    if not source_id:
        return set()
    s = source_id.lower().replace("\\", "/")
    parts = re.split(r"[/.]", s)
    out = set()
    for p in parts:
        if len(p) > 2:
            out.add(p)
        out |= {t for t in re.split(r"[-_]", p) if len(t) > 2}
    return out


def stem_of(source_id):
    if not source_id:
        return ""
    base = source_id.replace("\\", "/").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0]


def ngrams(seq, n):
    return {" ".join(seq[i:i + n]) for i in range(len(seq) - n + 1)}


class Bed:
    def __init__(self):
        self.con = sqlite3.connect(BED, uri=True)
        self.cur = self.con.cursor()
        self.df_cache = {}
        self.gene_cache = {}

    def gene(self, gid):
        if gid in self.gene_cache:
            return self.gene_cache[gid]
        r = self.cur.execute(
            "select gene_id, content, promoter, source_id, key_values, source_kind,"
            " support_span, authority_class from genes where gene_id=?",
            (gid,),
        ).fetchone()
        if r is None:
            self.gene_cache[gid] = None
            return None
        gid_, content, promoter, source_id, kv, kind, span, auth = r
        try:
            prom = json.loads(promoter) if promoter else {}
        except Exception:
            prom = {}
        try:
            kvs = json.loads(kv) if kv else []
        except Exception:
            kvs = []
        d = {
            "gene_id": gid_,
            "content": content or "",
            "domains": [str(x) for x in prom.get("domains", []) or []],
            "entities": [str(x) for x in prom.get("entities", []) or []],
            "intent": str(prom.get("intent", "") or ""),
            "source_id": source_id or "",
            "key_values": [str(x) for x in kvs],
            "source_kind": kind,
            "support_span": span,
            "authority_class": auth,
        }
        self.gene_cache[gid] = d
        return d

    def siblings(self, gid, source_id):
        stem = stem_of(source_id)
        if not stem:
            return []
        rows = self.cur.execute(
            "select gene_id from filename_index where filename_stem=? limit 60", (stem,)
        ).fetchall()
        return [r[0] for r in rows if r[0] != gid]

    def tag_df(self, term):
        if term in self.df_cache:
            return self.df_cache[term]
        n = self.cur.execute(
            "select count(*) from (select 1 from promoter_index where tag_value=? limit ?)",
            (term, DF_CAP),
        ).fetchone()[0]
        self.df_cache[term] = n
        return n


def main():
    d = json.load(open(RECEIPT, encoding="utf-8"))
    pq = {r["needle"]: r for r in d["arms"][0]["per_query"]}
    needles = json.load(open(NEEDLES, encoding="utf-8"))["needles"]
    gold = json.load(open(GOLD, encoding="utf-8"))
    basic = [x for x in needles if x.get("question_type") == "basic"]
    bed = Bed()

    rows = []
    for nd in basic:
        name = nd["name"]
        q = nd["query"]
        rec = pq.get(name, {})
        mr = rec.get("rank_of_first_gold")
        fr = rec.get("final_rank_of_first_gold")
        dg = int(rec.get("delivered_gold") or 0)
        gids = gold.get(name, [])
        genes = [g for g in (bed.gene(x) for x in gids) if g]

        doms, ents = extract_query_signals(q)
        kws = sorted({str(k).lower() for k in list(doms) + list(ents) if len(str(k)) > 2})

        # gold field token sets (union across gold genes)
        c_tok, t_tok, p_tok, kvk_tok, kvv_tok, i_tok = set(), set(), set(), set(), set(), set()
        gold_lens = []
        src_ids = []
        kinds = []
        for g in genes:
            c_tok |= toks(g["content"])
            t_tok |= toks(" ".join(g["domains"] + g["entities"]))
            p_tok |= path_tokens(g["source_id"])
            i_tok |= toks(g["intent"])
            for kv in g["key_values"]:
                k, _, v = kv.partition("=")
                kvk_tok |= toks(k)
                kvv_tok |= toks(v)
            gold_lens.append(len(g["content"]))
            src_ids.append(g["source_id"])
            kinds.append(g["source_kind"])

        def hits(tset):
            return [k for k in kws if k in tset]

        h_c, h_t, h_p, h_kvk, h_kvv, h_i = (
            hits(c_tok), hits(t_tok), h_p_ := hits(p_tok), hits(kvk_tok),
            hits(kvv_tok), hits(i_tok),
        )
        h_p = h_p_
        any_tok = c_tok | t_tok | p_tok | kvk_tok | kvv_tok | i_tok
        h_any = hits(any_tok)
        missing = [k for k in kws if k not in any_tok]
        missing_from_content = [k for k in kws if k not in c_tok]

        n_kw = len(kws) or 1

        # sibling / passage-boundary probe
        sib_recover = set()
        sib_n = 0
        sib_best_gain = 0
        for g in genes[:4]:
            sibs = bed.siblings(g["gene_id"], g["source_id"])
            sib_n += len(sibs)
            for sgid in sibs[:12]:
                sg = bed.gene(sgid)
                if not sg:
                    continue
                st = toks(sg["content"]) | toks(" ".join(sg["domains"] + sg["entities"]))
                rec_here = [k for k in missing_from_content if k in st]
                if len(rec_here) > sib_best_gain:
                    sib_best_gain = len(rec_here)
                sib_recover |= set(rec_here)

        # tag DF (crowding) for the kws that DO hit gold content
        dfs = {k: bed.tag_df(k) for k in h_c}
        capped = [k for k, v in dfs.items() if v >= DF_CAP]
        rare = [k for k, v in dfs.items() if v < 200]
        median_df = 0
        if dfs:
            vv = sorted(dfs.values())
            median_df = vv[len(vv) // 2]

        # phrase evidence: exact query bigrams / trigrams verbatim in gold content
        qw = [t for t in WORD.findall(q.lower())]
        qbi, qtri = ngrams(qw, 2), ngrams(qw, 3)
        gold_blob = " ".join(" ".join(WORD.findall(g["content"].lower())) for g in genes)
        bi_hit = sorted(b for b in qbi if b in gold_blob)
        tri_hit = sorted(t for t in qtri if t in gold_blob)

        qwset = words(q)
        row = {
            "needle": name,
            "query": q,
            "map_rank": mr,
            "final_rank": fr,
            "delivered_gold": dg,
            "delivered_count": rec.get("delivered_count"),
            "n_gold": len(gids),
            "gold_present_in_bed": len(genes),
            "gold_content_len": gold_lens,
            "source_ids": src_ids,
            "source_kinds": kinds,
            "n_kw": len(kws),
            "kws": kws,
            "hit_content": h_c,
            "hit_tags": h_t,
            "hit_path": h_p,
            "hit_kv_key": h_kvk,
            "hit_kv_val": h_kvv,
            "hit_intent": h_i,
            "frac_content": round(len(h_c) / n_kw, 3),
            "frac_tags": round(len(h_t) / n_kw, 3),
            "frac_path": round(len(h_p) / n_kw, 3),
            "frac_any": round(len(h_any) / n_kw, 3),
            "kw_missing_everywhere": missing,
            "sibling_count": sib_n,
            "sibling_recovered_kws": sorted(sib_recover),
            "sibling_best_gain": sib_best_gain,
            "tag_df_median_of_content_hits": median_df,
            "kw_content_hits_saturated_df": sorted(capped),
            "kw_content_hits_rare_df": sorted(rare),
            "phrase_bigrams_verbatim": bi_hit,
            "phrase_trigrams_verbatim": tri_hit,
            "n_bigram_hits": len(bi_hit),
            "n_trigram_hits": len(tri_hit),
            "q_has_date_cue": bool(qwset & (MONTHS | DATE_CUES)) or bool(
                re.search(r"\b(19|20|21)\d{2}\b|\bq[1-4]\b|\d{4}-\d{2}-\d{2}", q.lower())
            ),
            "q_has_num_cue": bool(qwset & NUM_CUES) or bool(re.search(r"\d", q)),
            "q_has_doc_cue": bool(qwset & DOC_CUES),
            "q_has_code_symbol": bool(
                re.search(r"[a-z]+_[a-z]+|\.(py|json|ya?ml|md|ts|tsx|js|toml|sh|sql|csv|pdf)\b"
                          r"|[a-z]+\.[a-z]+\(|\b[A-Z]{2,}_[A-Z]{2,}\b|\bv\d+\.\d+", q)
            ),
        }
        rows.append(row)

    json.dump(rows, open(os.path.join(OUT, "_basic_raw_rows.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print("wrote raw rows", len(rows))

    miss = [r for r in rows if not r["delivered_gold"]]
    print("misses", len(miss))
    b = Counter()
    for r in miss:
        m = r["map_rank"]
        b["absent" if m is None else "<=12" if m <= 12 else "13-30" if m <= 30
          else "31-100" if m <= 100 else ">100"] += 1
    print(dict(b))


if __name__ == "__main__":
    main()
