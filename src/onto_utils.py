"""
Ontology utilities for the neuro-symbolic pipeline: parse/serialize, DL reasoning
(consistency + unsatisfiable classes + 0-1 consistency score C), element
extraction, lexical alignment, and P/R/F1.

Depends on rdflib + owlready2 (HermiT). Stdlib otherwise.
"""
import os, re, sys, tempfile, json
import rdflib
from rdflib.namespace import RDF, RDFS, OWL, XSD
import owlready2

SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")
NOTHING = "http://www.w3.org/2002/07/owl#Nothing"
THING = "http://www.w3.org/2002/07/owl#Thing"


# --------------------------------------------------------------------------- #
# Parsing / serialisation
# --------------------------------------------------------------------------- #
def parse_ttl(text):
    """Parse a Turtle string into an rdflib Graph (raises on syntax error)."""
    g = rdflib.Graph()
    g.parse(data=text, format="turtle")
    return g


def extract_turtle(llm_text):
    """Pull a Turtle body out of an LLM response (fenced ```turtle block, or raw)."""
    m = re.search(r"```(?:turtle|ttl)?\s*(.*?)```", llm_text, flags=re.S | re.I)
    body = m.group(1) if m else llm_text
    # ensure common prefixes exist so a bare body still parses
    head = ""
    if "@prefix owl:" not in body:
        head += "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    if "@prefix rdf:" not in body:
        head += "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
    if "@prefix rdfs:" not in body:
        head += "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    if "@prefix xsd:" not in body:
        head += "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    if "@prefix skos:" not in body:
        head += "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
    return head + body


def graph_to_owl(g, path):
    g.serialize(destination=path, format="xml")


def local(uri):
    s = str(uri)
    for sep in ("#", "/"):
        if sep in s:
            t = s.rsplit(sep, 1)[1]
            if t:
                return t
    return s


def normalize_datatypes(g):
    """xsd:date -> xsd:dateTime. A deterministic step documented in the protocol.

    A single xsd:date literal in a raw extraction makes HermiT report global inconsistency
    (C = 0) although the ontology contains no real logical contradiction. Paper Section 4.3
    records this artefact and that it is normalised before scoring; the same transformation
    is applied in the generation pipeline.
    """
    out = rdflib.Graph()
    for pfx, ns in g.namespaces():
        out.bind(pfx, ns)

    def fix(t):
        if isinstance(t, rdflib.URIRef) and t == XSD.date:
            return XSD.dateTime
        if isinstance(t, rdflib.Literal) and t.datatype == XSD.date:
            return rdflib.Literal(str(t), datatype=XSD.dateTime)
        return t

    for s_, p_, o_ in g:
        out.add((fix(s_), fix(p_), fix(o_)))
    return out


# --------------------------------------------------------------------------- #
# DL reasoning  (HermiT via owlready2)
# --------------------------------------------------------------------------- #
def reason(g):
    """Run HermiT on an rdflib graph. Returns dict with consistency, the list of
    unsatisfiable named classes, and the 0-1 consistency score C."""
    named = sorted({c for c in g.subjects(RDF.type, OWL.Class)
                    if isinstance(c, rdflib.URIRef)}, key=local)
    n = len(named)
    fd, owlpath = tempfile.mkstemp(suffix=".owl")
    os.close(fd)
    try:
        g.serialize(destination=owlpath, format="xml")
        w = owlready2.World()
        w.get_ontology("file://" + os.path.abspath(owlpath)).load()
        consistent = True
        try:
            owlready2.sync_reasoner_hermit(w, infer_property_values=False, debug=0)
        except owlready2.OwlReadyInconsistentOntologyError:
            consistent = False
        unsat = sorted({c.iri for c in w.inconsistent_classes()
                        if c.iri not in (NOTHING, THING)})
    except Exception as e:
        # malformed ontology -> treat as maximally inconsistent
        return {"consistent": False, "unsatisfiable": [], "C": 0.0,
                "n_classes": n, "error": str(e)}
    finally:
        try:
            os.remove(owlpath)
        except OSError:
            pass
    if not consistent:
        C = 0.0
    elif n:
        C = round(1.0 - len(unsat) / n, 4)
    else:
        C = 1.0
    return {"consistent": consistent, "unsatisfiable": unsat, "C": C, "n_classes": n}


