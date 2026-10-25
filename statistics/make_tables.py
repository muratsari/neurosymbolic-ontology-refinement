#!/usr/bin/env python3
"""Rebuilds the paper's Tables 1-4 and the per-run score sheets from the stored score files.

No LLM call, no reasoner call, no random numbers: every value is computed from
  results/<arm>/<domain folder>/scoring/{f1,cq}_<run>_<config>.json
with the same primitives as cross_model_stats.py (stats_core.py: one-sided paired sign-flip test,
exact up to 20 non-zero differences and deterministic Monte Carlo beyond, deterministic percentile
bootstrap, Cohen's dz, Wilson interval).

Outputs
  results/primary_extractor/per_run_scores.csv   one row per domain x run x configuration
  results/second_extractor/per_run_scores.csv
  statistics/table1_finance_performance.csv
  statistics/table2_ablation.csv
  statistics/table3_cross_domain.csv
  statistics/table4_cross_model.csv
  statistics/paired_tests.csv      every paired test behind the tables (long format)
  statistics/tables.md             the four tables, laid out as in the paper

Usage: python statistics/make_tables.py
"""
import csv, json, os, sys, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import paths as P                                                    # noqa: E402
from stats_core import signflip, cohen_dz, boot_ci, wilson           # noqa: E402

RUNS = sorted(x for x in os.listdir(P.domain_dir(P.PRIMARY, "securities")) if x.startswith("run"))
# ladder key, file stem, name used in the paper
CFG = [("A", "llm_only", "LLM-only"),
       ("Bp", "prune", "Reasoner-prune (control)"),
       ("Br", "single_pass", "LLM + single-pass repair"),
       ("C", "hybrid", "Proposed (Hybrid)")]
NAME = {k: n for k, _, n in CFG}
ARMS = [("primary_extractor", P.PRIMARY), ("second_extractor", P.SECOND)]
ARM_LABEL = {"primary_extractor": "Primary extractor", "second_extractor": "Second extractor"}
DELTA = 0.02                       # pre-specified non-inferiority margin (paper Section 4.7)
OUT = P.STATS_OUT


