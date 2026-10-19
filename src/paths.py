"""Repository layout in one place.

Folders are named after the paper's domains (finance, healthcare, education). File names,
ontology IRIs, competency-question suites and JSON outputs use the corpus-topic keys
(securities, hypertension, assessment). FOLDER maps one onto the other; every script in
src/, evaluation/ and statistics/ resolves its inputs and outputs through this module.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOMAINS = ["securities", "hypertension", "assessment"]
FOLDER = {"securities": "finance", "hypertension": "healthcare", "assessment": "education"}
PAPER_NAME = {"securities": "Finance", "hypertension": "Healthcare", "assessment": "Education"}

# inputs
CORPORA = os.path.join(ROOT, "corpora")
CORPUS_FILE = {"securities": "corpus.jsonl", "hypertension": "corpus.jsonl",
               "assessment": "corpus.jsonl"}
PROMPTS_EXTRACTION = os.path.join(ROOT, "prompts", "extraction")
PROMPT_FILE = {"securities": "finance.md", "hypertension": "healthcare.md",
               "assessment": "education.md"}
REFERENCE = os.path.join(ROOT, "reference_ontologies")
CQ_DIR = os.path.join(ROOT, "competency_questions")
CQ_FILE = {"securities": "securities.cq.json", "hypertension": "hypertension.cq.json",
           "assessment": "assessment.cq.json"}

# outputs
RESULTS = os.path.join(ROOT, "results")
PRIMARY = os.path.join(RESULTS, "primary_extractor")     # claude-sonnet-5 (paper Sections 5.1-5.6)
SECOND = os.path.join(RESULTS, "second_extractor")       # gemini-3.8-flash (paper Section 5.7)
ARMS = {"primary_extractor": PRIMARY, "second_extractor": SECOND}
STATS_OUT = os.path.join(ROOT, "statistics")              # the statistics scripts write next to themselves

# tools called as subprocesses (one reasoner JVM per call)
PYTHON = sys.executable
ONTO_UTILS = os.path.join(ROOT, "src", "onto_utils.py")
CQ_APPLY = os.path.join(ROOT, "evaluation", "cq_apply.py")


def corpus_path(domain):
    return os.path.join(CORPORA, FOLDER[domain], CORPUS_FILE[domain])


def gold_path(domain):
    return os.path.join(REFERENCE, f"{domain}.ttl")


def cq_path(domain):
    return os.path.join(CQ_DIR, CQ_FILE[domain])


def resolve_root(root):
    """A result tree given on the command line: absolute, or relative to the repository root."""
    return root if os.path.isabs(root) else os.path.join(ROOT, root)


def domain_dir(root, domain):
    """<result tree>/<domain folder>; unknown domains keep their own name."""
    return os.path.join(root, FOLDER.get(domain, domain))


def scoring_dir(root, domain):
    return os.path.join(domain_dir(root, domain), "scoring")


def stats_dest(root, name):
    """Statistics of a stored arm go to statistics/<stem>_<arm>.json; statistics of any other
    result tree are written next to that tree."""
    for arm, path in ARMS.items():
        if os.path.normpath(root) == os.path.normpath(path):
            os.makedirs(STATS_OUT, exist_ok=True)
            stem, ext = os.path.splitext(name)
            return os.path.join(STATS_OUT, f"{stem}_{arm}{ext}")
    return os.path.join(root, name)
