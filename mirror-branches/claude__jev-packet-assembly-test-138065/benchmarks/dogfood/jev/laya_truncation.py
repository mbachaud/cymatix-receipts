"""Truncation report for a Laya-served receipt, from Laya's own usage block.

laya-serve returns ``usage.state_tokens`` / ``state_tokens_dropped`` /
``truncated`` on every response. This groups them by call type (question
type, per-chunk, packet) so a receipt can say how much of each state the
model actually read.

Usage: python -P laya_truncation.py <receipt.json> [<receipt.json> ...]
"""

from __future__ import annotations

import json
import statistics
import sys


def kind(key: str) -> str:
    if key.endswith("::qtype"):
        return "qtype"
    if "::packet::" in key:
        return "packet"
    return "chunk"


def report(path: str) -> dict:
    r = json.load(open(path, encoding="utf-8"))
    groups: dict = {}
    for key, resp in r["raw_cache"].items():
        groups.setdefault(kind(key), []).append(resp.get("usage") or {})
    out = {"receipt": path, "provider": r.get("provider")}
    for name, us in sorted(groups.items()):
        # laya common.py: state_tokens = the whole tokenized state;
        # state_tokens_dropped = the part past max_len that was not read.
        total = [u.get("state_tokens", 0) for u in us]
        dropped = [u.get("state_tokens_dropped", 0) for u in us]
        read = [t - d for t, d in zip(total, dropped)]
        out[name] = {
            "calls": len(us),
            "truncated": sum(bool(u.get("truncated")) for u in us),
            "state_tokens_p50": statistics.median(total) if total else None,
            "read_tokens_p50": statistics.median(read) if read else None,
            "dropped_frac_mean": round(sum(d / t for d, t in zip(dropped, total) if t) / len(us), 3),
        }
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(report(p), indent=1))
