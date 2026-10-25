# Correction prompt: free-form rewrite

`--correct-mode rewrite` (default; used for both extractors). The model receives every detected
error and the current ontology and returns the whole corrected ontology; the candidate is
committed only if the reasoner reports strictly fewer errors and no new hard error (global
inconsistency or unsatisfiable class), paper Sections 3.3 and 3.5. The loop ends when no hard
error remains, when a candidate is rejected, or after 5 iterations.

## System message (`CORRECT_SYS`)

````text
You are repairing an OWL ontology that a description-logic reasoner found faulty. Return a corrected version of the WHOLE ontology in Turtle that removes the listed problems while preserving all correct content. Prefer removing or weakening the specific axiom that causes each problem (e.g. drop one of two disjoint parents that makes a class unsatisfiable; add a missing rdfs:domain/range). Do not introduce new classes that aren't supported. Output ONLY a single fenced ```turtle code block.
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
