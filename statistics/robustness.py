#!/usr/bin/env python3
"""Initial-ontology robustness (paper §5.5) - no LLM calls.

Every paired run starts from an independent LLM-only extraction, so a result tree
holds 30 distinct starting points per domain. For each domain this reports the
range of initial coherence, the unsatisfiable classes and global inconsistencies
the starting ontologies contain, and how many runs end coherent.

Usage (from the repository root):
  python statistics/robustness.py                                  # primary extractor
  python statistics/robustness.py --root results/second_extractor
Writes statistics/robustness_<arm>.json (any other result tree: next to that tree).
"""
import os, sys, json, argparse, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import paths as P                                          # noqa: E402

PROJ = P.ROOT
DOMAINS = ["securities", "hypertension", "assessment"]


def _load(sc, pref, run, cfg):
    p = os.path.join(sc, f"{pref}_{run}_{cfg}.json")
    return json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) > 0 else None


# --------------------------------------------------------------------------- #
def _coherent(s):
    """Paper §4.3: consistent AND no unsatisfiable class."""
    return s.get("consistent", True) and s["unsatisfiable"] == 0


def r1(root):
    print("=" * 78)
    print("R1 - INITIAL-ONTOLOGY ROBUSTNESS")
    print("=" * 78)
    print(f"Every run is an independent starting point ({os.path.relpath(root, PROJ)}).\n")
    out = {}
    for dom in DOMAINS:
        sc = P.scoring_dir(root, dom)
        runs = sorted(x for x in os.listdir(P.domain_dir(root, dom))
                      if x.startswith("run")) if os.path.isdir(P.domain_dir(root, dom)) else []
        rows = []
        for r in runs:
            a = _load(sc, "f1", r, "llm_only")
            c = _load(sc, "f1", r, "hybrid")
            if a and c:
                rows.append({"run": r, "C0": a["consistency_C"], "unsat0": a["unsatisfiable"],
                             "consistent0": a.get("consistent", True),
                             "C1": c["consistency_C"], "unsat1": c["unsatisfiable"],
                             "coherent1": _coherent(c)})
        if not rows:
            continue
        C0 = [x["C0"] for x in rows]; U0 = [x["unsat0"] for x in rows]
        conv = sum(1 for x in rows if x["coherent1"])
        out[dom] = {"n": len(rows), "C0_min": min(C0), "C0_max": max(C0),
                    "C0_mean": round(st.mean(C0), 4), "unsat0_total": sum(U0),
                    "unsat0_max": max(U0), "inconsistent0": sum(not x["consistent0"] for x in rows),
                    "converged": conv, "rows": rows}
        print(f"--- {dom} (n={len(rows)})")
        print(f"    initial C       : {min(C0):.3f} - {max(C0):.3f} (mean {st.mean(C0):.3f})")
        print(f"    initial unsat   : 0 - {max(U0)} ({sum(U0)} unsatisfiable classes in total)")
        print(f"    globally inconsistent at start: {out[dom]['inconsistent0']} runs")
        print(f"    coherent at end : {conv}/{len(rows)} runs")
        worst = sorted(rows, key=lambda x: -x["unsat0"])[:3]
        print("    3 worst starting points: " + ", ".join(
            f"{w['run']} unsat {w['unsat0']}→{w['unsat1']} (C {w['C0']:.2f}→{w['C1']:.2f})"
            for w in worst))
        print()
    tot_u = sum(v["unsat0_total"] for v in out.values())
    tot_n = sum(v["n"] for v in out.values())
    tot_c = sum(v["converged"] for v in out.values())
    print(f"SUMMARY: {tot_n} independent initial ontologies, {tot_u} unsatisfiable classes in total")
    print(f"      -> {tot_c}/{tot_n} runs coherent at the end\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="results/primary_extractor",
                    help="result tree of the extractor")
    a = ap.parse_args()
    root = P.resolve_root(a.root)
    out = {"root": os.path.relpath(root, PROJ), "r1": r1(root)}
    dest = P.stats_dest(root, "robustness.json")
    json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"-> {dest}")


if __name__ == "__main__":
    main()
