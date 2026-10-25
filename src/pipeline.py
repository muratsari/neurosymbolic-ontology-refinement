#!/usr/bin/env python
"""
Neuro-symbolic ontology generation pipeline (the paper's experiment engine).

PAIRED PROTOCOL. Each *run* performs ONE neural extraction and derives all four
configurations from it, as the paper's paired design (n = 30 extractions per
domain and extractor) requires:

  * llm_only    (A)  : the extraction itself -- no reasoning, no correction
  * prune       (Bp) : reasoner-deletion control -- unsatisfiable classes are
                       DELETED rather than repaired (no LLM involved)
  * single_pass (Br) : the refinement loop stopped after one committed correction
  * hybrid  (C)  : the refinement loop run to convergence (the full method)

Br is a snapshot of C's first committed iteration rather than an independently
sampled repair. This keeps the Br/C contrast perfectly paired (it removes
sampling noise from the comparison) and costs one fewer generation call per run.

Refinement loop = Algorithm 1 of the paper. Errors split into hard errors
(global inconsistency, unsatisfiable classes) and soft errors (missing rdfs:domain
/ rdfs:range). Every detected error is sent to the model for correction, but the
loop ends normally once no hard error remains (H_t = {}). A candidate revision is
committed only if it strictly reduces the error count and introduces no new hard
error (H' is a subset of H_t); otherwise the loop stops and returns the last admitted
ontology (validate-before-commit -> monotone, fully autonomous). Correction mode
"rewrite" (paper §3.5, the protocol default): the model receives the detected errors
and the current ontology and returns the corrected ontology in full. The optional
"patch" mode returns a compact edit list instead.

Metrics: consistency score C in [0,1] (HermiT coherence) + Precision/Recall/F1
vs the gold standard (concept-level, relation-level, overall micro).

Usage:
  python src/pipeline.py                                   # all domains, 1 run
  python src/pipeline.py --domains securities --runs 30
  python src/pipeline.py --provider gemini --runs 30 \
         --out results/my_gemini_arm
  PIPELINE_LLM=mock python src/pipeline.py                 # offline, no API key

Outputs (default results/pipeline_reference/):
  <domain folder>/<run>/{llm_only,prune,single_pass,hybrid}.ttl
  <domain folder>/<run>/manifest.json     per-run settings, refine history + token/latency telemetry
  <domain folder>/<run>/calls.jsonl       every model reply of the run, verbatim
  results_<domain>.json, tables_<domain>.md   aggregate of every run directory of the
                                   domain, rebuilt after each invocation
"""
import os, sys, re, json, argparse, time, copy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import onto_utils as ou
import rdflib.collection            # noqa: F401  (for rdflib.collection.Collection)
from llm import get_client, QuotaExhausted, MAX_OUTPUT_TOKENS, CACHE_TTL
import paths as P

# repository layout (folders, canonical file of each domain): src/paths.py
PROJ = P.ROOT
PROMPTS = P.PROMPTS_EXTRACTION
DOMAINS = P.DOMAINS
CORPUS_FILE = P.CORPUS_FILE
CONFIGS = ["llm_only", "prune", "single_pass", "hybrid"]
MAX_REFINE_ITERS = 5   # paper §3.7/§4.4: five-iteration cap
CHUNK_CHARS = 600000   # larger than every corpus -> single-call extraction, no merge step
HARD_ERROR_TYPES = {"inconsistency", "unsatisfiable_class"}   # paper §3.7
PARSE_RETRIES = 2      # extra attempts when a reply is not parseable Turtle
EXTRACTION_REPEATS = 3 # a run whose extraction yields no ontology is repeated this often


class ExtractionFailed(RuntimeError):
    """GenerateOntology (Algorithm 1, line 1) produced no parseable ontology.

    The run has no initial ontology, so it is not a result: it is repeated under the
    same run id instead of being scored as an empty (vacuously coherent) ontology."""
MERGE_BATCH = 4        # partials folded per merge call (see merge_partials)

# The frozen, domain-specific extraction prompts of the experimental protocol. Paper Section 4.4:
# "a frozen, domain-specific prompt that encodes a strict naming contract".
# The contract (CamelCase singular classes, has<Range>/is<X>Of properties, one concept = one
# term) keeps names aligned across chunks and with the reference ontology; without it the
# same concept would get a different IRI in every chunk.
PROMPT_FILE = P.PROMPT_FILE
_PROMPT_CACHE = {}


