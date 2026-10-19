"""
Apply a gold-authored Competency-Question suite to a (differently-vocabularied) ontology.

The CQs are written in the gold ontology's terms. A generated ontology uses its own IRIs and
names, so each CQ's class/property references are re-mapped onto the target ontology via the
SAME normalised-label alignment used for P/R/F1 (onto_utils._norm). Fresh individuals in a CQ
(e.g. ea:a1) are rewritten into a neutral namespace and kept.

A CQ is scored against the target as:
  - UNANSWERABLE (fail): the target lacks an aligned class/property the CQ needs -> it literally
    cannot express the question.
  - PASS/FAIL: if all terms map, the entailment is decided by HermiT exactly as in cq_eval
    (membership / subsumption / inconsistency / consistency). A label may align but the target's
    *definition* may be too weak to entail the conclusion -> FAIL. This is the point: the metric
    rewards correct definitions, not just present labels.

Usage:  python cq_apply.py <cq_spec.json> <gold.ttl> <target.ttl>   (prints one JSON object)
The gold is used only to classify each CQ token as a class term, a property term, or a fresh
individual (by its role in the gold).
"""
import sys, os, re, json
import rdflib
from rdflib.namespace import RDF, RDFS, OWL

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import onto_utils
import cq_eval

IND_NS = "http://cq.local/ind#"


def norm_maps(g):
    """norm-label -> IRI string, for classes and for (object+datatype) properties."""
    cls, prop = {}, {}
    for c in g.subjects(RDF.type, OWL.Class):
        if isinstance(c, rdflib.URIRef):
            cls.setdefault(onto_utils._norm(onto_utils._label_or_local(g, c)), str(c))
    for pt in (OWL.ObjectProperty, OWL.DatatypeProperty):
        for p in g.subjects(RDF.type, pt):
            if isinstance(p, rdflib.URIRef):
                prop.setdefault(onto_utils._norm(onto_utils._label_or_local(g, p)), str(p))
    return cls, prop


def norm_sets(g):
    c, p = norm_maps(g)
    return set(c), set(p)


# CQ_FUZZY=1 enables a conservative containment fallback for vocabulary alignment: when a
# CQ term has no exact normalised-label match in the target, map it to the UNIQUE target term
# whose normalised name contains (or is contained by) the CQ term (e.g. hassystolic <->
# hassystolicvalue). Uniqueness is required, so ambiguous cases stay unanswerable (no false
# pass). Strict mode (default) is the headline; fuzzy is reported as a lenient secondary.
FUZZY_REMAP = os.environ.get("CQ_FUZZY", "0") == "1"


def _align(n, gen_map):
    iri = gen_map.get(n)
    if iri is not None:
        return iri
    if not FUZZY_REMAP or len(n) < 4:
        return None
    cands = {iri for k, iri in gen_map.items() if len(k) >= 4 and (n in k or k in n)}
    return next(iter(cands)) if len(cands) == 1 else None


def remap_text(text, dom_prefix, gold_cls, gold_prop, gen_cls, gen_prop, missing):
    """Substitute every <dom_prefix>:Name token: class/prop -> aligned target IRI (or record
    missing); anything else -> fresh individual IRI. Returns the rewritten Turtle string."""
    if not text:
        return text
    pat = re.compile(r"\b" + re.escape(dom_prefix) + r":([A-Za-z0-9_]+)")

    def sub(m):
        name = m.group(1)
        n = onto_utils._norm(name)
        if n in gold_cls:
            iri = _align(n, gen_cls)
            if iri is None:
                missing.append(f"class:{name}")
                return f"<{IND_NS}MISSING_{name}>"
            return f"<{iri}>"
        if n in gold_prop:
            iri = _align(n, gen_prop)
            if iri is None:
                missing.append(f"prop:{name}")
                return f"<{IND_NS}MISSING_{name}>"
            return f"<{iri}>"
        return f"<{IND_NS}{name}>"   # fresh individual

    return pat.sub(sub, text)


def apply_cq(gen_ttl, dom_prefix, gold_cls, gold_prop, gen_cls, gen_prop, cq):
    missing = []
    probe = dict(cq["probe"])
    setup_text = cq.get("setup", "")
    if isinstance(setup_text, list):
        setup_text = "\n".join(setup_text)
    args = (dom_prefix, gold_cls, gold_prop, gen_cls, gen_prop, missing)
    sub_cq = {"setup": remap_text(setup_text, *args), "probe": {"kind": probe["kind"]}}
    for k in ("ind", "cls", "sub", "sup"):
        if k in probe:
            sub_cq["probe"][k] = remap_text(probe[k], *args)

    if missing:
        return {"observed": "unanswerable", "pass": False, "missing": sorted(set(missing))}

    r = cq_eval.run_cq(gen_ttl, {"cq": "http://cq.local#"}, sub_cq)
    r["missing"] = []
    return r


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("usage: cq_apply.py <cq_spec.json> <gold.ttl> <target.ttl>")
        sys.exit(2)
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    gold_g = onto_utils.parse_ttl(open(sys.argv[2], encoding="utf-8").read())
    gen_ttl = open(sys.argv[3], encoding="utf-8").read()
    gen_g = onto_utils.parse_ttl(gen_ttl)
    dom_prefix = next(iter(spec["prefixes"]))
    gold_cls, gold_prop = norm_sets(gold_g)
    gen_cls, gen_prop = norm_maps(gen_g)

    results = []
    for cq in spec["cqs"]:
        r = apply_cq(gen_ttl, dom_prefix, gold_cls, gold_prop, gen_cls, gen_prop, cq)
        results.append({"id": cq["id"], "kind": cq["probe"]["kind"],
                        "category": cq.get("category", ""), "pass": r["pass"],
                        "observed": r["observed"], "missing": r.get("missing", []),
                        "err": r.get("err"), "nl": cq["nl"]})
    passed = sum(1 for r in results if r["pass"])
    print(json.dumps({"domain": spec["domain"], "target": os.path.basename(sys.argv[3]),
                      "total": len(results), "passed": passed,
                      "failed": len(results) - passed, "results": results}, indent=2))
