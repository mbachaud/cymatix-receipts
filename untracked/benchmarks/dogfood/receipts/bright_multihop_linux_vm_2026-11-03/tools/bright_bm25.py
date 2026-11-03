"""Same-corpus BM25 nDCG@10 / R@100 for BRIGHT domains (raw BEIR-layout pulls, excluded_ids removed).
bm25s 0.3.16 lucene k1=1.5 b=0.75, English stopwords, PyStemmer english. Binary qrels, standard nDCG."""
import json, math, sys
from pathlib import Path
import bm25s, Stemmer
P = Path("/home/user/bench/pulls/beir"); out = {}
for d in sys.argv[1].split(","):
    p = P / f"bright_{d}"
    docs = [json.loads(l) for l in open(p / "corpus.jsonl")]
    ids = [x["_id"] for x in docs]
    qs = {(q := json.loads(l))["_id"]: q["text"] for l in open(p / "queries.jsonl")}
    rel = {}
    for i, l in enumerate(open(p / "qrels" / "test.tsv")):
        a = l.rstrip("\n").split("\t")
        if i == 0 and not a[-1].lstrip("-").isdigit(): continue
        if int(a[2]) > 0: rel.setdefault(a[0], set()).add(a[1])
    ex = json.loads((p / "excluded.json").read_text()) if (p / "excluded.json").exists() else {}
    stem = Stemmer.Stemmer("english")
    idx = bm25s.BM25(k1=1.5, b=0.75, method="lucene")
    idx.index(bm25s.tokenize([(x.get("title", "") + " " + x["text"]).strip() for x in docs], stopwords="en", stemmer=stem, show_progress=False), show_progress=False)
    names = [q for q in rel if q in qs]
    kmax = 100 + max([len(v) for v in ex.values()] or [0])
    kmax = min(kmax, len(ids))
    res, _ = idx.retrieve(bm25s.tokenize([qs[q] for q in names], stopwords="en", stemmer=stem, show_progress=False), k=kmax, show_progress=False, n_threads=4)
    nd, rc = [], []
    for q, row in zip(names, res):
        e = set(ex.get(q, [])); g = rel[q] - e
        top = [ids[j] for j in row if ids[j] not in e][:100]
        if not g: continue
        dcg = sum(1 / math.log2(i + 2) for i, x in enumerate(top[:10]) if x in g)
        idcg = sum(1 / math.log2(i + 2) for i in range(min(len(g), 10)))
        nd.append(dcg / idcg); rc.append(len(g & set(top)) / len(g))
    out[d] = {"n": len(nd), "bm25_ndcg@10": round(sum(nd) / len(nd), 4), "bm25_recall@100": round(sum(rc) / len(rc), 4)}
    print(d, out[d], flush=True)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + "\n")