def load_frozen_prompt(domain):
    """Extracts the '## PROMPT' section of the frozen prompt file.

    The returned text contains the '{corpus_passages}' placeholder where the corpus is
    inserted. If the file does not exist, the generic EXTRACT_SYS is used instead.
    """
    if domain in _PROMPT_CACHE:
        return _PROMPT_CACHE[domain]
    path = os.path.join(PROMPTS, PROMPT_FILE.get(domain, ""))
    if not os.path.exists(path):
        sys.stderr.write(f"  ! frozen prompt for {domain} not found -> generic prompt\n")
        _PROMPT_CACHE[domain] = None
        return None
    text = open(path, encoding="utf-8").read()
    # Only the "## PROMPT" section is the frozen prompt; the rest of the file is protocol
    # notes that must never reach the model. The lookahead used to be "^##\s " (stray
    # trailing space), which never matched and silently fell back to the WHOLE file.
    m = re.search(r"^##\s+PROMPT\b[^\n]*\n(.*?)(?=^##\s)", text, flags=re.S | re.M)
    if not m:
        raise RuntimeError(f"{path}: '## PROMPT' section not found; refusing to send the whole file")
    body = m.group(1).strip().strip("-").strip()
    if "{corpus_passages}" not in body:
        sys.stderr.write(f"  ! {path} has no {{corpus_passages}} placeholder\n")
        _PROMPT_CACHE[domain] = None
        return None
    _PROMPT_CACHE[domain] = body
    return body


EXTRACT_SYS = (
    "You are a senior ontology engineer. From the supplied domain text you build an "
    "OWL 2 DL ontology (TBox only) in Turtle. Extract: named classes (with rdfs:label "
    "and a one-sentence skos:definition), a subClassOf taxonomy, and object/data "
    "properties WITH explicit rdfs:domain and rdfs:range. Critically, also extract the "
    "LOGICAL AXIOMS the text implies: class disjointness (owl:disjointWith / "
    "owl:AllDisjointClasses), cardinality/functionality (owl:qualifiedCardinality, "
    "owl:FunctionalProperty), and existential restrictions (owl:someValuesFrom) - these "
    "are what a reasoner can check. Use the base IRI http://example.org/gen# (prefix ':'). "
    "Output ONLY a single fenced ```turtle code block, nothing else."
)
MERGE_SYS = (
    "You are an ontology engineer. Merge the given partial OWL ontologies (Turtle) into "
    "ONE coherent OWL 2 DL ontology: deduplicate classes/properties by meaning, unify the "
    "taxonomy, keep all logical axioms (disjointness, cardinality, restrictions), and keep "
    "rdfs:label + rdfs:domain/range. Base IRI http://example.org/gen# (prefix ':'). "
    "Output ONLY a single fenced ```turtle code block."
)
MERGE_ALIAS_SYS = (
    "You are an ontology engineer. You are given the list of class and property names that "
    "appear across several partial ontologies extracted from the SAME corpus, so the same "
    "concept often appears under several names. Group the names that denote the same concept "
    "(spelling variants, singular/plural, synonyms, abbreviations, or one name being a "
    "redundant restatement of another). Choose the clearest member of each group as the "
    "canonical name. Output ONLY a JSON object mapping each canonical name to the list of its "
    "other names, for example {\"EquitySecurity\": [\"EquitySecurities\", \"Equity\"]}. "
    "Include a group only if it has at least one alias. Never invent a name that is not in the "
    "input list. Do not merge names that denote genuinely different concepts."
)
CORRECT_PATCH_SYS = (
    "You are repairing an OWL ontology that a description-logic reasoner found faulty. You are "
    "given the reasoner's findings and the ontology in Turtle. Do NOT rewrite the ontology. "
    "Return ONLY a JSON object describing the minimal edits that remove the listed problems "
    "while preserving all correct content:\n"
    '{"drop_subclass": [["Child","Parent"]], "drop_disjoint": [["A","B"]], '
    '"add_domain": [["prop","Class"]], "add_range": [["prop","Class"]]}\n'
    "Use local names exactly as they appear in the ontology (no prefixes, no angle brackets). "
    "Prefer the smallest set of edits that makes every unsatisfiable class satisfiable: when a "
    "class is unsatisfiable because it is a subclass of two disjoint classes, drop the less "
    "appropriate parent rather than the disjointness that the corpus supports. Never delete a "
    "class outright. Include only the keys you actually need."
)
CORRECT_SYS = (
    "You are repairing an OWL ontology that a description-logic reasoner found faulty. "
    "Return a corrected version of the WHOLE ontology in Turtle that removes the listed "
    "problems while preserving all correct content. Prefer removing or weakening the "
    "specific axiom that causes each problem (e.g. drop one of two disjoint parents that "
    "makes a class unsatisfiable; add a missing rdfs:domain/range). Do not introduce new "
    "classes that aren't supported. Output ONLY a single fenced ```turtle code block."
)


