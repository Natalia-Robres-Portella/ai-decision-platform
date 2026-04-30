#!/usr/bin/env python3
"""CLI runner for the RAG evaluation suite.

Usage (from the backend/ directory):
    python evaluation/run_eval.py

The backend must be running:
    uvicorn app.main:app --port 8002 --reload

Results are saved to evaluation/evaluation_report_<timestamp>.json.
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


BACKEND_URL = "http://localhost:8002/api/v1/eval/run"
TIMEOUT_S = 300  # eval takes ~30-60 s; generous timeout for slow API days


def _score_bar(score: float, width: int = 10) -> str:
    """Render a simple ASCII bar: [████░░░░░░] for a 0–1 score."""
    filled = round(score * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def _color(score: float, text: str, scale: str = "pct") -> str:
    """ANSI colour code: green ≥ 80%, yellow ≥ 60%, red < 60%."""
    if not sys.stdout.isatty():
        return text  # no colour codes in CI / file redirects
    if scale == "pct":
        threshold_hi, threshold_lo = 0.80, 0.60
    else:  # 1-5 scale
        threshold_hi, threshold_lo = 4.0, 3.0
    if score >= threshold_hi:
        code = "\033[32m"  # green
    elif score >= threshold_lo:
        code = "\033[33m"  # yellow
    else:
        code = "\033[31m"  # red
    return f"{code}{text}\033[0m"


def main() -> None:
    print(f"Connecting to {BACKEND_URL} …")
    print("This takes ~30–60 s. Hang tight.\n")

    req = urllib.request.Request(BACKEND_URL, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            report = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        print(f"\n[ERROR] Could not reach backend: {exc.reason}")
        print("Make sure the backend is running:")
        print("  uvicorn app.main:app --port 8002 --reload")
        sys.exit(1)

    # ── Summary ───────────────────────────────────────────────────────────────
    ts = report["timestamp"]
    n = report["total_questions"]
    faith = report["avg_faithfulness"]
    rel = report["avg_relevance"]
    comp = report["avg_completeness"]
    r_ms = report["avg_retrieval_latency_ms"]
    t_ms = report["avg_total_latency_ms"]

    print("=" * 66)
    print(f"  EVALUATION REPORT  ·  {ts[:19].replace('T', ' ')} UTC")
    print("=" * 66)
    print(f"  Questions evaluated : {n}")
    print()
    print(
        f"  Faithfulness  {_score_bar(faith)}  "
        + _color(faith, f"{faith:.1%}", "pct")
        + "  (hallucination check)"
    )
    print(
        f"  Relevance     {_score_bar((rel - 1) / 4)}  "
        + _color(rel, f"{rel:.2f}/5", "1-5")
        + "  (retrieval quality)"
    )
    print(
        f"  Completeness  {_score_bar((comp - 1) / 4)}  "
        + _color(comp, f"{comp:.2f}/5", "1-5")
        + "  (answer coverage)"
    )
    print()
    print(f"  Retrieval latency : {r_ms:.0f} ms avg")
    print(f"  Total latency     : {t_ms:.0f} ms avg")
    print("=" * 66)
    print()

    # ── Per-question table ────────────────────────────────────────────────────
    col_q = 44
    print(f"  {'Question':<{col_q}} {'Faith':>6} {'Rel':>5} {'Comp':>5} {'ms':>7}")
    print(f"  {'-' * col_q} {'------':>6} {'-----':>5} {'-----':>5} {'-------':>7}")

    for r in report["results"]:
        if r.get("error"):
            row_q = r["question"][:col_q]
            print(f"  {row_q:<{col_q}} {'ERROR':>6}")
            continue

        row_q = r["question"]
        if len(row_q) > col_q:
            row_q = row_q[: col_q - 1] + "…"

        f_str = _color(r["faithfulness"], f"{r['faithfulness']:.0%}", "pct")
        rel_str = _color(r["relevance_raw"], f"{r['relevance_raw']:.1f}", "1-5")
        comp_str = _color(r["completeness_raw"], f"{r['completeness_raw']:.1f}", "1-5")
        ms_str = f"{r['total_latency_ms']:.0f}"

        print(f"  {row_q:<{col_q}} {f_str:>6} {rel_str:>5} {comp_str:>5} {ms_str:>7}")

    # ── Save JSON report ──────────────────────────────────────────────────────
    out_dir = Path(__file__).parent
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"evaluation_report_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Full report → {out_path}")


if __name__ == "__main__":
    main()