def detect_errors(g):
    """Reasoner + structural error list for the refinement loop."""
    r = reason(g)
    errors = []
    if not r["consistent"]:
        errors.append({"type": "inconsistency",
                       "detail": "the ontology has no model (globally inconsistent)"})
    for u in r["unsatisfiable"]:
        errors.append({"type": "unsatisfiable_class", "focus": local(u),
                       "detail": f"class '{local(u)}' is unsatisfiable (equivalent to owl:Nothing)"})
    # structural: object properties missing domain or range
    for p in sorted({p for p in g.subjects(RDF.type, OWL.ObjectProperty)
                     if isinstance(p, rdflib.URIRef)}, key=local):
        if (p, RDFS.domain, None) not in g:
            errors.append({"type": "missing_domain", "focus": local(p),
                           "detail": f"object property '{local(p)}' has no rdfs:domain"})
        if (p, RDFS.range, None) not in g:
            errors.append({"type": "missing_range", "focus": local(p),
                           "detail": f"object property '{local(p)}' has no rdfs:range"})
    return errors, r


# --------------------------------------------------------------------------- #
# Element extraction + lexical alignment  (for P/R/F1)
# --------------------------------------------------------------------------- #
def _norm(s):
    """Lexical normalisation for alignment: lowercase, strip non-alnum, naive singular."""
    s = re.sub(r"[^a-z0-9]", "", str(s).lower())
    if len(s) > 4 and s.endswith("s") and not s.endswith("ss"):
        s = s[:-1]
    return s


def _label_or_local(g, c):
    """Alignment name for a term: its rdfs:label, else the IRI local part.

    A term may carry several labels (the extraction prompt asks for synonyms to
    go into rdfs:label). g.value() would then return an arbitrary one, and since
    the choice depends on the graph's internal ordering the same ontology could
    score differently after a rebuild. We therefore pick deterministically:
    the label that agrees with the IRI local name if there is one, otherwise the
    lexicographically first. With zero or one label this is exactly the previous
    behaviour, so results computed before this change are unaffected.
    """
    labs = sorted(str(x) for x in g.objects(c, RDFS.label))
    if not labs:
        return local(c)
    if len(labs) == 1:
        return labs[0]
    loc = local(c)
    for lab in labs:
        if _norm(lab) == _norm(loc):
            return lab
    return labs[0]


def elements(g):
    """Return the normalised element set of an ontology for micro P/R/F1:
    ('class', n) , ('subclass', child_n, parent_n) , ('objprop', n).
    Also returns the raw concept labels for reporting."""
    classes = {c for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, rdflib.URIRef)}
    cls_norm = {c: _norm(_label_or_local(g, c)) for c in classes}
    objprops = {p for p in g.subjects(RDF.type, OWL.ObjectProperty)
                if isinstance(p, rdflib.URIRef)}
    els = set()
    labels = {}
    for c in classes:
        els.add(("class", cls_norm[c]))
        labels[cls_norm[c]] = _label_or_local(g, c)
    # subClassOf between two named classes
    for a, b in g.subject_objects(RDFS.subClassOf):
        if a in cls_norm and b in cls_norm:
            els.add(("subclass", cls_norm[a], cls_norm[b]))
    for p in objprops:
        els.add(("objprop", _norm(_label_or_local(g, p))))
    return els, labels


def prf1(gen_set, gold_set):
    """Micro precision / recall / F1 over element sets."""
    tp = len(gen_set & gold_set)
    p = tp / len(gen_set) if gen_set else 0.0
    r = tp / len(gold_set) if gold_set else 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4),
            "tp": tp, "gen": len(gen_set), "gold": len(gold_set)}


def evaluate_against_gold(gen_graph, gold_graph):
    """Concept-level, relation-level (subclass+objprop) and overall (micro) P/R/F1."""
    gen, _ = elements(gen_graph)
    gold, _ = elements(gold_graph)
    by = {"class": (set(), set()), "rel": (set(), set())}
    for e in gen:
        by["class" if e[0] == "class" else "rel"][0].add(e)
    for e in gold:
        by["class" if e[0] == "class" else "rel"][1].add(e)
    return {
        "overall": prf1(gen, gold),
        "concept": prf1(*by["class"]),
        "relation": prf1(*by["rel"]),
    }


