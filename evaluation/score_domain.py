#!/usr/bin/env python3
"""Deterministic scoring of stored ontologies: every (run, configuration) is scored with
onto_utils eval (coherence, precision/recall/F1 against the reference ontology) and with
cq_apply (competency-question entailment under HermiT).

Usage:
  score_domain.py <domain> [gold.ttl] [cq.json] [--root results/primary_extractor] [...]

<domain> is securities | hypertension | assessment.
Layout: <root>/<domain folder>/<run>/<config>.ttl
Output: <root>/<domain folder>/scoring/{f1,cq}_<run>_<config>.json

Generation is blind to the reference ontology; scoring sees it (separate step).
"""
import sys, os, json, argparse, subprocess, collections
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "..", "src"))
import paths as P                                          # noqa: E402

PROJ = P.ROOT
VENV = P.PYTHON
OU = P.ONTO_UTILS
CQAPPLY = os.path.join(BASE, "cq_apply.py")

DEFAULT_CFG = ["llm_only", "prune", "single_pass", "hybrid"]


def bycat(j):
    cc = collections.defaultdict(lambda: [0, 0])
    for r in j.get("results", []):
        c = r.get("category", "?")
        cc[c][1] += 1
        if r["pass"]:
            cc[c][0] += 1
    return {k: {"passed": v[0], "total": v[1]} for k, v in cc.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("gold", nargs="?", default=None,
                    help="reference ontology (default: the reference ontology of the domain)")
    ap.add_argument("cq", nargs="?", default=None,
                    help="competency-question suite (default: the canonical suite)")
    ap.add_argument("--root", default="results/primary_extractor",
                    help="result tree, relative to the repository root or absolute")
    ap.add_argument("--configs", default=",".join(DEFAULT_CFG))
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--f1-prefix", default="f1")
    ap.add_argument("--cq-prefix", default="cq")
    ap.add_argument("--full-cq", action="store_true",
                    help="also write the per-question results[] array to the CQ file")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--scoring-dir", default="scoring",
                    help="output folder inside <root>/<domain>/")
    ap.add_argument("--skip-f1", action="store_true", help="score competency questions only")
    a = ap.parse_args()
    a.gold = a.gold or P.gold_path(a.domain)
    a.cq = a.cq or P.cq_path(a.domain)

    root = P.resolve_root(a.root)
    out = P.domain_dir(root, a.domain)
    score = os.path.join(out, a.scoring_dir)
    os.makedirs(score, exist_ok=True)
    runs = [f"run{i:02d}" for i in range(1, a.runs + 1)]
    cfgs = [c.strip() for c in a.configs.split(",") if c.strip()]

    missing, errors = [], []

    def cell(args):
        run, cfg = args
        ttl = os.path.join(out, run, f"{cfg}.ttl")
        if not os.path.exists(ttl):
            missing.append(f"{run}/{cfg}")
            return 0
        try:
            if a.skip_f1:
                raise StopIteration
            r = subprocess.run([VENV, OU, "eval", ttl, a.gold],
                               capture_output=True, text=True, timeout=300)
            json.dump(json.loads(r.stdout),
                      open(os.path.join(score, f"{a.f1_prefix}_{run}_{cfg}.json"), "w"),
                      indent=1)
        except StopIteration:
            pass
        except Exception as e:
            errors.append(f"f1:{run}/{cfg}:{repr(e)[:80]}")
        try:
            r = subprocess.run([VENV, CQAPPLY, a.cq, a.gold, ttl],
                               capture_output=True, text=True, timeout=900)
            j = json.loads(r.stdout)
            payload = {"passed": j["passed"], "total": j["total"],
                       "failed": j["failed"], "by_category": bycat(j)}
            if a.full_cq:
                payload["results"] = j["results"]
            json.dump(payload,
                      open(os.path.join(score, f"{a.cq_prefix}_{run}_{cfg}.json"), "w"),
                      indent=1)
        except Exception as e:
            errors.append(f"cq:{run}/{cfg}:{repr(e)[:80]}")
        print(f"  {run}/{cfg} ok", flush=True)
        return 1

    cells = [(r, c) for r in runs for c in cfgs]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        done = sum(ex.map(cell, cells))

    print(json.dumps({"domain": a.domain, "root": root, "scored_cells": done,
                      "missing": missing, "errors": errors}, indent=1))


if __name__ == "__main__":
    main()
