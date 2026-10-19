# Naming contract (v1, 2026-07-03)

The naming contract is the orthographic standard shared by the three artifacts of the study:
the extraction prompt, the reference ontology and the competency-question suite (paper
Section 4.4). Structural scoring aligns generated and reference terms by strict normalised-label
matching, so the three artifacts must spell names the same way; the contract fixes that spelling.
It does not disclose the vocabulary of the reference ontology.

## Rules

1. **Classes:** CamelCase singular nouns, no abbreviations, no qualifier prefixes.
   - Right: `GovernmentBond`, `Future`, `EquityDerivative`
   - Wrong: `GovernmentBonds`, `FuturesContract`, `GovtBond`, `WHO_Hypertension`
2. **Object properties:** `has<Range>`, and `is<X>Of` for the inverse direction.
   - Right: `hasIssuer`, `hasUnderlying`, `isUnderlyingOf`
   - Wrong: `issuedBy`, `issues`, `tracksIndex`, `convertibleInto`
3. **Datatype properties:** `has<Attribute>`.
   - Right: `hasMaturityDate`, `hasStrikePrice`
4. **One concept, one term:** never mint a second IRI for the same concept; synonyms and
   acronyms go into `rdfs:label` or `skos:altLabel`.

## Where it applies

- **Extraction prompts** (`prompts/extraction/`): the rules are stated verbatim in every frozen
  prompt, with domain-specific examples.
- **Reference ontologies** (`reference_ontologies/<domain>.ttl`): authored under the
  same rules; the few terms of earlier versions that did not comply were renamed (name only,
  meaning unchanged).
- **Competency-question suites** (`competency_questions/`): probe only reference terms that
  follow the contract; a suite is frozen before the runs.

## What it does not do

The contract does not loosen the matcher. Scoring remains strict normalised-label matching
(`src/onto_utils.py`, `_norm`); no LLM-based equivalence judgement is used, because it would
be neither reproducible nor free of self-preference. The only secondary alignment is the
deterministic morphological fallback of the CQ scorer (`CQ_FUZZY=1` in
`evaluation/cq_apply.py`), reported as a lenient secondary, never as the headline.
