"""Multi-hop scoring for pooled-corpus beds: does the packet carry ALL supporting paragraphs?

Per needle (doc level; a doc counts when any of its genes appears):
  all@10 / all@100   every gold doc within the first 10 / 100 distinct docs of score_ranked_ids
  all_delivered      every gold doc among delivered_gene_ids (the 12-item packet)
  frac_delivered     share of gold docs delivered (coverage, as in the pruning post)
Plus a BM25 baseline (bm25s, English stopwords + Snowball stemmer, k1=1.5 b=0.75 lucene)
on the same corpus files: all@10 / all@100 / all@12 (the packet size).
"""
import argparse, json, sqlite3, statistics
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--tag"); ap.add_argument("--ladder"); ap.add_argument("--db")
ap.add_argument("--bench-dir"); ap.add_argument("--corpus-root"); ap.add_argument("--out")
a = ap.parse_args()
root = Path(a.corpus_root); bench = Path(a.bench_dir)
gold_paths = json.loads((bench / f"gold_paths_{a.tag}.json").read_text())
needles = {n["name"]: n["query"] for n in json.loads((bench / f"needles_{a.tag}.json").read_text())["needles"]}

conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
doc_of = {}
for gid, sid in conn.execute("SELECT gene_id, source_id FROM genes"):
    try: doc_of[gid] = Path(sid).relative_to(root).as_posix()
    except Exception: pass

lad = json.loads(Path(a.ladder).read_text()); arm = lad["arms"]
arm = arm[0] if isinstance(arm, list) else next(iter(arm.values()))
def L(v): return v if isinstance(v, list) else (json.loads(v.replace("'", '"')) if isinstance(v, str) and v.startswith("[") else [])
def docs(ids, n=None):
    out = []
    for g in ids:
        d = doc_of.get(g)
        if d and d not in out:
            out.append(d)
            if n and len(out) >= n: break
    return out

rows = []
for q in arm["per_query"]:
    gold = set(gold_paths.get(q["needle"], []))
    if not gold: continue
    ranked = docs(L(q.get("score_ranked_ids") or []))
    deliv = set(docs(L(q.get("delivered_gene_ids") or [])))
    rows.append({"needle": q["needle"], "n_gold": len(gold),
                 "all@10": gold <= set(ranked[:10]), "all@100": gold <= set(ranked[:100]),
                 "all_delivered": gold <= deliv, "any_delivered": bool(gold & deliv),
                 "frac_delivered": len(gold & deliv) / len(gold),
                 "delivered_chars": int(q.get("delivered_chars") or 0)})

# BM25 baseline over the same emitted files
import bm25s, Stemmer
files = sorted(p for p in root.rglob("*.txt"))
rels = [p.relative_to(root).as_posix() for p in files]
stem = Stemmer.Stemmer("english")
idx = bm25s.BM25(k1=1.5, b=0.75, method="lucene")
idx.index(bm25s.tokenize([p.read_text(errors="replace") for p in files], stopwords="en", stemmer=stem, show_progress=False), show_progress=False)
names = [r["needle"] for r in rows]
res, _ = idx.retrieve(bm25s.tokenize([needles[n] for n in names], stopwords="en", stemmer=stem, show_progress=False), k=100, show_progress=False, n_threads=4)
for r, hits in zip(rows, res):
    top = [rels[i] for i in hits]; gold = set(gold_paths[r["needle"]])
    r["bm25_all@10"] = gold <= set(top[:10]); r["bm25_all@12"] = gold <= set(top[:12]); r["bm25_all@100"] = gold <= set(top[:100])
    r["bm25_frac@12"] = len(gold & set(top[:12])) / len(gold)

def m(k): return round(statistics.mean(float(r[k]) for r in rows), 4)
summary = {k: m(k) for k in ("all@10", "all@100", "all_delivered", "any_delivered", "frac_delivered",
                             "bm25_all@10", "bm25_all@12", "bm25_all@100", "bm25_frac@12")}
summary["delivered_chars_median"] = statistics.median(r["delivered_chars"] for r in rows)
summary["n"] = len(rows)
Path(a.out).write_text(json.dumps({"tag": a.tag, "ladder": a.ladder, "summary": summary, "per_query": rows}, indent=1))
print(a.tag, summary)
