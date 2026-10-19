"""
Competency-Question (CQ) entailment evaluator for ontologies.

An ontology's value is not just structural overlap (P/R/F1) or internal coherence
(consistency C): it must ENTAIL the right conclusions. The canonical example is a
defined class -- "a male person who has a child is a Father" -- tested by asserting an
individual and checking the reasoner infers the membership.

This harness tests, against any ontology (gold or generated), a suite of CQs. Each CQ is
one of four probe kinds, all decided by HermiT (via Owlready2):

  membership   : O |= (ind : C)        -> tested as: O + setup + (ind : not C) is INCONSISTENT
                                          (control: O + setup alone must be CONSISTENT)
  subsumption  : O |= (Sub <= Sup)     -> tested as: O + (z:Sub and z:not Sup) is INCONSISTENT
                 and Sub satisfiable    AND  O + (z:Sub) is CONSISTENT (an unsatisfiable Sub is
                                          subsumed by every class, which must not count as a pass)
  inconsistency: O + setup is INCONSISTENT  (a constraint is violated, e.g. disjointness/cardinality)
  consistency  : O + setup is CONSISTENT    (a legitimate combination is allowed, e.g. orthogonal axes)

A CQ PASSES iff the reasoner's verdict matches the CQ's expectation. Running this on the
GOLD validates that (a) the reference ontology really supports the inference and (b) the
harness is correct, before applying it to model-generated ontologies.

Usage:  python cq_eval.py <cq_spec.json> <ontology.ttl>   (prints one JSON object)

`cls`/`sub`/`sup` may be a prefixed name (fis:EquityDerivative) OR an inline Turtle class
expression (a blank-node restriction), so necessary/sufficient conditions can be probed.
"""
import sys, os, json, tempfile, signal
import rdflib
import owlready2

CQ_TIMEOUT = int(os.environ.get("CQ_TIMEOUT", "40"))  # per reasoner call; guards HermiT hangs


class _CQTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise _CQTimeout()

NOTHING = "http://www.w3.org/2002/07/owl#Nothing"
THING = "http://www.w3.org/2002/07/owl#Thing"

STD_PREFIXES = {
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


def _header(prefixes):
    lines = [f"@prefix {p}: <{ns}> ." for p, ns in {**STD_PREFIXES, **prefixes}.items()]
    return "\n".join(lines) + "\n"


def _as_text(snippet):
    if snippet is None:
        return ""
    if isinstance(snippet, list):
        return "\n".join(snippet)
    return str(snippet)


def graph_with(base_ttl, prefixes, *snippets):
    """Base ontology graph + extra Turtle snippets (ABox / negation), merged."""
    g = rdflib.Graph()
    g.parse(data=base_ttl, format="turtle")
    hdr = _header(prefixes)
    for s in snippets:
        t = _as_text(s).strip()
        if t:
            g.parse(data=hdr + t, format="turtle")
    return g


def is_consistent(g):
    """(bool|None, err): True/False consistency via HermiT; None on load/serialise error."""
    fd, owlpath = tempfile.mkstemp(suffix=".owl")
    os.close(fd)
    try:
        g.serialize(destination=owlpath, format="xml")
        w = owlready2.World()
        w.get_ontology("file://" + os.path.abspath(owlpath)).load()
        old = signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(CQ_TIMEOUT)
        try:
            owlready2.sync_reasoner_hermit(w, infer_property_values=False, debug=0)
            return True, None
        except owlready2.OwlReadyInconsistentOntologyError:
            return False, None
        except _CQTimeout:
            return None, "reasoner-timeout"
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    except Exception as e:
        return None, str(e)
    finally:
        try:
            os.remove(owlpath)
        except OSError:
            pass


def run_cq(base_ttl, prefixes, cq):
    probe = cq["probe"]
    kind = probe["kind"]
    setup = cq.get("setup", "")

    if kind == "inconsistency":
        cons, err = is_consistent(graph_with(base_ttl, prefixes, setup))
        observed = {True: "consistent", False: "inconsistent", None: "error"}[cons]
        return {"observed": observed, "pass": cons is False, "err": err}

    if kind == "consistency":
        cons, err = is_consistent(graph_with(base_ttl, prefixes, setup))
        observed = {True: "consistent", False: "inconsistent", None: "error"}[cons]
        return {"observed": observed, "pass": cons is True, "err": err}

    if kind == "membership":
        ind, cls = probe["ind"], probe["cls"]
        neg = f"{ind} a [ a owl:Class ; owl:complementOf {cls} ] ."
        ctrl, _ = is_consistent(graph_with(base_ttl, prefixes, setup))
        cn, err = is_consistent(graph_with(base_ttl, prefixes, setup, neg))
        entailed = cn is False
        return {"observed": "entailed" if entailed else "not-entailed",
                "control_consistent": ctrl, "pass": (ctrl is True) and entailed, "err": err}

    if kind == "subsumption":
        sub, sup = probe["sub"], probe["sup"]
        ns0 = next(iter(prefixes))
        z = f"{ns0}:__cqz"
        neg = f"{z} a {sub} , [ a owl:Class ; owl:complementOf {sup} ] ."
        ctrl, _ = is_consistent(graph_with(base_ttl, prefixes))
        cn, err = is_consistent(graph_with(base_ttl, prefixes, setup, neg))
        entailed = cn is False
        # Sub <= Bottom <= Sup holds for every Sup, so the entailment test alone passes
        # vacuously when Sub is unsatisfiable; the CQ additionally requires Sub to have
        # an instance, i.e. O + setup + (z : Sub) must be consistent.
        sat, err2 = None, None
        if ctrl is True and entailed:
            sat, err2 = is_consistent(graph_with(base_ttl, prefixes, setup, f"{z} a {sub} ."))
        observed = ("entailed" if sat is True else "entailed-vacuously") if entailed else "not-entailed"
        return {"observed": observed, "control_consistent": ctrl, "sub_satisfiable": sat,
                "pass": (ctrl is True) and entailed and (sat is True), "err": err or err2}

    return {"observed": "unknown-kind", "pass": False, "err": f"unknown probe kind {kind}"}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: cq_eval.py <cq_spec.json> <ontology.ttl>")
        sys.exit(2)
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    base_ttl = open(sys.argv[2], encoding="utf-8").read()
    prefixes = spec["prefixes"]
    results = []
    for cq in spec["cqs"]:
        r = run_cq(base_ttl, prefixes, cq)
        results.append({"id": cq["id"], "kind": cq["probe"]["kind"],
                        "category": cq.get("category", ""), "pass": r["pass"],
                        "observed": r["observed"], "err": r.get("err"),
                        "control_consistent": r.get("control_consistent"),
                        "nl": cq["nl"]})
    passed = sum(1 for r in results if r["pass"])
    print(json.dumps({"domain": spec["domain"], "ontology": os.path.basename(sys.argv[2]),
                      "total": len(results), "passed": passed,
                      "failed": len(results) - passed, "results": results}, indent=2))
