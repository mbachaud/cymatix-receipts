"""Pooled multi-hop corpora -> BEIR layout under pulls/beir/mh_<name>/.

Corpus = every distinct (title, paragraph) across all dev questions' provided contexts
(HotpotQA distractor 10/q, 2Wiki 10/q, MuSiQue-Ans 20/q). Doc id = sha1(title + text)[:16],
so a paragraph shared by several questions is one document. Gold = that question's supporting
paragraphs (score 1). Not the open-domain setting: numbers compare only to each other.
"""
import ast, hashlib, json, sys
from pathlib import Path
import pyarrow.parquet as pq
SRC = Path("/home/user/bench/dl/mh"); DST = Path("/home/user/bench/pulls/beir")
def lit(v): return ast.literal_eval(v) if isinstance(v, str) else v
def did(title, text): return hashlib.sha1((title + "\x00" + text).encode()).hexdigest()[:16]

def emit(name, items):
    out = DST / f"mh_{name}"; (out / "qrels").mkdir(parents=True, exist_ok=True)
    docs, nq, ng = {}, 0, []
    with open(out / "queries.jsonl", "w") as fq, open(out / "qrels/test.tsv", "w") as fr:
        fr.write("query-id\tcorpus-id\tscore\n")
        for qid, question, paras, gold_idx in items:
            ids = []
            for title, text in paras:
                i = did(title, text); docs.setdefault(i, (title, text)); ids.append(i)
            gold = sorted({ids[k] for k in gold_idx})
            if not gold: continue
            fq.write(json.dumps({"_id": qid, "text": question}) + "\n"); nq += 1; ng.append(len(gold))
            for g in gold: fr.write(f"{qid}\t{g}\t1\n")
    with open(out / "corpus.jsonl", "w") as f:
        for i, (t, x) in docs.items(): f.write(json.dumps({"_id": i, "title": t, "text": x}) + "\n")
    print(name, "docs", len(docs), "queries", nq, "gold/q", round(sum(ng) / len(ng), 2))

def wiki_style(rows):          # HotpotQA / 2Wiki: context {title[], sentences[][]}, supporting_facts {title[]}
    for r in rows:
        c, sf = lit(r["context"]), lit(r["supporting_facts"])
        paras = [(t, "".join(s) if "hotpot" in r.get("_src", "") else " ".join(s)) for t, s in zip(c["title"], c["sentences"])]
        st = set(sf["title"])
        yield r["id"], r["question"], paras, [k for k, (t, _) in enumerate(paras) if t in st]

which = sys.argv[1:]
if "hotpotqa" in which:
    rows = pq.read_table(SRC / "distractor/validation-00000-of-00001.parquet").to_pylist()
    for r in rows: r["_src"] = "hotpot"
    emit("hotpotqa", wiki_style(rows))
if "2wiki" in which:
    emit("2wiki", wiki_style(pq.read_table(SRC / "data/validation-00000-of-00001.parquet").to_pylist()))
if "musique" in which:
    def mus():
        for line in open(SRC / "musique_ans_v1.0_dev.jsonl"):
            r = json.loads(line); ps = lit(r["paragraphs"])
            yield r["id"], r["question"], [(p["title"], p["paragraph_text"]) for p in ps], [k for k, p in enumerate(ps) if p.get("is_supporting")]
    emit("musique", mus())
