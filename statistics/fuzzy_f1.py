#!/usr/bin/env python3
"""Supplementary morphological-matching (fuzzy) F1 (paper §4.1).

Strict F1 aligns a generated term with a reference term only when their normalised labels are
identical (onto_utils._norm). The fuzzy variant adds the containment fallback that CQ scoring
uses under CQ_FUZZY=1 (code/scoring/cq_apply.py): a generated name without an exact match is
mapped to the UNIQUE reference name of the same kind (class or object property) that contains it
or is contained in it (both at least 4 characters, reference name not already matched exactly),
e.g. systolicpressure <-> systolicbloodpressure. Ambiguous cases stay unmatched. Elements are then
compared exactly as in strict F1 (classes, named subclass pairs, object properties).

Usage (from the repository root):
  python statistics/fuzzy_f1.py results/primary_extractor
Writes statistics/fuzzy_f1_<arm>.json: per domain and configuration the mean strict and fuzzy F1
and their difference.
"""
import os, sys, json, glob, statistics as st
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import paths as P                                              # noqa: E402

PROJ = P.ROOT
import onto_utils as ou                                        # noqa: E402

DOMAINS = ["securities", "hypertension", "assessment"]
CONFIGS = ["llm_only", "prune", "single_pass", "hybrid"]
MIN_LEN = 4


def fuzzy_map(gen_names, gold_names):
    """gen name -> gold name: exact first, then the unique containment partner."""
    m = {n: n for n in gen_names if n in gold_names}
    free = gold_names - set(m.values())
    for n in gen_names:
        if n in m or len(n) < MIN_LEN:
            continue
        cands = {k for k in free if len(k) >= MIN_LEN and (n in k or k in n)}
        if len(cands) == 1:
            m[n] = next(iter(cands))
    return m


def rename(els, cmap, pmap):
    out = set()
    for e in els:
        if e[0] == "class":
            out.add(("class", cmap.get(e[1], e[1])))
        elif e[0] == "subclass":
            out.add(("subclass", cmap.get(e[1], e[1]), cmap.get(e[2], e[2])))
        else:
            out.add(("objprop", pmap.get(e[1], e[1])))
    return out


def names(els, kind):
    return {e[1] for e in els if e[0] == kind}


def score(args):
    ttl, gold_ttl = args
    gen, _ = ou.elements(ou.parse_ttl(open(ttl, encoding="utf-8").read()))
    gold, _ = ou.elements(ou.parse_ttl(open(gold_ttl, encoding="utf-8").read()))
    cmap = fuzzy_map(names(gen, "class"), names(gold, "class"))
    pmap = fuzzy_map(names(gen, "objprop"), names(gold, "objprop"))
    return ou.prf1(gen, gold)["f1"], ou.prf1(rename(gen, cmap, pmap), gold)["f1"]


def main():
    root = P.resolve_root(sys.argv[1] if len(sys.argv) > 1 else "results/primary_extractor")
    out = {}
    for d in DOMAINS:
        gold = P.gold_path(d)
        runs = sorted(glob.glob(os.path.join(P.domain_dir(root, d), "run*")))
        out[d] = {}
        for cfg in CONFIGS:
            cells = [(os.path.join(r, f"{cfg}.ttl"), gold) for r in runs]
            with ProcessPoolExecutor() as ex:
                res = list(ex.map(score, cells))
            strict, fuzzy = [r[0] for r in res], [r[1] for r in res]
            out[d][cfg] = {"n": len(res), "strict_f1": round(st.mean(strict), 4),
                           "fuzzy_f1": round(st.mean(fuzzy), 4),
                           "delta": round(st.mean(f - s for s, f in res), 4)}
            o = out[d][cfg]
            print(f"{d:<13} {cfg:<12} strict {o['strict_f1']:.3f}  fuzzy {o['fuzzy_f1']:.3f}  "
                  f"delta {o['delta']:+.3f}", flush=True)
    dest = P.stats_dest(root, "fuzzy_f1.json")
    json.dump(out, open(dest, "w", encoding="utf-8"), indent=2)
    print("->", dest)


if __name__ == "__main__":
    main()
