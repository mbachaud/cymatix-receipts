"""BRIGHT (xlangai/BRIGHT, short-doc split) -> BEIR layout under pulls/beir/bright_<domain>/.

corpus.jsonl {_id, title:"", text}; queries.jsonl {_id, text}; qrels/test.tsv (gold_ids, score 1);
excluded.json {qid: [doc ids]} for the BRIGHT excluded_ids rule.
"""
import ast, json, sys
from pathlib import Path
import pyarrow.parquet as pq
SRC = Path("/home/user/bench/dl/bright"); DST = Path("/home/user/bench/pulls/beir")
def lst(v): return v if isinstance(v, list) else ast.literal_eval(v)
for d in sys.argv[1:]:
    out = DST / f"bright_{d}"; (out / "qrels").mkdir(parents=True, exist_ok=True)
    with open(out / "corpus.jsonl", "w") as f:
        for r in pq.read_table(SRC / f"documents/{d}-00000-of-00001.parquet").to_pylist():
            f.write(json.dumps({"_id": r["id"], "title": "", "text": r["content"]}) + "\n")
    ex = {}
    with open(out / "queries.jsonl", "w") as fq, open(out / "qrels/test.tsv", "w") as fr:
        fr.write("query-id\tcorpus-id\tscore\n")
        for r in pq.read_table(SRC / f"examples/{d}-00000-of-00001.parquet").to_pylist():
            fq.write(json.dumps({"_id": r["id"], "text": r["query"]}) + "\n")
            for g in lst(r["gold_ids"]):
                fr.write(f"{r['id']}\t{g}\t1\n")
            e = [x for x in lst(r["excluded_ids"]) if x != "N/A"]
            if e: ex[r["id"]] = e
    (out / "excluded.json").write_text(json.dumps(ex))
    print(d, "excluded queries:", len(ex))