# --------------------------------------------------------------------------- #
def load_corpus(domain, max_passages=None):
    path = P.corpus_path(domain)
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    # Units whose source licence does not allow redistribution are listed without their
    # text ("text_withheld": true, see corpora/README.md) and cannot be fed to the extractor.
    held = sum(1 for r in recs if "text" not in r)
    if held:
        sys.stderr.write(f"  ! {domain}: {held} of {len(recs)} corpus units are listed without "
                         f"text and skipped; this run sees less text than the reported runs\n")
    recs = [r for r in recs if "text" in r]
    if max_passages:
        recs = recs[:max_passages]
    return [r["text"] for r in recs]


def chunk(passages, budget=None):
    budget = budget or CHUNK_CHARS
    chunks, cur, n = [], [], 0
    for p in passages:
        if n + len(p) > budget and cur:
            chunks.append(cur); cur, n = [], 0
        cur.append(p); n += len(p)
    if cur:
        chunks.append(cur)
    return chunks


def safe_parse(llm_text):
    try:
        return ou.parse_ttl(ou.extract_turtle(llm_text))
    except Exception as e:
        sys.stderr.write(f"  ! turtle parse failed: {e}\n")
        return None


def complete_ttl(llm, system, prompt, retries=PARSE_RETRIES, cache=False):
    """One LLM call whose reply must parse as Turtle; retried on parse failure.

    Weaker/open-weight models occasionally emit prose around (or instead of) the
    fenced block; a bounded retry keeps a single malformed reply from silently
    dropping a whole chunk. Returns (graph|None, attempts).
    """
    for attempt in range(1, retries + 2):
        try:
            g = safe_parse(llm.complete(system, prompt, cache=cache))
        except QuotaExhausted:
            raise
        if g is not None and len(g):
            return g, attempt
        if attempt <= retries:
            sys.stderr.write(f"  ! retry {attempt}/{retries}\n")
    return None, retries + 1


def copy_graph(g):
    out = ou.rdflib.Graph()
    for pfx, ns in g.namespaces():
        out.bind(pfx, ns)
    for t in g:
        out.add(t)
    return out


def extract(passages, llm, stats, domain=None):
    """Neural extraction -> rdflib graph (chunk -> per-chunk extract -> merge).

    Uses the frozen, domain-specific prompt of the experimental protocol when one
    exists; the generic EXTRACT_SYS is only a fallback for unknown domains.
    """
    frozen = load_frozen_prompt(domain) if domain else None
    if frozen:
        head, _, tail = frozen.partition("{corpus_passages}")
        sys_text, corpus_lead = head.rsplit("CORPUS:", 1) if "CORPUS:" in head else (head, "")
        sys_text = sys_text.strip()
        corpus_lead = ("CORPUS:" + corpus_lead) if corpus_lead is not None else "CORPUS:"
    else:
        sys_text, corpus_lead, tail = EXTRACT_SYS, "TASK: EXTRACT the ontology.\n\nCORPUS:\n", ""
    chunks = chunk(passages)
    partials = []
    for i, ch in enumerate(chunks):
        prompt = corpus_lead + "\n\n---\n\n".join(ch) + (tail or "")
        # the extraction prompt (frozen prompt + corpus) repeats across the runs of
        # a domain, so it is served from the prompt cache after the first run
        g, tries = complete_ttl(llm, sys_text, prompt, cache=True)
        stats["parse_attempts"] += tries
        if g is None:
            stats["parse_failures"] += 1
        else:
            partials.append(g)
        print(f"    extract chunk {i+1}/{len(chunks)}: "
              f"{len(g) if g is not None else 0} triples", flush=True)
    if not partials:
        raise ExtractionFailed(f"no parseable ontology after {stats['parse_attempts']} "
                               f"extraction attempts")
    return merge_partials(partials, llm, stats)


