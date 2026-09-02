"""Full-depth (weekly tier, UNFILTERED pytest) scorerift audit of cymatix-context.

All artifacts stay in F:/tmp/cymatixscontext_SR_reports. Target repo is not
modified (no register, no .scorerift.json).
"""
import json
import os
import time
from pathlib import Path

REPORTS = Path(r"F:\tmp\cymatixscontext_SR_reports")

# Env contract: full suite (no marker filter), 90-min pytest budget.
os.environ.pop("SCORERIFT_PYTEST_MARKERS", None)
os.environ["SCORERIFT_PYTEST_TIMEOUT"] = "5400"

from scorerift import AuditEngine
from scorerift.presets import PRESETS
from scorerift.exporters.csv_export import export_csv
from scorerift.exporters.json_export import export_json
from scorerift.exporters.markdown_export import export_markdown


def main() -> None:
    engine = AuditEngine(
        db_path=str(REPORTS / "audit.db"),
        baseline_path=str(REPORTS / "audit_baseline.json"),
        target_path=r"F:\Projects\cymatix-context",
    )
    engine.register_many(PRESETS["python"])

    t0 = time.time()
    results = engine.run_tier("weekly")
    elapsed = time.time() - t0

    payload = {
        "target": engine.target_path,
        "tier": "weekly",
        "pytest_markers_env": os.environ.get("SCORERIFT_PYTEST_MARKERS"),
        "pytest_timeout_env": os.environ.get("SCORERIFT_PYTEST_TIMEOUT"),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)),
        "elapsed_seconds": round(elapsed, 1),
        "dimensions": [
            {
                "name": r.name,
                "auto_score": r.auto_score,
                "auto_confidence": r.auto_confidence,
                "divergent": r.divergent,
                "auto_detail": r.auto_detail,
            }
            for r in results
        ],
        "overall_score": engine.overall_score(),
        "overall_grade": engine.overall_grade(),
        "health": engine.health_check(),
    }
    (REPORTS / "raw_results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    export_json(engine, REPORTS / "scores.json")
    export_csv(engine, REPORTS / "scores.csv")
    export_markdown(engine, REPORTS / "scores.md")

    engine.close()
    print(json.dumps(
        {
            "overall": payload["overall_score"],
            "grade": payload["overall_grade"],
            "health": payload["health"],
            "elapsed_seconds": payload["elapsed_seconds"],
        },
        default=str,
    ))


if __name__ == "__main__":
    main()
