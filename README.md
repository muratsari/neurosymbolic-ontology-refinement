# A Neuro-Symbolic Framework for Automatic Ontology Generation with Iterative Consistency Refinement

Replication package for the paper of the same name: corpora, frozen prompts, reference
ontologies, competency-question suites, source code, the stored output of every run, and the
scripts that turn those outputs into the tables and figures of the paper.

An LLM extracts an OWL ontology from a text corpus; a description-logic reasoner (HermiT) checks
it; the detected errors are returned to the LLM as a correction prompt; a validation gate commits
a revision only if it strictly reduces the error count and introduces no new hard error (global
inconsistency or unsatisfiable class). The study covers three domains with n = 30 paired
runs each, for two extraction models that differ only in the model.

---

## 1. Repository layout

```
corpora/
  finance/ healthcare/ education/   corpus (JSON Lines); scraper seeds where the corpus was scraped
  scrape.py                         retrieval and preprocessing script
  README.md                         sources and licences, withheld units, how to obtain them
prompts/
  extraction/                       frozen extraction prompt of each domain
  correction/                       correction prompts: free-form rewrite (used), compact edit list (option)
reference_ontologies/               hand-authored reference ontology of each domain, authoring
                                    briefs, naming contract; README.md with measured facts of each file
competency_questions/               frozen competency-question suites (one JSON file per domain)
src/                                pipeline.py (extraction, refinement loop, gate), llm.py, onto_utils.py, paths.py
evaluation/                         score_domain.py (batch scorer), cq_apply.py, cq_eval.py
results/
  primary_extractor/                claude-sonnet-5: 3 domains x 30 runs x 4 configurations
  second_extractor/                 gemini-3.8-flash: 3 domains x 30 runs x 4 configurations
statistics/                         statistics, tables and figure scripts (deterministic) and what they
                                    write: JSON, CSV tables, Fig. 3-5
requirements.txt
README.md
```

## 2. Domain names

Folders carry the names used in the paper. File names, ontology IRIs, competency-question suites
and JSON outputs carry the topic of the corpus, which is also the key the scripts expect on the
command line.

| Paper | Folder | Key in file names, IRIs, JSON and CLI |
|---|---|---|
| Finance | `finance/` | `securities` |
| Healthcare | `healthcare/` | `hypertension` |
| Education | `education/` | `assessment` |

The mapping lives in one place, `src/paths.py`.

## 3. The two extractors

Both arms were produced by `src/pipeline.py` with the same corpora, frozen extraction prompts,
correction prompt, refinement algorithm, generation settings, reference ontologies and
competency-question suites, and are analysed with the same tests. They differ only in the model.

| | Primary extractor | Second extractor |
|---|---|---|
| Folder | `results/primary_extractor/` | `results/second_extractor/` |
| Model | `claude-sonnet-5` (Anthropic Messages API) | `gemini-3.8-flash` (Gemini API) |
| Reasoning | adaptive thinking, effort `high` | `thinking_level` `medium` |
| In the paper | Sections 5.1–5.6; Tables 1–3; Table 4 | Section 5.7; Table 4 |
| Runs | 3 domains × 30 paired runs | 3 domains × 30 paired runs |

Shared settings: at most 64,000 output tokens per call (reasoning included; a reply cut off at
the limit is discarded), no sampling parameters, the whole corpus in one extraction call,
`xsd:date` → `xsd:dateTime` normalisation before reasoning (paper Section 4.3), free-form
rewrite correction (`prompts/correction/rewrite.md`), iteration cap 5. A reply that does not parse
as Turtle is retried twice.

Each run folder holds the four configurations derived from **one** extraction, which is what
makes the runs paired:

| Paper name | File | Ladder key | What it is |
|---|---|---|---|
| LLM-only | `llm_only.ttl` | A | the extraction itself, no reasoning, no correction |
| Reasoner-prune (control) | `prune.ttl` | Bp | unsatisfiable classes deleted by the reasoner, no LLM repair |
| LLM + single-pass repair | `single_pass.ttl` | Br | the refinement loop stopped after its first admitted correction |
| Proposed (Hybrid) | `hybrid.ttl` | C | the full refinement loop (Algorithm 1) |