def graph_union(graphs):
    """Deduplication-free fallback: keep every triple rather than lose a branch."""
    out = ou.rdflib.Graph()
    for g in graphs:
        for pfx, ns in g.namespaces():
            out.bind(pfx, ns)
        for t in g:
            out.add(t)
    return out


def _local(u):
    t = str(u)
    return t.rsplit("#", 1)[-1] if "#" in t else t.rsplit("/", 1)[-1]


def _named_terms(g):
    """Named classes and properties, as (URIRef, local name) pairs."""
    types = (ou.OWL.Class, ou.OWL.ObjectProperty, ou.OWL.DatatypeProperty)
    out = {}
    for t in types:
        for s_ in g.subjects(ou.RDF.type, t):
            if isinstance(s_, ou.rdflib.URIRef):
                out[s_] = _local(s_)
    return out


def _extract_json(text):
    """Pull the first JSON object out of a reply that may be fenced or chatty."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    blob = m.group(1) if m else None
    if blob is None:
        i, j = text.find("{"), text.rfind("}")
        blob = text[i:j + 1] if i >= 0 and j > i else None
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def merge_partials(partials, llm, stats, batch=MERGE_BATCH):
    """Union the partials deterministically, then let the model resolve duplicates.

    A free-form merge asks the model to re-emit the entire merged ontology in one
    response. On a 15-chunk corpus that response runs to tens of thousands of
    tokens; models that spend much of their output budget on reasoning truncate or
    cancel it, and when a response does return it tends to concatenate rather than
    deduplicate -- a union carrying every duplicate class, which destroys precision
    and leaves the reasoner nothing to repair.

    We therefore split the operation along the neuro-symbolic seam the paper
    argues for. The union is computed symbolically with rdflib, so no content can
    be lost or invented. The model is asked only for the judgement it is actually
    needed for -- which names denote the same concept -- and returns it as a
    compact alias map (a few hundred tokens regardless of ontology size). The
    rewrite is then applied mechanically. Coreference resolution stays neural;
    graph manipulation stays symbolic.
    """
    if len(partials) == 1:
        return partials[0]
    g = graph_union(partials)
    terms = _named_terms(g)
    if not terms:
        return g
    names = sorted(set(terms.values()))
    prompt = ("TASK: EXTRACT (merge).\n\nNames appearing across the partial ontologies:\n"
              + "\n".join(names))
    t0 = len(g)
    raw = None
    for attempt in range(1, PARSE_RETRIES + 2):
        try:
            raw = _extract_json(llm.complete(MERGE_ALIAS_SYS, prompt))
        except QuotaExhausted:
            raise
        except Exception as e:
            sys.stderr.write(f"  ! merge call failed: {e}\n")
            raw = None
        stats["parse_attempts"] += 1
        if isinstance(raw, dict):
            break
        if attempt <= PARSE_RETRIES:
            sys.stderr.write(f"  ! merge retry {attempt}/{PARSE_RETRIES}\n")
    if not isinstance(raw, dict):
        stats["parse_failures"] += 1
        print(f"    merge: alias map unavailable -> plain union ({t0} triples)", flush=True)
        return g

    # local name -> canonical local name (only names the model was actually given)
    known = set(names)
    canon = {}
    for c, aliases in raw.items():
        if c not in known or not isinstance(aliases, list):
            continue
        for a in aliases:
            if isinstance(a, str) and a in known and a != c:
                canon[a] = c
    if not canon:
        print(f"    merge: no duplicates reported ({t0} triples)", flush=True)
        return g

    remap = {u: ou.rdflib.URIRef(str(u).rsplit(_local(u), 1)[0] + canon[n])
             for u, n in terms.items() if n in canon}
    out = ou.rdflib.Graph()
    for pfx, ns in g.namespaces():
        out.bind(pfx, ns)
    for s_, p_, o_ in g:
        out.add((remap.get(s_, s_), remap.get(p_, p_), remap.get(o_, o_)))
    print(f"    merge: {len(partials)} partials, {len(names)} names, "
          f"{len(canon)} aliases folded -> {len(out)} triples "
          f"(union was {t0})", flush=True)
    return out


def _name_index(g):
    idx = {}
    for s_ in set(g.subjects()) | {o for o in g.objects() if isinstance(o, ou.rdflib.URIRef)}:
        if isinstance(s_, ou.rdflib.URIRef):
            idx.setdefault(_local(s_), s_)
    return idx


def apply_patch(g, patch):
    """Applies the minimal edits proposed by the model mechanically.

    A free-form correction requires the model to rewrite the WHOLE ontology; for an
    ontology of 1000+ triples this exceeds the output budget and truncates the reply. The
    patch language reduces the correction to four edit types that match exactly the error
    types the reasoner reports, so the model's output stays independent of ontology size.
    The acceptance criterion is unchanged: the result still passes the validate-before-commit
    gate.
    """
    out = ou.rdflib.Graph()
    for pfx, ns in g.namespaces():
        out.bind(pfx, ns)
    for t in g:
        out.add(t)
    idx = _name_index(out)
    n = 0

    def U(name):
        return idx.get(name if isinstance(name, str) else str(name))

    for pair in patch.get("drop_subclass") or []:
        if not (isinstance(pair, list) and len(pair) == 2):
            continue
        c, p_ = U(pair[0]), U(pair[1])
        if c is not None and p_ is not None and (c, ou.RDFS.subClassOf, p_) in out:
            out.remove((c, ou.RDFS.subClassOf, p_)); n += 1

    for pair in patch.get("drop_disjoint") or []:
        if not (isinstance(pair, list) and len(pair) == 2):
            continue
        a, b = U(pair[0]), U(pair[1])
        if a is None or b is None:
            continue
        for x, y in ((a, b), (b, a)):
            if (x, ou.OWL.disjointWith, y) in out:
                out.remove((x, ou.OWL.disjointWith, y)); n += 1
        # remove b from the member list of AllDisjointClasses (repairing the RDF list)
        for axiom in list(out.subjects(ou.RDF.type, ou.OWL.AllDisjointClasses)):
            head = next(out.objects(axiom, ou.OWL.members), None)
            if head is None:
                continue
            cells = ou.rdflib.collection.Collection(out, head)
            members = list(cells)
            if a in members and b in members:
                keep = [m for m in members if m != b]
                cells.clear()
                if len(keep) >= 2:
                    for m in keep:
                        cells.append(m)
                else:
                    out.remove((axiom, ou.OWL.members, head))
                    for t in list(out.triples((axiom, None, None))):
                        out.remove(t)
                n += 1

    for key, pred in (("add_domain", ou.RDFS.domain), ("add_range", ou.RDFS.range)):
        for pair in patch.get(key) or []:
            if not (isinstance(pair, list) and len(pair) == 2):
                continue
            p_, c = U(pair[0]), U(pair[1])
            if p_ is not None and c is not None and (p_, pred, c) not in out:
                out.add((p_, pred, c)); n += 1
    return out, n


def correct_by_patch(cur, errs, llm, stats):
    """One correction round: the model returns the minimal edits as JSON."""
    err_lines = "\n".join(f"- [{e['type']}] {e['detail']}" for e in errs)
    prompt = ("TASK: CORRECT the ontology.\n\nThe reasoner found these problems:\n"
              + err_lines + "\n\nCurrent ontology:\n```turtle\n"
              + cur.serialize(format="turtle") + "\n```")
    for attempt in range(1, PARSE_RETRIES + 2):
        try:
            patch = _extract_json(llm.complete(CORRECT_PATCH_SYS, prompt))
        except QuotaExhausted:
            raise
        except Exception as e:
            sys.stderr.write(f"  ! correction call failed: {e}\n")
            patch = None
        stats["parse_attempts"] += 1
        if isinstance(patch, dict):
            cand, n = apply_patch(cur, patch)
            if n:
                return cand, n
            sys.stderr.write("  ! patch applied no edits\n")
        if attempt <= PARSE_RETRIES:
            sys.stderr.write(f"  ! correction retry {attempt}/{PARSE_RETRIES}\n")
    stats["parse_failures"] += 1
    return None, 0


def hard_errors(errs):
    """H_t = HardErrors(E_t) (Algorithm 1, line 5), as a set of (type, focus) pairs."""
    return {(e["type"], e.get("focus")) for e in errs if e["type"] in HARD_ERROR_TYPES}


def admit(errs, cand_errs):
    """Validation gate (Algorithm 1, line 12): |E'| < |E_t| and H' is a subset of H_t.

    Global inconsistency is itself a hard error, so a candidate that turns a
    consistent ontology inconsistent is rejected even though HermiT then reports
    it as a single error.
    """
    return len(cand_errs) < len(errs) and hard_errors(cand_errs) <= hard_errors(errs)


def refine(graph, llm, stats, max_iters=MAX_REFINE_ITERS, mode="rewrite"):
    """Algorithm 1: reasoner-gated LLM correction.

    Returns (final_graph, history, after_first_iteration, stop_reason). The third
    value is the single-pass repair baseline: the graph once the first correction
    has been committed (or the untouched input, if none was). stop_reason is one
    of "no_hard_errors", "gate_rejected", "no_usable_correction", "iteration_cap".
    """
    cur = graph
    errs, r = ou.detect_errors(cur)
    history = [{"iter": 0, "n_errors": len(errs), "n_hard": len(hard_errors(errs)),
                "C": r["C"], "unsat": len(r["unsatisfiable"])}]
    first = None
    it = 0
    stop = "iteration_cap"
    while it < max_iters:
        if not hard_errors(errs):
            stop = "no_hard_errors"
            break
        it += 1
        if mode == "patch":
            cand, n_edits = correct_by_patch(cur, errs, llm, stats)
        else:
            err_lines = "\n".join(f"- [{e['type']}] {e['detail']}" for e in errs)
            prompt = ("TASK: CORRECT the ontology.\n\nThe reasoner found these problems:\n"
                      + err_lines + "\n\nCurrent ontology:\n```turtle\n"
                      + cur.serialize(format="turtle") + "\n```")
            cand, tries = complete_ttl(llm, CORRECT_SYS, prompt)
            stats["parse_attempts"] += tries
            if cand is None:
                stats["parse_failures"] += 1
        if cand is None:
            print(f"    refine iter {it}: no usable correction -> stop", flush=True)
            stop = "no_usable_correction"
            break
        cerrs, cr = ou.detect_errors(cand)
        if admit(errs, cerrs):
            cur, errs, r = cand, cerrs, cr
            print(f"    refine iter {it}: COMMIT  errors={len(errs)}  "
                  f"hard={len(hard_errors(errs))}  C={r['C']}", flush=True)
        else:
            new_hard = len(hard_errors(cerrs) - hard_errors(errs))
            print(f"    refine iter {it}: reject (errors {len(cerrs)} vs {len(errs)}, "
                  f"new_hard={new_hard}) -> stop", flush=True)
            stop = "gate_rejected"
            break
        history.append({"iter": it, "n_errors": len(errs), "n_hard": len(hard_errors(errs)),
                        "C": r["C"], "unsat": len(r["unsatisfiable"])})
        if it == 1:
            first = copy_graph(cur)
    else:
        if not hard_errors(errs):
            stop = "no_hard_errors"
    if first is None:
        first = copy_graph(graph)      # no committed correction -> no repair
    return cur, history, first, stop


# --------------------------------------------------------------------------- #
def run_paired(domain, run_id, llm, max_passages=None, outdir="results", configs=None,
               correct_mode="rewrite"):
    """One extraction -> all four configurations (the paper's paired protocol)."""
    configs = configs or CONFIGS
    print(f"\n=== {domain} / {run_id} ===", flush=True)
    gold = ou.parse_ttl(open(P.gold_path(domain), encoding="utf-8").read())
    passages = load_corpus(domain, max_passages)
    print(f"  corpus passages: {len(passages)}", flush=True)

    t0 = time.time()
    before = llm.stats.asdict()
    llm.call_log = []                 # every reply of this run, archived below
    stats = {"parse_attempts": 0, "parse_failures": 0}

    base = extract(passages, llm, stats, domain)
    # The documented normalisation of the protocol (paper Section 4.3): a single xsd:date
    # literal makes HermiT report global inconsistency without any real contradiction. In the
    # primary arm it was applied before scoring; here it is applied in the pipeline, so the
    # stored ontology is the scored ontology.
    base = ou.normalize_datatypes(base)
    graphs = {"llm_only": base}

    if "prune" in configs:
        pruned, pinfo = ou.prune_graph(copy_graph(base))
        graphs["prune"] = pruned
    else:
        pinfo = None

    history, stop = None, None
    if "hybrid" in configs or "single_pass" in configs:
        hybrid, history, single, stop = refine(base, llm, stats, mode=correct_mode)
        graphs["hybrid"] = hybrid
        graphs["single_pass"] = single

    run_dir = os.path.join(P.domain_dir(outdir, domain), run_id)
    os.makedirs(run_dir, exist_ok=True)
    recs = []
    for cfg in configs:
        g = graphs.get(cfg)
        if g is None:
            continue
        g.serialize(destination=os.path.join(run_dir, f"{cfg}.ttl"), format="turtle")
        errs, r = ou.detect_errors(g)
        m = ou.evaluate_against_gold(g, gold)
        rec = {
            "domain": domain, "run": run_id, "config": cfg, "llm": llm.name,
            "consistency_C": r["C"], "consistent": r["consistent"],
            "unsatisfiable": len(r["unsatisfiable"]), "n_errors": len(errs),
            "gen_classes": r["n_classes"],
            "f1": m["overall"]["f1"], "precision": m["overall"]["precision"],
            "recall": m["overall"]["recall"],
            "concept_f1": m["concept"]["f1"], "relation_f1": m["relation"]["f1"],
            "metrics": m,
        }
        recs.append(rec)
        print(f"  {cfg:<12} C={rec['consistency_C']} F1={rec['f1']} "
              f"unsat={rec['unsatisfiable']} ({rec['gen_classes']} classes)", flush=True)

    after = llm.stats.asdict()
    telemetry = {
        "llm": llm.name,
        "wall_seconds": round(time.time() - t0, 1),
        "calls": after["calls"] - before["calls"],
        "in_tokens": after["in_tokens"] - before["in_tokens"],
        "cache_read_tokens": after["cache_read_tokens"] - before["cache_read_tokens"],
        "cache_write_tokens": after["cache_write_tokens"] - before["cache_write_tokens"],
        "out_tokens": after["out_tokens"] - before["out_tokens"],
        "thinking_tokens": after["thinking_tokens"] - before["thinking_tokens"],
        "api_seconds": round(after["seconds"] - before["seconds"], 1),
        "parse_attempts": stats["parse_attempts"],
        "parse_failures": stats["parse_failures"],
        "truncated_replies": after["truncated"] - before["truncated"],
        "served_model_ids": after["model_ids"],
        "refine_iterations": (len(history) - 1) if history else 0,
        "refine_stop": stop,
    }
    settings = {"max_output_tokens": MAX_OUTPUT_TOKENS, "reasoning": llm.reasoning,
                "prompt_cache": f"extraction call (ttl {CACHE_TTL} where configurable)",
                "correct_mode": correct_mode, "chunk_chars": CHUNK_CHARS,
                "max_refine_iters": MAX_REFINE_ITERS,
                "hard_error_types": sorted(HARD_ERROR_TYPES)}
    manifest = {"domain": domain, "run": run_id, "settings": settings,
                "telemetry": telemetry,
                "refine_history": history, "prune_info": pinfo,
                "scores": [{k: v for k, v in r.items() if k != "metrics"} for r in recs]}
    json.dump(manifest, open(os.path.join(run_dir, "manifest.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=2)
    # raw replies, one JSON line per call (prompts as hashes: they contain the corpus)
    with open(os.path.join(run_dir, "calls.jsonl"), "w", encoding="utf-8") as fh:
        for i, rec in enumerate(llm.call_log or [], 1):
            fh.write(json.dumps({"call": i, **rec}, ensure_ascii=False) + "\n")
    llm.call_log = None
    print(f"  telemetry: {telemetry}", flush=True)
    return recs


# --------------------------------------------------------------------------- #
def collect_records(outdir, domain):
    """Every config-row of every run directory of a domain, rebuilt from the run files.

    The aggregate is never assembled from the runs of one invocation only: a set
    completed later with --run-offset would otherwise overwrite it with a partial one.
    Scores come from each manifest; the detailed metrics are recomputed from the
    stored ontology (deterministic, no reasoner call).
    """
    root = P.domain_dir(outdir, domain)
    runs = sorted(r for r in os.listdir(root) if re.fullmatch(r"run\d+", r)
                  and os.path.exists(os.path.join(root, r, "manifest.json")))
    if not runs:
        return []
    gold = ou.parse_ttl(open(P.gold_path(domain), encoding="utf-8").read())
    recs = []
    for run in runs:
        man = json.load(open(os.path.join(root, run, "manifest.json"), encoding="utf-8"))
        for sc in man["scores"]:
            g = ou.parse_ttl(open(os.path.join(root, run, f"{sc['config']}.ttl"),
                                  encoding="utf-8").read())
            recs.append({**sc, "metrics": ou.evaluate_against_gold(g, gold)})
    return recs


def write_tables(records, outdir, filename="tables.md"):
    domains = sorted({r["domain"] for r in records})
    configs = [c for c in CONFIGS if any(r["config"] == c for r in records)]
    names = {"llm_only": "LLM-only", "prune": "Reasoner-prune (control)",
             "single_pass": "LLM + single-pass repair", "hybrid": "Proposed (Hybrid)"}

    def avg(rows, key):
        vals = [r[key] for r in rows]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    L = ["# Pipeline results", "", f"LLM: {records[0]['llm']}",
         f"Runs per domain: {len({(r['domain'], r['run']) for r in records}) // max(len(domains),1)}", ""]
    L += ["## Ladder (averaged over runs, per domain)", "",
          "| Domain | Config | Consistency C | coherent runs | F1 | Precision | Recall |",
          "|---|---|---|---|---|---|---|"]
    for d in domains:
        for c in configs:
            rows = [r for r in records if r["domain"] == d and r["config"] == c]
            if not rows:
                continue
            coh = sum(1 for r in rows if r["consistent"] and r["unsatisfiable"] == 0)
            L.append(f"| {d} | {names.get(c,c)} | {avg(rows,'consistency_C')} "
                     f"| {coh}/{len(rows)} | {avg(rows,'f1')} "
                     f"| {avg(rows,'precision')} | {avg(rows,'recall')} |")
    open(os.path.join(outdir, filename), "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    global CHUNK_CHARS
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", default=",".join(DOMAINS))
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--runs", type=int, default=1, help="paired runs per domain")
    ap.add_argument("--run-offset", type=int, default=0,
                    help="start numbering at run<offset+1> (to extend an existing set)")
    ap.add_argument("--provider", default=None,
                    help="anthropic | gemini | openai | deepseek | openrouter | mock")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-passages", type=int, default=None)
    ap.add_argument("--correct-mode", choices=["rewrite", "patch"], default="rewrite",
                    help="rewrite (protocol, paper §3.5): the model returns the whole "
                         "corrected ontology; patch: a compact edit list")
    ap.add_argument("--chunk-chars", type=int, default=CHUNK_CHARS,
                    help="chunk budget in characters; the default exceeds every corpus, "
                         "so extraction is a single call")
    ap.add_argument("--out", default=os.path.join(PROJ, "results", "pipeline_reference"))
    a = ap.parse_args()
    domains = [d.strip() for d in a.domains.split(",") if d.strip()]
    configs = [c.strip() for c in a.configs.split(",") if c.strip()]
    CHUNK_CHARS = a.chunk_chars
    out = a.out if os.path.isabs(a.out) else os.path.join(PROJ, a.out)
    os.makedirs(out, exist_ok=True)
    llm = get_client(provider=a.provider, model=a.model)
    print(f"LLM client: {llm.name}", flush=True)

    for d in domains:
        for i in range(a.run_offset + 1, a.run_offset + a.runs + 1):
            run_id = f"run{i:02d}"
            try:
                for attempt in range(EXTRACTION_REPEATS + 1):
                    try:
                        run_paired(d, run_id, llm, a.max_passages, out, configs,
                                   a.correct_mode)
                        break
                    except ExtractionFailed as e:
                        sys.stderr.write(f"  ! {d}/{run_id}: {e}; "
                                         + (f"repeating the run ({attempt + 1}/"
                                            f"{EXTRACTION_REPEATS})\n"
                                            if attempt < EXTRACTION_REPEATS else "giving up\n"))
                else:
                    sys.stderr.write(f"  ! {d}/{run_id} failed: no initial ontology\n")
            except QuotaExhausted as e:
                sys.stderr.write(f"\n!! QUOTA EXHAUSTED: {e}\n"
                                 f"!! {d}/{run_id} and later runs skipped; continue with "
                                 f"--run-offset once the quota is renewed.\n")
                break
            except Exception as e:
                sys.stderr.write(f"  ! {d}/{run_id} failed: {e}\n")
    print(f"\nTotal LLM usage: {llm.stats.asdict()}", flush=True)
    # one aggregate per domain, rebuilt from all of the domain's run directories, so
    # parallel per-domain processes and later --run-offset completions never leave a
    # partial aggregate behind
    for d in domains:
        if not os.path.isdir(P.domain_dir(out, d)):
            continue
        recs = collect_records(out, d)
        res_path = os.path.join(out, f"results_{d}.json")
        json.dump(recs, open(res_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        if recs:
            write_tables(recs, out, f"tables_{d}.md")
        print(f"Wrote {res_path} and tables_{d}.md ({len(recs)} config-rows, "
              f"{len(recs) // max(1, len(configs))} runs)", flush=True)


if __name__ == "__main__":
    main()