# --------------------------------------------------------------------------- #
# Redundancy  (for the draft's Q = a*Consistency + b*Coverage - c*Redundancy)
# --------------------------------------------------------------------------- #
def redundancy(g):
    """Ontology redundancy signals (higher = more redundant/worse):
      - redundant subClassOf axioms: an asserted named A subClassOf B that is already
        ENTAILED transitively (there is another asserted parent C of A with B among C's
        ancestors) -> the direct edge is logically redundant (transitive-reduction sense).
      - duplicate named classes / object properties sharing a normalised label.
    Returns ratios + counts; `redundancy_ratio` (redundant subclass edges / all named subclass
    edges) is the primary R used in Q.
    """
    classes = {c for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, rdflib.URIRef)}
    # asserted named subClassOf edges child -> set(parents)
    parents = {}
    edges = []
    for a, b in g.subject_objects(RDFS.subClassOf):
        if a in classes and b in classes and a != b:
            parents.setdefault(a, set()).add(b)
            edges.append((a, b))

    # ancestors over the asserted DAG (memoised)
    _anc = {}
    def ancestors(x, stack=None):
        if x in _anc:
            return _anc[x]
        stack = stack or set()
        acc = set()
        for p in parents.get(x, ()):
            if p in stack:
                continue
            acc.add(p)
            acc |= ancestors(p, stack | {x})
        _anc[x] = acc
        return acc

    redundant = 0
    for a, b in edges:
        # b is redundant as a DIRECT parent of a if reachable via another parent c != b
        if any(c != b and b in ancestors(c) for c in parents.get(a, ())):
            redundant += 1

    # duplicate labels
    def dup_pairs(entities):
        buckets = {}
        for e in entities:
            buckets.setdefault(_norm(_label_or_local(g, e)), 0)
            buckets[_norm(_label_or_local(g, e))] += 1
        return sum(v - 1 for v in buckets.values() if v > 1)

    objprops = {p for p in g.subjects(RDF.type, OWL.ObjectProperty) if isinstance(p, rdflib.URIRef)}
    n_edges = len(edges)
    dup_c = dup_pairs(classes)
    dup_p = dup_pairs(objprops)
    return {
        "redundancy_ratio": round(redundant / n_edges, 4) if n_edges else 0.0,
        "redundant_subclass": redundant, "n_subclass": n_edges,
        "duplicate_classes": dup_c, "duplicate_objprops": dup_p,
        "n_classes": len(classes),
    }


# Blank nodes that are legitimately ROOT-LEVEL: they carry a type but are never
# the object of any triple. A naive "unreferenced blank node = garbage" test
# deletes these, which silently strips every disjointness axiom from the graph.
STANDALONE_AXIOM_TYPES = {OWL.AllDisjointClasses, OWL.AllDifferent,
                          OWL.AllDisjointProperties, OWL.Axiom,
                          OWL.NegativePropertyAssertion}
# Predicates whose object is an rdf:List head.
LIST_PREDICATES = (OWL.members, OWL.intersectionOf, OWL.unionOf, OWL.oneOf,
                   OWL.distinctMembers)
# A well-formed owl:Restriction needs a filler; without one it is a remnant.
RESTRICTION_FILLERS = (OWL.someValuesFrom, OWL.allValuesFrom, OWL.hasValue,
                       OWL.onClass, OWL.onDataRange, OWL.cardinality,
                       OWL.minCardinality, OWL.maxCardinality,
                       OWL.qualifiedCardinality, OWL.minQualifiedCardinality,
                       OWL.maxQualifiedCardinality)


def _list_cells(g, head):
    """Walk an rdf:List, returning [(cell, first_value), ...]. Cycle-safe."""
    cells, cell, seen = [], head, set()
    while cell is not None and cell != RDF.nil and cell not in seen:
        seen.add(cell)
        first = next(g.objects(cell, RDF.first), None)
        cells.append((cell, first))
        cell = next(g.objects(cell, RDF.rest), None)
    return cells


def _splice_from_lists(g, bad):
    """Remove `bad` members from every rdf:List, repairing the chain in place.

    Without this, deleting a member's triples leaves a headless cell and the
    whole list (hence the axiom carrying it) becomes malformed.
    """
    removed = 0
    for pred in LIST_PREDICATES:
        for owner, head in list(g.subject_objects(pred)):
            cells = _list_cells(g, head)
            if not any(v in bad for _, v in cells):
                continue
            keep = [v for _, v in cells if v is not None and v not in bad]
            # tear the old chain down
            for cell, _ in cells:
                for t in list(g.triples((cell, None, None))):
                    g.remove(t); removed += 1
            g.remove((owner, pred, head)); removed += 1
            if len(keep) >= 2 or (pred != OWL.members and keep):
                # rebuild a fresh chain with the survivors
                cur_head = RDF.nil
                for v in reversed(keep):
                    cell = rdflib.BNode()
                    g.add((cell, RDF.first, v))
                    g.add((cell, RDF.rest, cur_head))
                    cur_head = cell
                g.add((owner, pred, cur_head))
            # else: fewer than two members left -> the axiom is vacuous; the
            # owner is cleaned up by the orphan sweep below.
    return removed


