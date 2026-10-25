#!/usr/bin/env python3
"""Measured computational cost (closes the "not instrumented" limitation of paper Section 6).

For every paired run src/pipeline.py writes the number of calls, input/output/thinking tokens,
model time and the number of refinement iterations to manifest.json. This script aggregates
them per domain and overall.

Per-configuration cost follows from the paired protocol: a run performs one extraction and
derives the four configurations from it, so
  llm_only    = extraction (1 call)
  prune       = extraction + 0 calls (reasoner deletion, no LLM)
  single_pass = extraction + at most 1 correction call
  hybrid      = extraction + as many correction calls as refinement iterations observed

Usage : python statistics/cost_telemetry.py results/<arm>
Output: statistics/cost_telemetry_<arm>.json (any other result tree: next to that tree)
"""
import os, sys, json, glob, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import paths as P                                          # noqa: E402

PROJ = P.ROOT


def collect(root):
    rows = []
    for m in sorted(glob.glob(os.path.join(root, "*", "run*", "manifest.json"))):
        try:
            j = json.load(open(m, encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        t = j.get("telemetry") or {}
        if not t:
            continue
        rows.append({"domain": j.get("domain"), "run": j.get("run"), **t})
    return rows


def summarize(rows, domain=None):
    sel = [r for r in rows if domain is None or r["domain"] == domain]
    if not sel:
        return None
    def m(k):
        v = [r.get(k, 0) or 0 for r in sel]
        return round(st.mean(v), 1) if v else 0
    iters = [r.get("refine_iterations", 0) or 0 for r in sel]
    return {
        "n": len(sel),
        "calls_per_run": m("calls"),
        "in_tokens_per_run": round(m("in_tokens")),
        "out_tokens_per_run": round(m("out_tokens")),
        "thinking_tokens_per_run": round(m("thinking_tokens")),
        "api_seconds_per_run": m("api_seconds"),
        "wall_seconds_per_run": m("wall_seconds"),
        "refine_iterations": {i: iters.count(i) for i in sorted(set(iters))},
        "median_iterations": st.median(iters),
        "parse_failures_total": sum(r.get("parse_failures", 0) or 0 for r in sel),
        "parse_attempts_total": sum(r.get("parse_attempts", 0) or 0 for r in sel),
    }


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python statistics/cost_telemetry.py results/<arm>")
    root = P.resolve_root(sys.argv[1])
    rows = collect(root)
    if not rows:
        raise SystemExit(f"no manifest.json found under {root}")
    domains = sorted({r["domain"] for r in rows})
    out = {"root": os.path.relpath(root, PROJ), "overall": summarize(rows),
           "by_domain": {d: summarize(rows, d) for d in domains}}

    print(f"MEASURED COST - {os.path.basename(root)}  (n={len(rows)} paired runs)\n")
    hdr = (f"{'domain':<14}{'run':>4}{'calls':>7}{'in tok':>11}{'out tok':>11}"
           f"{'thinking':>10}{'API s':>9}{'median it.':>11}")
    print(hdr); print("-" * len(hdr))
    for d in domains + ["TOTAL"]:
        s = out["by_domain"][d] if d != "TOTAL" else out["overall"]
        print(f"{d:<14}{s['n']:>4}{s['calls_per_run']:>7}{s['in_tokens_per_run']:>11,}"
              f"{s['out_tokens_per_run']:>11,}{s['thinking_tokens_per_run']:>10,}"
              f"{s['api_seconds_per_run']:>9}{s['median_iterations']:>11}")
    o = out["overall"]
    print(f"\nrefinement iterations (all domains): {o['refine_iterations']}")
    print(f"parse failures: {o['parse_failures_total']}/{o['parse_attempts_total']} attempts")

    # relative cost per configuration
    ex = o["calls_per_run"]
    print("\nLLM calls per configuration (paired protocol):")
    print(f"  llm_only     1 (extraction)")
    print(f"  prune        1 (extraction; deletion needs no LLM)")
    print(f"  single_pass  1 + at most 1 correction")
    print(f"  hybrid       1 + {o['median_iterations']} corrections (median), upper bound 1 + 5")
    print(f"  measured mean: {ex} calls/run (all four configurations together)")

    dest = P.stats_dest(root, "cost_telemetry.json")
    json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n-> wrote {dest}")


if __name__ == "__main__":
    main()