**Refinement loop (Algorithm 1).** Hard errors are global inconsistency and unsatisfiable
classes; soft errors are object properties without `rdfs:domain` or `rdfs:range`. The loop ends
when no hard error remains. Otherwise every detected error is sent with the current ontology to
the model, which returns the corrected ontology in full; the candidate is admitted only if the
total error count strictly decreases and no new hard error appears, and a rejected candidate ends
the loop with the last admitted ontology.

Every run folder also holds `manifest.json` (settings, calls, tokens, model time, the model
version the provider reported, refinement history, stop reason) and `calls.jsonl` (every model
reply, verbatim). Scores are stored in `<domain folder>/scoring/`: `f1_<run>_<config>.json`
(coherence, unsatisfiable classes, precision, recall, F1) and `cq_<run>_<config>.json`
(competency questions passed). Both arms are also flattened into one sheet each,
`results/<arm>/per_run_scores.csv`. Details: `results/README.md`.

## 4. Which file produces which result

Everything in this table is deterministic and runs on the stored files, without an API key.

| Paper item | Script | Reads | Writes |
|---|---|---|---|
| **Table 1** (finance, quantitative comparison) | `statistics/make_tables.py` | `results/primary_extractor/finance/scoring/` | `statistics/table1_finance_performance.csv` |
| **Table 2** (ablation, incl. prune control) | `statistics/make_tables.py` | `results/primary_extractor/finance/scoring/` | `statistics/table2_ablation.csv` |
| **Table 3** (cross-domain) | `statistics/make_tables.py` | `results/primary_extractor/*/scoring/` | `statistics/table3_cross_domain.csv` |
| **Table 4** (cross-model) | `statistics/make_tables.py` | `results/*/*/scoring/` | `statistics/table4_cross_model.csv` |
| All four tables, laid out as in the paper | `statistics/make_tables.py` | as above | `statistics/tables.md` |
| Every paired test behind the tables (p, 95% CI, d<sub>z</sub>) | `statistics/make_tables.py` | as above | `statistics/paired_tests.csv` |
| p-values, confidence intervals and effect sizes of Sections 5.1–5.7 and 6 | `statistics/cross_model_stats.py` | `results/<arm>/*/scoring/` | `statistics/cross_model_stats_<arm>.json` |
| Measured cost and iteration profile | `statistics/cost_telemetry.py` | `results/<arm>/*/run*/manifest.json` | `statistics/cost_telemetry_<arm>.json` |
| Section 4.1, supplementary fuzzy F1 | `statistics/fuzzy_f1.py` | `results/<arm>/*/run*/*.ttl` | `statistics/fuzzy_f1_<arm>.json` |
| Section 5.5, initial ontologies | `statistics/robustness.py` | `results/<arm>/*/scoring/` | `statistics/robustness_<arm>.json` |
| Fig. 3–5 and the error and iteration counts of Section 5.3 | `statistics/figure_data.py` | `results/primary_extractor/` | `statistics/figure_data.json` |
| Fig. 3–5 (drawing) | `statistics/make_all_figs.py`, `statistics/svg2png.py` | `statistics/figure_data.json` | `statistics/fig3_*`, `fig4_*`, `fig5_*` (SVG, PDF, PNG) |
| Score files themselves | `evaluation/score_domain.py` | `results/<arm>/<domain folder>/<run>/*.ttl` | `results/<arm>/<domain folder>/scoring/` |

`<arm>` is `primary_extractor` or `second_extractor`. Table 5 of the paper is qualitative and
has no data behind it.

## 5. Setup

```bash
python -m venv .venv && . .venv/bin/activate      # Python 3.12 or newer
pip install -r requirements.txt
java -version                                     # HermiT (bundled with owlready2) needs Java 8+
```

Java is needed for scoring and for `figure_data.py`, not for the tables and statistics.

## 6. Reproducing the results

All commands are run from the repository root.

### 6.1 Tables and statistics from the stored scores