def prune_graph(g):
    """Reasoner-deletion control (the paper's `prune` configuration): enforce
    consistency by DELETING unsatisfiable classes instead of repairing them.
    No LLM is involved. Mutates and returns `g`, plus a removal summary.

    Deletion is *minimal*: only the unsatisfiable classes and the structures
    that genuinely break because of their removal are dropped. Axioms that do
    not mention an unsatisfiable class survive untouched, so an ontology with
    nothing unsatisfiable is returned unchanged (a strict no-op).

    NOTE on blank nodes: crude triple removal breaks rdf:Lists (owl:members /
    intersectionOf) and restriction fillers, leaving MALFORMED OWL that a
    reasoner may mis-report as globally inconsistent (C=0) -- impossible for a
    purely subtractive edit (monotonicity). We therefore splice deleted members
    out of their lists and garbage-collect the resulting remnants, while
    protecting root-level axiom nodes (STANDALONE_AXIOM_TYPES), which are
    unreferenced by design and must not be mistaken for garbage.
    """
    r = reason(g)
    bad = {rdflib.URIRef(u) for u in r["unsatisfiable"]}
    if not bad:
        # nothing is unsatisfiable -> nothing to enforce; leave the graph alone
        return g, {"removed_classes": 0, "removed_triples": 0, "removed_axioms": 0}

    removed = _splice_from_lists(g, bad)
    for u in bad:
        for t in list(g.triples((u, None, None))) + list(g.triples((None, None, u))):
            g.remove(t); removed += 1

    # drop restrictions that lost their filler
    for b in {s for s in g.subjects(RDF.type, OWL.Restriction)
              if isinstance(s, rdflib.BNode)}:
        if not any((b, f, None) in g for f in RESTRICTION_FILLERS):
            for t in list(g.triples((b, None, None))) + list(g.triples((None, None, b))):
                g.remove(t); removed += 1

    # sweep genuinely orphaned blank nodes (broken list/restriction remnants),
    # but never the root-level axiom nodes
    axioms_dropped, changed = 0, True
    while changed:
        changed = False
        for b in {s for s in g.subjects() if isinstance(s, rdflib.BNode)}:
            types = set(g.objects(b, RDF.type))
            standalone = bool(types & STANDALONE_AXIOM_TYPES)
            if standalone:
                # a disjointness/difference axiom needs at least two members
                head = next((o for p in LIST_PREDICATES
                             for o in g.objects(b, p)), None)
                n = len([v for _, v in _list_cells(g, head) if v is not None]) if head else 0
                if n >= 2:
                    continue
                axioms_dropped += 1
            elif (None, None, b) in g:
                continue                      # still referenced -> keep
            for t in list(g.triples((b, None, None))):
                g.remove(t); removed += 1
            changed = True

    return g, {"removed_classes": len(bad), "removed_triples": removed,
               "removed_axioms": axioms_dropped}


# --------------------------------------------------------------------------- #
# CLI - deterministic tools for sub-agents (no API key needed)
#   python onto_utils.py reason <ontology.ttl>
#   python onto_utils.py eval   <generated.ttl> <gold.ttl>
# Both print a single JSON line to stdout.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "reason":
        try:
            g = parse_ttl(open(sys.argv[2], encoding="utf-8").read())
        except Exception as e:
            print(json.dumps({"parses": False, "error": str(e)})); sys.exit(1)
        errs, r = detect_errors(g)
        print(json.dumps({
            "parses": True, "consistent": r["consistent"], "C": r["C"],
            "n_classes": r["n_classes"],
            "unsatisfiable": [local(u) for u in r["unsatisfiable"]],
            "n_errors": len(errs), "errors": errs[:50],
        }))
    elif cmd == "eval":
        gen = parse_ttl(open(sys.argv[2], encoding="utf-8").read())
        gold = parse_ttl(open(sys.argv[3], encoding="utf-8").read())
        m = evaluate_against_gold(gen, gold)
        r = reason(gen)
        print(json.dumps({
            "consistency_C": r["C"], "consistent": r["consistent"],
            "unsatisfiable": len(r["unsatisfiable"]), "gen_classes": r["n_classes"],
            "f1": m["overall"]["f1"], "precision": m["overall"]["precision"],
            "recall": m["overall"]["recall"],
            "concept_f1": m["concept"]["f1"], "relation_f1": m["relation"]["f1"],
            "metrics": m,
        }))
    elif cmd == "prune":
        g = parse_ttl(open(sys.argv[2], encoding="utf-8").read())
        g, info = prune_graph(g)
        g.serialize(destination=sys.argv[3], format="turtle")
        print(json.dumps(info))
    else:
        print("usage: onto_utils.py reason <ttl> | eval <gen.ttl> <gold.ttl> "
              "| prune <in.ttl> <out.ttl>")
        sys.exit(2)
