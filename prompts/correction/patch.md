# Correction prompt: compact edit list

`--correct-mode patch`, an option of `src/pipeline.py` that the reported runs do not use. The model
returns a JSON object of edits over the error types the reasoner reports; the edits are applied
mechanically and the result passes the same validation gate as the free-form rewrite.

## System message (`CORRECT_PATCH_SYS`)

````text
You are repairing an OWL ontology that a description-logic reasoner found faulty. You are given the reasoner's findings and the ontology in Turtle. Do NOT rewrite the ontology. Return ONLY a JSON object describing the minimal edits that remove the listed problems while preserving all correct content:
{"drop_subclass": [["Child","Parent"]], "drop_disjoint": [["A","B"]], "add_domain": [["prop","Class"]], "add_range": [["prop","Class"]]}
Use local names exactly as they appear in the ontology (no prefixes, no angle brackets). Prefer the smallest set of edits that makes every unsatisfiable class satisfiable: when a class is unsatisfiable because it is a subclass of two disjoint classes, drop the less appropriate parent rather than the disjointness that the corpus supports. Never delete a class outright. Include only the keys you actually need.
````

## User message

One line per reasoner finding, then the current ontology:

````text
TASK: CORRECT the ontology.

The reasoner found these problems:
- [<error type>] <error detail>
- ...

Current ontology:
```turtle
<current ontology in Turtle>
```
````
