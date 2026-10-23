"""jev_239b_packet_know.py — can Jev filter packets and rank knows from misses?

EXPERIMENTAL. Jev (TypeSafe's "System One": typed questions in, calibrated
probabilities out) is a proprietary hosted API, not part of the cymatix
pipeline; nothing here changes retrieval. Follows the 09-27 dogfood pilot
(``jev_packet_qualify.py``, chunk filtering only) and adds the packet-level
know/miss question.

Bed: the #239b delivery-balanced synthetic set (72 needles, three cells),
ingested fresh under a profile TOML (default: the c4000 classcap grain
profile). Ground truth is by construction, computed locally, never sent:

* ``answerable``  gold ingested             -> packet truth = gold delivered
* ``heldout``     gold NOT ingested         -> packet truth = miss
* ``competition`` gold + wrong-answer twin  -> truth = gold delivered (contested)

Per needle, Jev receives the cymatix side as *incoming rankings*: the query
classifier class, each chunk's delivered rank and fused retrieval score, and
the Stage-6 know/miss block. Three typed calls:

1. ``qtype``  — Choice over the typed question sheet (question alone).
2. per delivered chunk — ``answers`` (Noul), ``relevance`` (Score),
   ``typed`` (the sheet row's Noul).
3. per packet — ``packet_answers`` (Noul: does any chunk state the answer?).

Every raw response is cached in the receipt; rerunning onto the same --out
resumes and rescoring needs no credentials (--rescore).

Usage::

    PYTHONHASHSEED=0 python benchmarks/dogfood/jev/jev_239b_packet_know.py --dry
    PYTHONHASHSEED=0 python benchmarks/dogfood/jev/jev_239b_packet_know.py --limit 6
    PYTHONHASHSEED=0 python benchmarks/dogfood/jev/jev_239b_packet_know.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "faithfulness"))

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
MIN_INTERVAL_S = 0.3        # workload budget: >= 300 ms between requests
DEFAULT_PROFILE = "benchmarks/dogfood/grain_ladder/configs/grain_c4000_classcap.toml"

# Typed question sheet, unchanged from the 09-27 pilot so rows compare.
SHEET = {
    "config_value": (
        "The question asks for a configured value, default, port, path or "
        "setting.",
        "Does the chunk state the concrete value or default of the setting "
        "the question asks about?",
    ),
    "code_location": (
        "The question asks where something is implemented or which "
        "file/function does something.",
        "Does the chunk contain the implementation, definition, or a direct "
        "pointer to the file/function the question asks about?",
    ),
    "mechanism": (
        "The question asks how or why a component works.",
        "Does the chunk explain the mechanism or reasoning the question asks "
        "about, not just mention the component?",
    ),
    "history_decision": (
        "The question asks what changed, when, or why a decision was made.",
        "Does the chunk record the change, date, or decision rationale the "
        "question asks about?",
    ),
    "fact_lookup": (
        "The question asks for a named fact, number, or entity not covered "
        "by the other types.",
        "Does the chunk state the specific fact the question asks for?",
    ),
}

RELEVANCE_LEVELS = [
    "Irrelevant: unrelated to the question.",
    "Topical: same subject area, but would not help answer.",
    "Supporting: useful context, but does not state the answer.",
    "Answering: states the answer to the question.",
]


def jev_call(api_key: str, state, questions: dict, last_call: list) -> dict:
    """One Jev request with pacing and backoff on 429/529."""
    body = json.dumps({"model": MODEL, "state": state,
                       "questions": questions}).encode("utf-8")
    for attempt in range(5):
        wait = MIN_INTERVAL_S - (time.monotonic() - last_call[0])
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(
            API_URL, data=body, method="POST",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"})
        last_call[0] = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            if exc.code in (429, 529) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Jev HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Jev unreachable: {exc!r}") from exc
    raise RuntimeError("Jev retries exhausted")


def qtype_questions() -> dict:
    return {"qtype": {
        "type": "choice",
        "instructions": "Which type of question is this?",
        "criteria": {k: v[0] for k, v in SHEET.items()},
    }}


def chunk_questions(qtype: str) -> dict:
    return {
        "answers": {
            "type": "noul",
            "instructions": "Does the chunk state the answer to the question?",
            "criteria": {
                "true": "The answer can be read directly from the chunk.",
                "false": "The answer is absent, only implied, or only the "
                         "topic is mentioned.",
            },
        },
        "relevance": {
            "type": "score",
            "instructions": "How useful is this chunk for answering the "
                            "question?",
            "criteria": RELEVANCE_LEVELS,
        },
        "typed": {
            "type": "noul",
            "instructions": SHEET[qtype][1],
            "criteria": {"true": "Yes.", "false": "No."},
        },
    }


def packet_questions() -> dict:
    return {"packet_answers": {
        "type": "noul",
        "instructions": "The retrieval system delivered this packet of ranked "
                        "chunks for the question, with its own know/miss "
                        "verdict. Does any chunk in the packet state the "
                        "answer to the question?",
        "criteria": {
            "true": "At least one chunk states the answer directly.",
            "false": "No chunk states the answer; the packet only covers the "
                     "topic, the entity's other attributes, or other "
                     "entities.",
        },
    }}


def auroc(scores: list, labels: list):
    """Mann-Whitney AUROC; None when one class is empty."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def confusion(pred: list, truth: list) -> dict:
    tp = sum(p and t for p, t in zip(pred, truth))
    fp = sum(p and not t for p, t in zip(pred, truth))
    fn = sum((not p) and t for p, t in zip(pred, truth))
    tn = sum((not p) and (not t) for p, t in zip(pred, truth))
    n = max(len(pred), 1)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "accuracy": round((tp + tn) / n, 3)}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.strip()