```bash
for arm in primary_extractor second_extractor; do
  python statistics/cross_model_stats.py results/$arm
  python statistics/cost_telemetry.py results/$arm
  python statistics/robustness.py --root results/$arm
  python statistics/fuzzy_f1.py results/$arm
done
python statistics/make_tables.py          # Tables 1-4 + per-run sheets
```

Sign-flip tests are exact up to 20 non-zero paired differences and use a deterministic Monte
Carlo (200,000 draws, fixed-seed linear congruential generator) beyond; the bootstrap uses a
fixed-seed generator as well, so every number is reproduced exactly.

### 6.2 Scoring the stored ontologies again (HermiT)

```bash
for arm in primary_extractor second_extractor; do
  for d in securities hypertension assessment; do
    python evaluation/score_domain.py $d --root results/$arm
  done
done
```

This overwrites the files in `scoring/`. Add `--scoring-dir scoring_check` to write next to
them instead. Scoring one ontology by hand:

```bash
python src/onto_utils.py eval results/primary_extractor/finance/run01/hybrid.ttl \
    reference_ontologies/securities.ttl
python evaluation/cq_apply.py competency_questions/securities.cq.json \
    reference_ontologies/securities.ttl \
    results/primary_extractor/finance/run01/hybrid.ttl
```

### 6.3 Generating new runs (API access)

```bash
# the two arms as reported (ANTHROPIC_API_KEY / GEMINI_API_KEY)
python src/pipeline.py --provider anthropic --model claude-sonnet-5 --runs 30 --out results/my_claude_arm
python src/pipeline.py --provider gemini --model gemini-3.8-flash --runs 30 --out results/my_gemini_arm
# offline plumbing test, no key and no network
PIPELINE_LLM=mock python src/pipeline.py --domains securities --max-passages 30
```

New runs are written in the same layout as the stored arms (default `results/pipeline_reference/`),
so `evaluation/score_domain.py --root <out>` and `statistics/cross_model_stats.py <out>` work on
them unchanged; `--run-offset N` completes a set from run N+1. Generation is not deterministic:
new ontologies differ from the stored ones, and the comparison is reproduced at the aggregate
level. Providers and their environment variables are listed at the top of `src/llm.py`.

### 6.4 Figures

```bash
python statistics/figure_data.py                    # inputs of Fig. 3-5
python statistics/make_all_figs.py                  # SVG and PDF
python statistics/svg2png.py                        # PNG
```

## 7. Corpora and licences

The corpora are third-party text. Every unit carries its own `source`, `url` and `license`
field and keeps that licence. Units whose source licence does not allow redistribution are
listed without their text (`"text_withheld": true`) together with the source, the URL, the word
count and the SHA-256 of the text that was used:

| Domain | Units | Words | Units without text | Words withheld | Share of words withheld |
|---|---:|---:|---:|---:|---:|
| Finance | 234 | 78,349 | 33 | 4,908 | 6.3% |
| Healthcare | 135 | 19,747 | 67 | 8,522 | 43.2% |
| Education | 173 | 51,998 | 0 | 0 | 0.0% |

Scoring and statistics do not read the corpora, so every result listed in Section 4 of this
README is reproducible from this package as it is. New extraction runs on healthcare and finance
see less text than the reported runs did unless the withheld units are restored.
`corpora/README.md` lists the sources and licences, and how the withheld text can be obtained.
The corpus files are the frozen experimental input and are provided exactly as used in the runs.

## 8. Notes

**Cost** per paired run, all four configurations together (`statistics/cost_telemetry_<arm>.json`):

| Extractor | Calls | Input tokens | Output tokens | Thinking tokens | Model time (s) |
|---|---:|---:|---:|---:|---:|
| Primary (`claude-sonnet-5`) | 2.1 | 168,965 | 80,949 | in output | 669 |
| Second (`gemini-3.8-flash`) | 1.3 | 71,744 | 14,562 | 16,082 | 167 |

The Anthropic API counts Claude's thinking inside the output tokens.

- **Determinism.** Generation is not deterministic (no sampling parameters are passed;
  Claude Sonnet 5 accepts only the API defaults for temperature, top-p and top-k), so
  regenerated ontologies differ. Scoring and statistics are deterministic on stored ontologies.
