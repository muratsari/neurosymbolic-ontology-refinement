# Frozen extraction prompt: Education (assessment)

Frozen extraction prompt of the experimental protocol (paper Section 4.4), used for both
extractors. `src/pipeline.py` sends the text between the `## PROMPT` heading and the next
`##` heading: the part before `CORPUS:` as the system message, the rest as the user message
with `{corpus_passages}` replaced by the corpus passages.

---

## PROMPT

You are an ontology engineer. Read the corpus passages below and produce an OWL ontology
in Turtle that models the domain AS STATED BY THE CORPUS (do not import outside knowledge).
Model every classification claim the corpus makes, even when passages disagree: if one
passage lists categories as coordinate alternatives and another subordinates one category
under another, encode BOTH claims as axioms and note the tension in an rdfs:comment. Do not
resolve conflicts by omitting one side.

OUTPUT REQUIREMENTS

1. FORMAT: valid Turtle. Use exactly this prefix for all domain terms:
   `@prefix ea: <http://example.org/onto/assessment#> .`
   plus standard owl/rdf/rdfs/xsd/skos prefixes. Output ONLY the Turtle, no commentary.
   Datatypes: OWL 2 DL only (use xsd:decimal, xsd:integer, xsd:boolean, xsd:string,
   xsd:dateTime; never xsd:date).

2. NAMING CONTRACT (strict):
   - Classes: CamelCase singular nouns, no abbreviations, no qualifier prefixes.
     Right: `FormativeAssessment`, `StandardizedTest`, `MultipleChoiceItem`.
     Wrong: `FormativeAssessments`, `StdTest`, `MCQ_Item`.
   - Object properties: `has<Range>` (e.g. `hasPurpose`, `hasRubric`, `hasLearningOutcome`);
     inverse direction: `is<X>Of` (e.g. `isItemOf`). Never verb-style names (`assesses`,
     `measuredBy`, `interpretsAgainst`, `contributesToGrade`).
   - Datatype properties: `has<Attribute>` (e.g. `hasReliabilityCoefficient`,
     `hasItemCount`). Never bare booleans as names (`isStandardized`): name the attribute.
   - One concept = one term. Never mint a second IRI for the same concept; put synonyms
     and acronyms in `rdfs:label` / `skos:altLabel` (e.g. class `MultipleChoiceItem` may
     carry altLabel "MCQ"; class `NormGroup` may carry altLabel "norming group").

3. AXIOMATIZATION (aggressive — model the logic, not just the taxonomy):
   - Taxonomy: every class gets `rdfs:subClassOf` placing it in a single coherent hierarchy.
   - DEFINITIONS: whenever the corpus states a genus + differentia ("an X is a Y whose Z
     is W"), model it as `owl:equivalentClass` with the restriction
     (`Y and (hasZ some W)`) — not merely subClassOf. Aim to define every classifiable
     leaf/family this way.
   - AXIS REIFICATION (worked example): when the corpus classifies a kind along an axis
     (e.g. purpose), reify the axis as a functional property `has<Axis>` with a
     value-partition class, and define the named kind as an equivalentClass bridge:
       `ea:DiagnosticAssessment owl:equivalentClass [ owl:intersectionOf ( ea:Assessment
        [ a owl:Restriction ; owl:onProperty ea:hasPurpose ;
          owl:someValuesFrom ea:DiagnosticPurpose ] ) ] .`
       `ea:PurposeCategory owl:disjointUnionOf ( ...its purpose value classes... ) .`
     Complete the whole chain in one place: the property, the value classes, the disjoint
     union, and one bridge definition per named kind.
   - DISJOINTNESS: whenever the corpus presents sibling kinds as mutually exclusive
     alternatives, assert `owl:AllDisjointClasses` (or pairwise `owl:disjointWith`).
     Treat every enumerated list of kinds ("X can be divided into A, B, C") as an
     exhaustive, pairwise-disjoint partition unless the corpus explicitly states overlap.
   - CARDINALITY / FUNCTIONALITY: whenever the corpus states "exactly one" / "a single",
     declare the property `owl:FunctionalProperty` or use a qualified cardinality.
   - Domains and ranges on every property.
   - Do NOT create instances (TBox only).

4. SCOPE: cover the corpus comprehensively but do not invent concepts that no passage
   supports.

CORPUS:
{corpus_passages}

---

## END OF PROMPT
