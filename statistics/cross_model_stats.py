#!/usr/bin/env python3
"""Paired statistics of one extractor's result tree (paper Tables 1-4).

For every domain under the tree: coherent-run counts (Wilson 95% CI), CQ and F1
means, one-sided paired sign-flip p values for the ladder A < Br < C and the prune
control Bp < C, bootstrap 95% CI and Cohen's dz for the CQ gains, and F1
non-inferiority of C against Br at delta = 0.02. Primitives: stats_core.py.

Usage (from the repository root):
  python statistics/cross_model_stats.py results/primary_extractor
  python statistics/cross_model_stats.py results/second_extractor securities
Writes statistics/cross_model_stats_<arm>.json for a stored arm, <tree>/cross_model_stats.json
for any other result tree (other domains already in the file are kept).
"""
import os, sys, json, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import paths as P                                                   # noqa: E402

PROJ = P.ROOT
from stats_core import signflip, cohen_dz, boot_ci, wilson          # noqa: E402

import re
RUNS = []   # set per domain by discover_runs()


def discover_runs(root, domain):
    """The runNN directories present under <root>/<domain>."""
    d = P.domain_dir(root, domain)
    return sorted(x for x in os.listdir(d) if re.fullmatch(r"run\d{2}", x)) if os.path.isdir(d) else []
CFG = {"A": "llm_only", "Bp": "prune", "Br": "single_pass", "C": "hybrid"}
ORDER = ["A", "Bp", "Br", "C"]
SUITE = {"securities": 21, "hypertension": 26, "assessment": 24}


def load(root, domain, pref, run, cfg):
    p = os.path.join(P.scoring_dir(root, domain), f"{pref}_{run}_{cfg}.json")
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        return None
    try:
        return json.load(open(p))
    except json.JSONDecodeError:
        return None


def collect(root, domain):
    cq, f1, uns = {}, {}, {}
    for r in RUNS:
        for k in ORDER:
            a = load(root, domain, "f1", r, CFG[k])
            q = load(root, domain, "cq", r, CFG[k])
            if a:
                f1[(r, k)] = a["f1"]
                # coherence as defined in Section 4.3 (consistent AND no unsatisfiable class); inconsistent -> -1
                uns[(r, k)] = a["unsatisfiable"] if a.get("consistent", True) else -1
            if q:
                cq[(r, k)] = q["passed"]
    return cq, f1, uns


def paired(vals, a, b):
    return [vals[(r, b)] - vals[(r, a)] for r in RUNS if (r, a) in vals and (r, b) in vals]


def analyse(root, domain):
    global RUNS
    RUNS = discover_runs(root, domain)
    cq, f1, uns = collect(root, domain)
    n = sum(1 for r in RUNS if (r, "C") in f1)
    if not n:
        print(f"  {domain}: no score files found ({root})")
        return None
    coh = {k: sum(1 for r in RUNS if uns.get((r, k)) == 0) for k in ORDER}
    ncov = {k: sum(1 for r in RUNS if (r, k) in uns) for k in ORDER}
    out = {"root": os.path.relpath(root, PROJ), "domain": domain, "n": n, "coherent": coh, "n_cov": ncov,
           "coherent_wilson95": {k: [round(x, 3) for x in wilson(coh[k], ncov[k])]
                                 for k in ORDER}}

    print("=" * 78)
    print(f"{domain.upper()}  ({root})  n={n}")
    print("=" * 78)
    print("  coherent runs: " + "  ".join(f"{k}={coh[k]}/{ncov[k]}" for k in ORDER))
    print("  F1 mean      : " + "  ".join(
        f"{k}={st.mean([f1[(r,k)] for r in RUNS if (r,k) in f1]):.3f}" for k in ORDER))
    if cq:
        print("  CQ mean      : " + "  ".join(
            f"{k}={st.mean([cq[(r,k)] for r in RUNS if (r,k) in cq]):.2f}" for k in ORDER))

    # coherence axis: binary coherence indicator
    cons = {k: {r: (1 if uns.get((r, k)) == 0 else 0) for r in RUNS if (r, k) in uns}
            for k in ORDER}
    for nm, a, b in (("cons_A<Br", "A", "Br"), ("cons_Br<C", "Br", "C"),
                     ("cons_A<C", "A", "C")):
        d = [cons[b][r] - cons[a][r] for r in RUNS if r in cons[a] and r in cons[b]]
        out[nm] = {"delta": round(st.mean(d), 4) if d else None,
                   "p": round(signflip(d), 5)}
    print(f"  CONS  A<Br p={out['cons_A<Br']['p']}  Br<C p={out['cons_Br<C']['p']}  "
          f"A<C p={out['cons_A<C']['p']} (Δ={out['cons_A<C']['delta']})")

    for nm, a, b in (("cq_A<Br", "A", "Br"), ("cq_Br<C", "Br", "C"),
                     ("cq_A<C", "A", "C"), ("cq_Bp<C", "Bp", "C")):
        d = paired(cq, a, b)
        if not d:
            continue
        lo, hi = boot_ci(d)
        out[nm] = {"delta": round(st.mean(d), 3), "p": round(signflip(d), 5),
                   "ci95": [round(lo, 3), round(hi, 3)], "dz": round(cohen_dz(d), 3)}
    if "cq_A<C" in out:
        o = out["cq_A<C"]
        print(f"  CQ    A<C  Δ={o['delta']}  p={o['p']}  CI95={o['ci95']}  dz={o['dz']}")
    if "cq_Bp<C" in out:
        o = out["cq_Bp<C"]
        print(f"  CQ    Bp<C Δ={o['delta']}  p={o['p']}  (prune control)")

    draw = paired(f1, "Br", "C")
    if draw:
        lo, hi = boot_ci(draw)
        out["f1_noninf_C_Br"] = {
            "deltaF1": round(st.mean(draw), 4), "ci95": [round(lo, 4), round(hi, 4)],
            "dz": round(cohen_dz(draw), 3),
            "p_noninf_delta0.02": round(signflip([x + 0.02 for x in draw]), 5)}
        o = out["f1_noninf_C_Br"]
        print(f"  F1    non-inf C-Br ΔF1={o['deltaF1']}  CI95={o['ci95']}  "
              f"p(δ=.02)={o['p_noninf_delta0.02']}")
    dbp = paired(f1, "Bp", "C")
    if dbp:
        out["f1_Bp<C"] = {"delta": round(st.mean(dbp), 4), "p": round(signflip(dbp), 5)}
    print()
    return out


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python statistics/cross_model_stats.py results/<arm> [domain]")
    root = P.resolve_root(sys.argv[1])
    domains = [sys.argv[2]] if len(sys.argv) > 2 else \
        [d for d in ("securities", "hypertension", "assessment")
         if os.path.isdir(P.scoring_dir(root, d))]
    dest = P.stats_dest(root, "cross_model_stats.json")
    # When called for a single domain, the results of the other domains are kept.
    OUT = {}
    if os.path.exists(dest):
        try:
            OUT = json.load(open(dest, encoding="utf-8"))
        except json.JSONDecodeError:
            OUT = {}
    for d in domains:
        r = analyse(root, d)
        if r:
            OUT[d] = r
    OUT = {k: OUT[k] for k in ("securities", "hypertension", "assessment") if k in OUT}
    json.dump(OUT, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"-> wrote {dest}")


if __name__ == "__main__":
    main()
