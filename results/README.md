# Results

Stored output of every run. Nothing here is aggregated except `per_run_scores.csv`.

```
<arm>/
  per_run_scores.csv                  all score files of the arm as one sheet (statistics/make_tables.py)
  <domain folder>/
    run01 ... run30/
      llm_only.ttl                    A   the extraction
      prune.ttl                       Bp  reasoner-prune control
      single_pass.ttl                 Br  refinement loop stopped after its first admitted correction
      hybrid.ttl                      C   the full refinement loop (Algorithm 1)
      manifest.json                   settings, telemetry, refinement history, stop reason, scores
      calls.jsonl                     every model reply of the run, verbatim
    scoring/
      f1_<run>_<config>.json          coherence, unsatisfiable classes, precision, recall, F1
      cq_<run>_<config>.json          competency questions passed
```

`<arm>` is `primary_extractor` (`claude-sonnet-5`) or `second_extractor` (`gemini-3.8-flash`);
`<domain folder>` is `finance`, `healthcare` or `education`. Both arms were produced by
`src/pipeline.py` with the same settings; they differ only in the model.

## Run files

All four ontologies of a run come from one extraction, which is what makes the runs paired.
The stored ontologies are already datatype-normalised (`xsd:date` -> `xsd:dateTime`, paper
Section 4.3), so they are scored as they are.

`manifest.json`: `settings` (output limit, reasoning level, correction mode, iteration cap,
hard-error types), `telemetry` (calls, input / output / thinking tokens with cache reads and
writes, model time, parse attempts, truncated replies, the model version the provider reported,
refinement iterations, stop reason), `refine_history` (errors, hard errors and coherence score
per committed step), `prune_info` and the scores computed at generation time. The Anthropic API
counts Claude's thinking inside the output tokens, so its thinking count is 0.

`calls.jsonl`: one line per model call: model version, finish reason, seconds, token usage and
the reply text. Prompts are stored as SHA-256 prefixes and sizes, since they contain the corpus.

## Score files

`f1_*.json`: `consistent` (global consistency), `unsatisfiable` (number of unsatisfiable named
classes), `consistency_C` (share of satisfiable named classes; 0 if inconsistent), `gen_classes`,
`precision`, `recall`, `f1`, and the same split into concept and relation level under `metrics`.
A run counts as coherent when `consistent` is true and `unsatisfiable` is 0.

`cq_*.json`: `passed`, `total`, `failed`, the split by question category, and `results`, one entry per
question with the reasoner's verdict. A subsumption question counts as passed only if the subclass
relation is entailed and the subclass is satisfiable; an entailment that holds only because the subclass
is unsatisfiable is recorded as `entailed-vacuously` and scored as a failure (`evaluation/cq_eval.py`).