def _json(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    return json.load(open(path, encoding="utf-8"))


def load(root, domain):
    """{(run, ladder key): score record} for one arm and domain."""
    cells = {}
    sc = P.scoring_dir(root, domain)
    for r in RUNS:
        for key, stem, _ in CFG:
            a = _json(os.path.join(sc, f"f1_{r}_{stem}.json"))
            q = _json(os.path.join(sc, f"cq_{r}_{stem}.json"))
            if a is None or q is None:
                continue
            consistent = bool(a.get("consistent", True))
            cells[(r, key)] = {
                "consistent": consistent, "unsatisfiable": a["unsatisfiable"],
                # paper Section 4.3: globally consistent AND no unsatisfiable named class
                "coherent": consistent and a["unsatisfiable"] == 0,
                "consistency_C": a["consistency_C"], "gen_classes": a["gen_classes"],
                "precision": a["precision"], "recall": a["recall"], "f1": a["f1"],
                "concept_f1": a["concept_f1"], "relation_f1": a["relation_f1"],
                "cq_passed": q["passed"], "cq_total": q["total"]}
    return cells


def column(cells, key, field):
    return [cells[(r, key)][field] for r in RUNS if (r, key) in cells]


def paired(cells, a, b, field):
    return [cells[(r, b)][field] - cells[(r, a)][field]
            for r in RUNS if (r, a) in cells and (r, b) in cells]


def mean_sd(v):
    return (st.mean(v), st.stdev(v) if len(v) > 1 else 0.0)


def summary(cells):
    """Per-configuration descriptives of one arm x domain."""
    out = {}
    for key, _, _ in CFG:
        n = len(column(cells, key, "f1"))
        if not n:
            continue
        k = sum(1 for x in column(cells, key, "coherent") if x)
        total = column(cells, key, "cq_total")[0]
        lo, hi = wilson(k, n)
        out[key] = {"n": n, "coherent": k, "coherence": k / n, "coh_lo": lo, "coh_hi": hi,
                    "cq_total": total,
                    "cq_passed": mean_sd(column(cells, key, "cq_passed")),
                    "cq_acc": mean_sd([x / total for x in column(cells, key, "cq_passed")]),
                    "precision": mean_sd(column(cells, key, "precision")),
                    "recall": mean_sd(column(cells, key, "recall")),
                    "f1": mean_sd(column(cells, key, "f1"))}
    return out


def tests(cells):
    """The paired tests of Section 4.7 for one arm x domain."""
    rows = []
    for a, b in (("A", "Br"), ("Br", "C"), ("A", "C")):
        d = [int(cells[(r, b)]["coherent"]) - int(cells[(r, a)]["coherent"])
             for r in RUNS if (r, a) in cells and (r, b) in cells]
        rows.append({"axis": "coherence", "contrast": f"{a}<{b}", "n_pairs": len(d),
                     "delta": st.mean(d), "p": signflip(d),
                     "pos": sum(1 for x in d if x > 0), "neg": sum(1 for x in d if x < 0)})
    for a, b in (("A", "Br"), ("Br", "C"), ("A", "C"), ("Bp", "C")):
        d = paired(cells, a, b, "cq_passed")
        lo, hi = boot_ci(d)
        rows.append({"axis": "cq_passed", "contrast": f"{a}<{b}", "n_pairs": len(d),
                     "delta": st.mean(d), "p": signflip(d), "ci95_low": lo, "ci95_high": hi,
                     "dz": cohen_dz(d),
                     "pos": sum(1 for x in d if x > 1e-12), "neg": sum(1 for x in d if x < -1e-12)})
    d = paired(cells, "Br", "C", "f1")
    lo, hi = boot_ci(d)
    rows.append({"axis": "f1", "contrast": f"non-inferiority C vs Br (margin {DELTA})",
                 "n_pairs": len(d), "delta": st.mean(d), "p": signflip([x + DELTA for x in d]),
                 "ci95_low": lo, "ci95_high": hi, "dz": cohen_dz(d)})
    d = paired(cells, "Bp", "C", "f1")
    rows.append({"axis": "f1", "contrast": "Bp<C", "n_pairs": len(d), "delta": st.mean(d),
                 "p": signflip(d)})
    return rows


def find(rows, axis, contrast):
    return next(r for r in rows if r["axis"] == axis and r["contrast"].startswith(contrast))


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #
SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def fmt_p(p):
    if p >= 0.9995:
        return "p = 1.000"
    if p >= 0.001 - 5e-5:
        return f"p = {p:.3f}"
    if p >= 1e-4:
        return f"p = {p:.4f}"
    m, e = f"{p:.1e}".split("e")
    return f"p = {m} × 10{str(int(e)).translate(SUP)}"


def pm(ms, nd):
    return f"{ms[0]:.{nd}f}±{ms[1]:.{nd}f}"


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def r4(x):
    return "" if x is None else round(x, 4)


# --------------------------------------------------------------------------- #
def main():
    data = {arm: {d: load(root, d) for d in P.DOMAINS} for arm, root in ARMS}
    summ = {arm: {d: summary(c) for d, c in v.items() if c} for arm, v in data.items()}
    test = {arm: {d: tests(c) for d, c in v.items() if c} for arm, v in data.items()}
    md = ["# Tables 1-4, recomputed from the stored score files", "",
          "Generated by `statistics/make_tables.py`. Coherence is the proportion of runs whose final "
          "ontology is globally consistent and has no unsatisfiable named class; other cells are "
          f"mean±SD over the n = {len(RUNS)} paired runs.", ""]

    # ---- per-run sheets ------------------------------------------------------
    for arm, root in ARMS:
        rows = []
        for d in P.DOMAINS:
            for r in RUNS:
                for key, stem, _ in CFG:
                    c = data[arm][d].get((r, key))
                    if c:
                        rows.append([arm, P.PAPER_NAME[d], d, r, stem, key, int(c["consistent"]),
                                     c["unsatisfiable"], int(c["coherent"]), c["consistency_C"],
                                     c["gen_classes"], c["precision"], c["recall"], c["f1"],
                                     c["concept_f1"], c["relation_f1"], c["cq_passed"],
                                     c["cq_total"]])
        write_csv(os.path.join(root, "per_run_scores.csv"),
                  ["arm", "domain", "domain_key", "run", "config", "ladder", "consistent",
                   "unsatisfiable_classes", "coherent", "consistency_C", "generated_classes",
                   "precision", "recall", "f1", "concept_f1", "relation_f1", "cq_passed",
                   "cq_total"], rows)
        print(f"{arm}: {len(rows)} rows -> per_run_scores.csv")

    # ---- Table 1: finance, primary extractor ---------------------------------
    s = summ["primary_extractor"]["securities"]
    rows, lines = [], ["## Table 1: finance, primary extractor", "",
                       "| Model (finance) | Coherence | CQ Accuracy | Precision | F1 | Recall |",
                       "|---|---|---|---|---|---|"]
    for key in ("A", "Br", "C"):
        x = s[key]
        rows.append([NAME[key], x["coherent"], x["n"], r4(x["coherence"]), r4(x["coh_lo"]),
                     r4(x["coh_hi"]), r4(x["cq_passed"][0] / x["cq_total"]), r4(x["cq_passed"][0]),
                     r4(x["cq_passed"][1]), x["cq_total"], r4(x["precision"][0]),
                     r4(x["precision"][1]), r4(x["f1"][0]), r4(x["f1"][1]), r4(x["recall"][0]),
                     r4(x["recall"][1])])
        lines.append(f"| {NAME[key]} | {x['coherence']:.2f} ({x['coherent']}/{x['n']}; 95% CI "
                     f"{x['coh_lo']:.2f}–{x['coh_hi']:.2f}) | "
                     f"{x['cq_passed'][0] / x['cq_total']:.2f} ({pm(x['cq_passed'], 1)}/"
                     f"{x['cq_total']}) | {pm(x['precision'], 3)} | {pm(x['f1'], 3)} | "
                     f"{pm(x['recall'], 3)} |")
    write_csv(os.path.join(OUT, "table1_finance_performance.csv"),
              ["model", "coherent_runs", "n", "coherence", "coherence_ci95_low",
               "coherence_ci95_high", "cq_accuracy", "cq_passed_mean", "cq_passed_sd", "cq_total",
               "precision_mean", "precision_sd", "f1_mean", "f1_sd", "recall_mean", "recall_sd"],
              rows)
    md += lines + [""]

    # ---- Table 2: ablation (finance, primary extractor) ----------------------
    rows, lines = [], ["## Table 2: ablation (finance, primary extractor)", "",
                       "| Configuration | Coherence | CQ Accuracy | ΔCoherence vs. LLM-only |", "|---|---|---|---|"]
    base = s["A"]["coherence"]
    for key in ("A", "Br", "C", "Bp"):
        x = s[key]
        acc = x["cq_passed"][0] / x["cq_total"]
        dcoh = None if key == "A" else x["coherence"] - base
        rows.append([NAME[key], r4(x["coherence"]), r4(acc), r4(dcoh)])
        lines.append(f"| {NAME[key]} | {x['coherence']:.2f} | {acc:.2f} | "
                     + ("–" if dcoh is None else f"{dcoh:+.2f}") + " |")
    write_csv(os.path.join(OUT, "table2_ablation.csv"),
              ["configuration", "coherence", "cq_accuracy", "delta_coherence_vs_llm_only"], rows)
    md += lines + [""]

    # ---- Table 3: cross-domain (primary extractor) ---------------------------
    rows, lines = [], ["## Table 3: cross-domain, primary extractor (LLM-only to hybrid)", "",
                       "| Domain | Coherence A→C | CQ Accuracy A→C | F1 A→C (brake) |",
                       "|---|---|---|---|"]
    for d in ("assessment", "hypertension", "securities"):
        a, c = summ["primary_extractor"][d]["A"], summ["primary_extractor"][d]["C"]
        rows.append([P.PAPER_NAME[d], d, r4(a["coherence"]), r4(c["coherence"]),
                     r4(a["cq_acc"][0]), r4(a["cq_acc"][1]), r4(c["cq_acc"][0]),
                     r4(c["cq_acc"][1]), r4(a["f1"][0]), r4(a["f1"][1]), r4(c["f1"][0]),
                     r4(c["f1"][1])])
        lines.append(f"| {P.PAPER_NAME[d]} ({d}) | {a['coherence']:.2f} → {c['coherence']:.2f} | "
                     f"{pm(a['cq_acc'], 2)} → {pm(c['cq_acc'], 2)} | "
                     f"{pm(a['f1'], 3)} → {pm(c['f1'], 3)} |")
    write_csv(os.path.join(OUT, "table3_cross_domain.csv"),
              ["domain", "domain_key", "coherence_A", "coherence_C", "cq_accuracy_A_mean",
               "cq_accuracy_A_sd", "cq_accuracy_C_mean", "cq_accuracy_C_sd", "f1_A_mean",
               "f1_A_sd", "f1_C_mean", "f1_C_sd"], rows)
    md += lines + [""]

    # ---- Table 4: cross-model ------------------------------------------------
    arms = [a for a, _ in ARMS if summ[a]]
    rows, lines = [], ["## Table 4: cross-model replication", "",
                       "| Domain | Axis | " + " | ".join(ARM_LABEL[a] for a in arms) + " |",
                       "|---|---|" + "---|" * len(arms)]
    for d in P.DOMAINS:
        cell = {a: {} for a in arms}
        for a in arms:
            if d not in summ[a]:
                cell[a] = dict.fromkeys(("runs", "coh", "cq", "f1"), "n/a")
                continue
            sa, ta = summ[a][d], test[a][d]
            coh, cq, ni = find(ta, "coherence", "A<C"), find(ta, "cq_passed", "A<C"), \
                find(ta, "f1", "non-inferiority")
            cell[a] = {"runs": f"{sa['A']['coherent']}/{sa['A']['n']} → "
                               f"{sa['C']['coherent']}/{sa['C']['n']}",
                       "coh": fmt_p(coh["p"]),
                       "cq": f"{cq['delta']:+.2f}, {fmt_p(cq['p'])}, dz = {cq['dz']:.2f}",
                       "f1": f"ΔF1 = {ni['delta']:+.4f}"}
            rows.append([P.PAPER_NAME[d], d, a, sa["A"]["coherent"], sa["C"]["coherent"],
                         sa["A"]["n"], coh["p"], r4(cq["delta"]), cq["p"], r4(cq["dz"]),
                         r4(ni["delta"]), ni["p"]])
        for i, (axis, k) in enumerate((("Coherent runs (A → C)", "runs"),
                                       ("Coherence A < C", "coh"), ("CQ accuracy A < C", "cq"),
                                       ("F1 non-inferiority (hybrid vs. single-pass)", "f1"))):
            lines.append(f"| {P.PAPER_NAME[d] if i == 0 else ''} | {axis} | "
                         + " | ".join(cell[a][k] for a in arms) + " |")
    write_csv(os.path.join(OUT, "table4_cross_model.csv"),
              ["domain", "domain_key", "arm", "coherent_runs_A", "coherent_runs_C", "n",
               "coherence_A<C_p", "cq_passed_delta_A<C", "cq_A<C_p", "cq_A<C_dz",
               "deltaF1_C_minus_Br", "f1_noninferiority_p"], rows)
    md += lines + [""]

    # ---- every paired test, long format --------------------------------------
    rows = []
    for a in arms:
        for d in P.DOMAINS:
            for t in test[a].get(d, []):
                rows.append([a, P.PAPER_NAME[d], d, t["axis"], t["contrast"], t["n_pairs"],
                             round(t["delta"], 4), t["p"], r4(t.get("ci95_low")),
                             r4(t.get("ci95_high")), r4(t.get("dz")), t.get("pos", ""),
                             t.get("neg", "")])
    write_csv(os.path.join(OUT, "paired_tests.csv"),
              ["arm", "domain", "domain_key", "axis", "contrast", "n_pairs", "mean_delta",
               "p_one_sided_signflip", "ci95_low", "ci95_high", "cohen_dz", "pairs_positive",
               "pairs_negative"], rows)

    open(os.path.join(OUT, "tables.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md))
    print(f"-> {os.path.relpath(OUT, P.ROOT)}/")

    # ---- cross-check against the JSON written by the two statistics scripts ---
    bad = 0
    for arm, fn in (("primary_extractor", "cross_model_stats_primary_extractor.json"),
                    ("second_extractor", "cross_model_stats_second_extractor.json")):
        ref = _json(os.path.join(P.STATS_OUT, fn))
        if not ref:
            continue
        for d, t in test[arm].items():
            for js, axis, contrast in (("cons_A<C", "coherence", "A<C"), ("cq_A<C", "cq_passed", "A<C"),
                                       ("cq_Bp<C", "cq_passed", "Bp<C")):
                if d in ref and js in ref[d] and \
                        abs(ref[d][js]["p"] - round(find(t, axis, contrast)["p"], 5)) > 1e-9:
                    bad += 1
                    print(f"  MISMATCH {fn} {d} {js}")
        print(f"cross-check with {fn}: {'ok' if not bad else 'MISMATCH'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