def build_bed(cfg, needles, corpus: Path):
    """Fresh-ingest the 239b bed; returns (manager, gold gene ids, competitor ids)."""
    from cymatix_context.context_manager import CymatixContextManager

    if Path(cfg.genome.path).exists():
        Path(cfg.genome.path).unlink()
    if corpus.exists():
        shutil.rmtree(corpus)
    mgr = CymatixContextManager(cfg)
    gold_ids, comp_ids, n_docs = {}, {}, 0
    for nd in needles:
        cdir = corpus / nd["cell"]
        cdir.mkdir(parents=True, exist_ok=True)
        for j, doc in enumerate(nd["ingest"]):
            fp = cdir / f"{nd['id']}__{j:02d}.md"
            fp.write_text(doc + "\n", encoding="utf-8")
            gids = mgr.ingest(doc, metadata={"source_id": str(fp.resolve())})
            if doc == nd["gold"]:
                gold_ids[nd["id"]] = set(gids)
            elif nd["cell"] == "competition" and j == 1:
                comp_ids[nd["id"]] = set(gids)
            n_docs += 1
    return mgr, gold_ids, comp_ids, n_docs


def summarize(needle_rows: list, chunks: list) -> dict:
    out = {"needles": len(needle_rows), "chunks": len(chunks)}
    truth = [r["truth_know"] for r in needle_rows]

    # Know vs miss: Jev packet verdict vs the cymatix contract.
    jev_p = [r["jev_packet_answers"] for r in needle_rows]
    jev_maxchunk = [r["jev_max_chunk_answers"] for r in needle_rows]
    cym_conf = [r["cymatix"]["know_confidence"] or 0.0 for r in needle_rows]
    cym_top = [r["cymatix"]["top_score"] for r in needle_rows]
    out["know_miss"] = {
        "truth_know": sum(truth), "truth_miss": len(truth) - sum(truth),
        "auroc_jev_packet": auroc(jev_p, truth),
        "auroc_jev_max_chunk": auroc(jev_maxchunk, truth),
        "auroc_cymatix_know_confidence": auroc(cym_conf, truth),
        "auroc_cymatix_top_score": auroc(cym_top, truth),
        "cymatix_contract": confusion(
            [r["cymatix"]["block"] == "know" for r in needle_rows], truth),
        "jev_packet_at_0.5": confusion([p >= 0.5 for p in jev_p], truth),
        "jev_max_chunk_at_0.5": confusion([p >= 0.5 for p in jev_maxchunk], truth),
    }
    by_cell = {}
    for cell in ("answerable", "heldout", "competition"):
        rs = [r for r in needle_rows if r["cell"] == cell]
        if not rs:
            continue
        by_cell[cell] = {
            "n": len(rs),
            "gold_delivered": sum(r["gold_rank"] is not None for r in rs),
            "cymatix_know": sum(r["cymatix"]["block"] == "know" for r in rs),
            "cymatix_miss_reasons": sorted({r["cymatix"]["miss_reason"]
                                            for r in rs if r["cymatix"]["miss_reason"]}),
            "jev_packet_ge_0.5": sum(r["jev_packet_answers"] >= 0.5 for r in rs),
            "jev_packet_mean": round(sum(r["jev_packet_answers"] for r in rs) / len(rs), 3),
        }
    out["by_cell"] = by_cell
    out["qtype_jev"] = {}
    for r in needle_rows:
        out["qtype_jev"][r["qtype"]] = out["qtype_jev"].get(r["qtype"], 0) + 1
    out["qtype_cymatix_classifier"] = {}
    for r in needle_rows:
        c = r["cymatix"]["classifier"]
        out["qtype_cymatix_classifier"][c] = out["qtype_cymatix_classifier"].get(c, 0) + 1

    # Chunk filtering against the strict label (chunk states the gold answer).
    if chunks:
        ys = [c["is_gold"] for c in chunks]
        out["chunk_filter"] = {
            "positives": sum(ys),
            "competitor_chunks": sum(c["is_competitor"] for c in chunks),
            "auroc_answers": auroc([c["jev"]["answers"] for c in chunks], ys),
            "auroc_typed": auroc([c["jev"]["typed"] for c in chunks], ys),
            "auroc_relevance": auroc([c["jev"]["relevance"] for c in chunks], ys),
            "auroc_cymatix_score": auroc([c["cymatix_score"] for c in chunks], ys),
            "auroc_cymatix_inverse_rank": auroc([-c["rank"] for c in chunks], ys),
        }
        comp = [c for c in chunks if c["is_competitor"]]
        if comp:
            out["chunk_filter"]["competitor_mean_answers"] = round(
                sum(c["jev"]["answers"] for c in comp) / len(comp), 3)
        sims = []
        gold_needles = [r["needle"] for r in needle_rows if r["gold_rank"] is not None]
        for t in (0.3, 0.5, 0.7):
            kept = [c for c in chunks if c["jev"]["answers"] >= t]
            retained = {c["needle"] for c in kept if c["is_gold"]}
            heldout_kept = [c for c in kept if c["cell"] == "heldout"]
            sims.append({
                "threshold": t,
                "chunks_kept": len(kept),
                "packet_reduction": round(1 - len(kept) / len(chunks), 3),
                "precision_gold": round(sum(c["is_gold"] for c in kept) / len(kept), 3) if kept else None,
                "needles_gold_delivered": len(gold_needles),
                "needles_gold_retained": len(retained),
                "heldout_chunks_kept": len(heldout_kept),
            })
        out["chunk_filter"]["filter_sim"] = sims

    # Ranking: gold rank under cymatix order vs Jev answers-probability order.
    rr_cym, rr_jev = [], []
    for r in needle_rows:
        if r["gold_rank"] is None:
            continue
        cs = [c for c in chunks if c["needle"] == r["needle"]]
        order = sorted(cs, key=lambda c: (-c["jev"]["answers"], c["rank"]))
        jev_rank = next(i for i, c in enumerate(order, 1) if c["is_gold"])
        rr_cym.append(1 / r["gold_rank"])
        rr_jev.append(1 / jev_rank)
    if rr_cym:
        out["gold_ranking"] = {
            "n": len(rr_cym),
            "mrr_cymatix": round(sum(rr_cym) / len(rr_cym), 3),
            "mrr_jev_rerank": round(sum(rr_jev) / len(rr_jev), 3),
            "top1_cymatix": sum(x == 1 for x in rr_cym),
            "top1_jev_rerank": sum(x == 1 for x in rr_jev),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry", action="store_true", help="build bed + packets, no Jev calls")
    ap.add_argument("--rescore", action="store_true", help="recompute summary from --out cache only")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workdir", default=str(Path(tempfile.gettempdir()) / "jev_239b_c4000"))
    args = ap.parse_args()

    if os.environ.get("PYTHONHASHSEED") != "0":
        print("ERROR: run with PYTHONHASHSEED=0", file=sys.stderr)
        return 2

    out_path = Path(args.out) if args.out else (
        REPO_ROOT / "benchmarks/dogfood/jev"
        / f"jev_239b_packet_know_{Path(args.profile).stem}_{time.strftime('%Y-%m-%d')}.json")

    if args.rescore:
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev["summary"] = summarize(prev["needles"], prev["chunks"])
        out_path.write_text(json.dumps(prev, indent=1), encoding="utf-8")
        print(json.dumps(prev["summary"], indent=1))
        return 0

    key_var = next((v for v in ("JEV_API_KEY", "TYPESAFE_API_KEY") if os.environ.get(v)), None)
    if not args.dry and key_var is None:
        print("ERROR: neither JEV_API_KEY nor TYPESAFE_API_KEY is set", file=sys.stderr)
        return 2
    api_key = os.environ.get(key_var) if key_var else None

    cache = {}
    if out_path.exists() and not args.dry:
        cache = json.loads(out_path.read_text(encoding="utf-8")).get("raw_cache", {})
        print(f"resuming: {len(cache)} cached Jev responses from {out_path}")

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    os.environ["CYMATIX_DISABLE_LEARN"] = "1"
    os.environ["CYMATIX_GENOME_PATH"] = str(workdir / "bed_239b.db")
    from needles_239b import NEEDLES_239B  # noqa: E402
    from cymatix_context.config import load_config  # noqa: E402
    from cymatix_context.retrieval.query_classifier import classify_query  # noqa: E402
    from cymatix_context.server.helpers import _compute_know_or_miss_block  # noqa: E402

    profile = (REPO_ROOT / args.profile).resolve()
    cfg = load_config(str(profile))
    cfg.genome.path = str(workdir / "bed_239b.db")
    needles = NEEDLES_239B[: args.limit] if args.limit else NEEDLES_239B
    # Always ingest the full bed so a --limit run sees the same distractor field.
    mgr, gold_ids, comp_ids, n_docs = build_bed(cfg, NEEDLES_239B, workdir / "corpus")
    n_genes = mgr.genome.conn.execute("SELECT COUNT(*) FROM genes").fetchone()[0]
    loaded_cfg = {
        "profile": args.profile,
        "genome.path": cfg.genome.path,
        "retrieval.fusion_mode": cfg.retrieval.fusion_mode,
        "retrieval.rrf_k": cfg.retrieval.rrf_k,
        "retrieval.dense_embedding_enabled": cfg.retrieval.dense_embedding_enabled,
        "budget.max_genes_per_turn": cfg.budget.max_genes_per_turn,
        "budget.expression_tokens": cfg.budget.expression_tokens,
        "budget.min_delivered_docs": cfg.budget.min_delivered_docs,
        "budget.classifier_cap_ref_chars": getattr(cfg.budget, "classifier_cap_ref_chars", None),
        "budget.abstain_enabled": getattr(cfg.budget, "abstain_enabled", None),
        "know.emit_floor": getattr(cfg.know, "emit_floor", None),
        "ribosome.backend": cfg.ribosome.backend,
        "ingestion.backend": cfg.ingestion.backend,
    }
    print(f"bed: {n_docs} docs -> {n_genes} genes; loaded config:", json.dumps(loaded_cfg))

    last_call = [0.0]
    jev_models = set()
    usage_in = [0]

    def cached_call(key, state, questions):
        if key not in cache:
            cache[key] = jev_call(api_key, state, questions, last_call)
            usage_in[0] += cache[key].get("usage", {}).get("input_tokens", 0)
        jev_models.add(cache[key].get("model"))
        return cache[key]["answers"]

    def checkpoint():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"partial": True, "raw_cache": cache},
                                       indent=1), encoding="utf-8")

    chunks, needle_rows = [], []
    t0 = time.monotonic()
    for i, nd in enumerate(needles, 1):
        q = nd["q"]
        window = mgr.build_context(q, read_only=True, ignore_delivered=True)
        block = _compute_know_or_miss_block(cymatix=mgr, window=window, query=q)
        ids = list(window.expressed_gene_ids)
        scores = window.retrieval_scores or {}
        cls = classify_query(q)
        is_know = block is not None and getattr(block, "found", False) is True
        cym = {
            "classifier": cls.cls,
            "block": "know" if is_know else ("miss" if block is not None else "none"),
            "know_confidence": getattr(block, "confidence", None) if is_know else None,
            "miss_reason": getattr(block, "reason", None) if not is_know and block is not None else None,
            "top_score": float(getattr(block, "top_score", 0.0) or 0.0),
            "score_gap": getattr(block, "score_gap", None),
            "ratio": getattr(block, "ratio", None),
            "coordinate_confidence": getattr(block, "coordinate_confidence", None),
            "delivered": len(ids),
        }
        gold = gold_ids.get(nd["id"], set())
        comp = comp_ids.get(nd["id"], set())
        delivered = []
        for rank, gid in enumerate(ids, 1):
            gene = mgr.genome.get_doc(gid)
            if gene is None:
                continue
            delivered.append({"rank": rank, "gene_id": gid, "text": gene.content or "",
                              "score": round(float(scores.get(gid, 0.0)), 4),
                              "is_gold": gid in gold, "is_competitor": gid in comp})
        gold_rank = next((d["rank"] for d in delivered if d["is_gold"]), None)
        truth_know = gold_rank is not None
        row = {"needle": nd["id"], "cell": nd["cell"], "query": q,
               "truth_know": truth_know, "gold_rank": gold_rank, "cymatix": cym}
        if args.dry:
            needle_rows.append(row)
            print(f"[{i}/{len(needles)}] {nd['id']:18s} {nd['cell']:11s} cls={cls.cls:10s} "
                  f"{cym['block']:4s} conf={cym['know_confidence']} reason={cym['miss_reason']} "
                  f"delivered={len(ids):2d} gold_rank={gold_rank}")
            continue

        qt = cached_call(f"{nd['id']}::qtype", {"question": q}, qtype_questions())["qtype"]
        qtype = qt["choice"]
        incoming = {"query_class": cls.cls, "delivered": len(delivered)}
        n_rows = []
        for d in delivered:
            ans = cached_call(
                f"{nd['id']}::{d['gene_id']}::{qtype}",
                {"question": q, "question_type": qtype,
                 "retrieval": {**incoming, "rank": d["rank"], "fused_score": d["score"]},
                 "chunk": {"text": d["text"]}},
                chunk_questions(qtype))
            c = {"needle": nd["id"], "cell": nd["cell"], "rank": d["rank"],
                 "gene_id": d["gene_id"], "cymatix_score": d["score"],
                 "is_gold": d["is_gold"], "is_competitor": d["is_competitor"],
                 "jev": {"answers": ans["answers"]["noul"],
                         "typed": ans["typed"]["noul"],
                         "relevance": ans["relevance"]["score"]}}
            chunks.append(c)
            n_rows.append(c)
        contract = {"verdict": cym["block"], "confidence": cym["know_confidence"],
                    "miss_reason": cym["miss_reason"], "top_score": cym["top_score"],
                    "score_gap": cym["score_gap"]}
        pk = cached_call(
            f"{nd['id']}::packet::{qtype}",
            {"question": q, "question_type": qtype,
             "retrieval": {**incoming, "know_miss": contract},
             "packet": [{"rank": d["rank"], "fused_score": d["score"], "text": d["text"]}
                        for d in delivered]},
            packet_questions())
        row.update({
            "qtype": qtype, "qtype_probs": qt.get("probabilities"),
            "jev_packet_answers": pk["packet_answers"]["noul"],
            "jev_max_chunk_answers": max((c["jev"]["answers"] for c in n_rows), default=0.0),
        })
        needle_rows.append(row)
        print(f"[{i}/{len(needles)}] {nd['id']:18s} {nd['cell']:11s} {cym['block']:4s} "
              f"gold_rank={gold_rank} jev_packet={row['jev_packet_answers']:.3f} "
              f"max_chunk={row['jev_max_chunk_answers']:.3f} chunks={len(n_rows)}")
        checkpoint()

    if args.dry:
        print(json.dumps({"by_cell": {cell: {
            "n": sum(r["cell"] == cell for r in needle_rows),
            "gold_delivered": sum(r["cell"] == cell and r["truth_know"] for r in needle_rows),
            "cymatix_know": sum(r["cell"] == cell and r["cymatix"]["block"] == "know" for r in needle_rows),
        } for cell in ("answerable", "heldout", "competition")}}, indent=1))
        return 0

    needles_src = (REPO_ROOT / "benchmarks/faithfulness/needles_239b.py").read_bytes()
    profile_bytes = profile.read_bytes()
    receipt = {
        "experimental": True,
        "harness": "benchmarks/dogfood/jev/jev_239b_packet_know.py",
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "behind_master": git("rev-list", "--count", "HEAD..origin/master"),
        "dirty": bool(git("status", "--porcelain")),
        "bed": {"set": "needles_239b (seed 239)", "docs": n_docs, "genes": n_genes,
                "needles_src_sha256": hashlib.sha256(needles_src).hexdigest()},
        "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "loaded_config": loaded_cfg,
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "api_key_var": key_var,
        "jev_model_requested": MODEL,
        "jev_models": sorted(m for m in jev_models if m),
        "jev_input_tokens_this_run": usage_in[0],
        "wall_s": round(time.monotonic() - t0, 1),
        "sheet": {k: list(v) for k, v in SHEET.items()},
        "summary": summarize(needle_rows, chunks),
        "needles": needle_rows,
        "chunks": chunks,
        "raw_cache": cache,
    }
    out_path.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(json.dumps(receipt["summary"], indent=1))
    print(f"receipt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
