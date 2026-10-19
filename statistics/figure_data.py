#!/usr/bin/env python3
"""Numeric inputs of the paper figures, computed from a result tree -> statistics/figure_data.json

statistics/make_all_figs.py only draws; every value it plots comes from here.

  fig3  finance (securities) ladder: share of coherent runs, CQ accuracy and F1 per
        configuration (LLM-only, single-pass repair, hybrid)
  fig4  error types the reasoner and the structural checks report in the LLM-only
        ontologies of all domains
  fig5  refinement iterations per run (measured: refine_history in each manifest)

Coherence follows paper §4.3: the ontology is consistent AND has no unsatisfiable
class.

Usage (from the repository root):
  python statistics/figure_data.py                                 # primary extractor
  python statistics/figure_data.py --root results/second_extractor
"""
import os, sys, json, glob, argparse, collections, statistics as st
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import paths as P                                              # noqa: E402

PROJ = P.ROOT
import onto_utils as ou                                        # noqa: E402

DOMAINS = ["securities", "hypertension", "assessment"]
LADDER = (("llm_only", "LLM-only"), ("single_pass", "LLM + single-pass repair"),
          ("hybrid", "Proposed (Hybrid)"))
CAP = 5


def runs_of(root, domain):
    return sorted(os.path.basename(os.path.dirname(m)) for m in
                  glob.glob(os.path.join(P.domain_dir(root, domain), "run*", "manifest.json")))


def _load(root, domain, pref, run, cfg):
    p = os.path.join(P.scoring_dir(root, domain), f"{pref}_{run}_{cfg}.json")
    return json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) > 0 else None


# --------------------------------------------------------------------------- #
def fig3(root, domain="securities"):
    """Ladder: coherent share / CQ accuracy / F1 per configuration."""
    runs = runs_of(root, domain)
    out = {}
    for cfg, label in LADDER:
        f1s, cqs, coh, n = [], [], 0, 0
        for r in runs:
            a, q = _load(root, domain, "f1", r, cfg), _load(root, domain, "cq", r, cfg)
            if a:
                f1s.append(a["f1"]); n += 1
                coh += 1 if a.get("consistent", True) and a["unsatisfiable"] == 0 else 0
            if q:
                cqs.append(q["passed"] / q["total"])
        out[label] = [round(coh / n, 4) if n else None,
                      round(st.mean(cqs), 4) if cqs else None,
                      round(st.mean(f1s), 4) if f1s else None]
    return {"domain": domain, "metrics": ["Coherence", "CQ accuracy", "F1"],
            "values": out, "n": len(runs)}


# --------------------------------------------------------------------------- #
def _errors_of(args):
    root, domain, run = args
    path = os.path.join(P.domain_dir(root, domain), run, "llm_only.ttl")
    g = ou.parse_ttl(open(path, encoding="utf-8").read())
    errs, _ = ou.detect_errors(g)     # stored ontologies are already datatype-normalized
    return domain, run, dict(collections.Counter(e["type"] for e in errs))


def fig4(root, workers=6):
    """Error types in the LLM-only ontologies (occurrences + runs affected)."""
    cells = [(root, d, r) for d in DOMAINS for r in runs_of(root, d)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_errors_of, cells))
    total, runs_with = collections.Counter(), collections.Counter()
    for _, _, c in rows:
        for k, v in c.items():
            total[k] += v
            runs_with[k] += 1
    order = ["unsatisfiable_class", "inconsistency", "missing_domain", "missing_range"]
    cats = [k for k in order if k in total] + [k for k in total if k not in order]
    return {"n_ontologies": len(rows), "categories": cats,
            "totals": {k: total[k] for k in cats},
            "runs_with": {k: runs_with[k] for k in cats},
            "per_run": {f"{d}/{r}": c for d, r, c in rows}}


# --------------------------------------------------------------------------- #
def iterations(root, domain):
    hist = [json.load(open(m))["telemetry"]["refine_iterations"] for m in
            sorted(glob.glob(os.path.join(P.domain_dir(root, domain), "run*", "manifest.json")))]
    c = collections.Counter(hist)
    ks = sorted(c)
    return {"n": len(hist), "iterations": ks, "counts": [c[k] for k in ks],
            "median": st.median(hist) if hist else None, "cap": CAP}


def fig5(root, domain="securities"):
    """Refinement iterations per run: the plotted domain plus every domain for reference."""
    return {"primary": {"domain": domain, **iterations(root, domain)},
            "by_domain": {d: iterations(root, d) for d in DOMAINS}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="results/primary_extractor",
                    help="result tree of the extractor the figures show")
    a = ap.parse_args()
    root = P.resolve_root(a.root)
    data = {"root": os.path.relpath(root, PROJ),
            "fig3": fig3(root), "fig4": fig4(root), "fig5": fig5(root)}
    os.makedirs(P.STATS_OUT, exist_ok=True)
    dest = os.path.join(P.STATS_OUT, "figure_data.json")
    json.dump(data, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"FIG 3 - securities ladder ({data['root']}, n={data['fig3']['n']})")
    for k, v in data["fig3"]["values"].items():
        print(f"  {k:<28} coherence={v[0]}  CQ={v[1]}  F1={v[2]}")
    print(f"\nFIG 4 - error types in {data['fig4']['n_ontologies']} LLM-only ontologies")
    for c in data["fig4"]["categories"]:
        print(f"  {c:<22} total={data['fig4']['totals'][c]:<5} "
              f"runs={data['fig4']['runs_with'][c]}/{data['fig4']['n_ontologies']}")
    print("\nFIG 5 - refinement iterations")
    for d, v in data["fig5"]["by_domain"].items():
        print(f"  {d:<14} n={v['n']} iterations={v['iterations']} counts={v['counts']} "
              f"median={v['median']}")
    print(f"\n-> {dest}")


if __name__ == "__main__":
    main()
