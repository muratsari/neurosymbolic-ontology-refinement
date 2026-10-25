# Reference ontologies

One hand-authored OWL 2 DL reference ontology (TBox only) per domain: the files every score in the
paper is computed against. The figures below are measured on the files in this folder
(`src/onto_utils.py`; HermiT through owlready2).

| Domain | File | Prefix | Named classes | Object properties | Datatype properties | Defined classes (`owl:equivalentClass`) | Disjointness axioms | HermiT | CQ suite |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| Finance | `securities.ttl` | `fis:` http://example.org/onto/securities# | 100 | 12 | 13 | 17 | 22 | consistent, no unsatisfiable class | `competency_questions/securities.cq.json` (21 questions) |
| Healthcare | `hypertension.ttl` | `ht:` http://example.org/onto/hypertension# | 96 | 6 | 3 | 7 | 19 | consistent, no unsatisfiable class | `competency_questions/hypertension.cq.json` (26 questions) |
| Education | `assessment.ttl` | `ea:` http://example.org/onto/assessment# | 76 | 16 | 4 | 7 | 16 | consistent, no unsatisfiable class | `competency_questions/assessment.cq.json` (24 questions) |

- `naming_contract.md`: the orthographic standard shared by the extraction prompts, the reference
  ontologies and the competency-question suites (paper Section 4.4).
- `securities_authoring_brief.md`, `assessment_authoring_brief.md`: the instructions the annotator
  worked from for the finance and education ontologies.
- Every class and property carries an `rdfs:label`; scoring aligns generated and reference terms by
  normalised label (`src/onto_utils.py`).
- Internal authoring notes were removed from the comments and from the `rdfs:comment` / `skos:note`
  annotations for publication. Axioms, labels and every other triple are identical to the files the
  scores were computed against; neither the scorer nor the reasoner reads these annotations.

Check a file yourself (prints consistency, unsatisfiable classes and class count as JSON):

```bash
python src/onto_utils.py reason reference_ontologies/securities.ttl
```
