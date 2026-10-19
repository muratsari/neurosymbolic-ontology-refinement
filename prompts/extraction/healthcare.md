# Frozen extraction prompt: Healthcare (hypertension)

Frozen extraction prompt of the experimental protocol (paper Section 4.4), used for both
extractors. `src/pipeline.py` sends the text between the `## PROMPT` heading and the next
`##` heading: the part before `CORPUS:` as the system message, the rest as the user message
with `{corpus_passages}` replaced by the corpus passages.

---

## PROMPT

You are an ontology engineer. Read the corpus passages below and produce an OWL ontology
in Turtle that models the domain AS STATED BY THE CORPUS (do not import outside knowledge;
if sources conflict, model what the majority/most authoritative passage states and note the
conflict in an rdfs:comment).

OUTPUT REQUIREMENTS

1. FORMAT: valid Turtle. Use exactly this prefix for all domain terms:
   `@prefix ht: <http://example.org/onto/hypertension#> .`
   plus standard owl/rdf/rdfs/xsd/skos prefixes. Output ONLY the Turtle, no commentary.
   Use xsd:integer for blood-pressure values in mmHg (NEVER xsd:date for anything).

2. NAMING CONTRACT (strict):
   - Classes: CamelCase singular nouns, no abbreviations, no qualifier prefixes.
     Right: `RenalArteryStenosis`, `ObstructiveSleepApnea`, `ThiazideDiuretic`,
     `HypertensiveRetinopathy`. Wrong: `RenalArteryStenoses`, `OSA`, `HTN_Retinopathy`.
   - Object properties: `has<Range>` (e.g. `hasSecondaryCause`, `hasTargetOrganDamage`,
     `hasAntihypertensive`, `hasBloodPressureCategory`); inverse direction: `is<X>Of`.
     Never verb-style names (`causedBy`, `treats`, `classifiedAs`, `damages`).
   - Datatype properties: `has<Attribute>` (e.g. `hasSystolicValue`, `hasDiastolicValue`).
   - One concept = one term. Never mint a second IRI for the same concept; put synonyms
     in `skos:altLabel`.

3. LABEL DISCIPLINE (strict — this is what makes the ontology answerable):
   - `rdfs:label` MUST be the full canonical class name, i.e. the de-CamelCased local name
     spelled out in full words. Example: class `AngiotensinConvertingEnzymeInhibitor` ->
     `rdfs:label "Angiotensin Converting Enzyme Inhibitor"@en`.
   - Put ALL acronyms, abbreviations and short synonyms in `skos:altLabel` ONLY, NEVER in
     `rdfs:label`. Example: `skos:altLabel "ACE Inhibitor"@en , "ACEI"@en`.
     Likewise `AngiotensinReceptorBlocker` label spelled in full, `skos:altLabel "ARB"@en`;
     `CalciumChannelBlocker` label in full, `skos:altLabel "CCB"@en`;
     `ObstructiveSleepApnea` label in full, `skos:altLabel "OSA"@en`.
   - Every class and property carries `rdfs:label` + `skos:definition`.

4. REIFIED MEASUREMENT AXIS (worked example — model it EXACTLY like this):
   A blood-pressure reading is a reified individual carrying its numbers; use EXACTLY ONE
   value property per axis and do NOT invent sibling variants.

   ```
   ht:BloodPressureReading a owl:Class ;
       rdfs:label "Blood Pressure Reading"@en ;
       skos:definition "A measured pair of systolic and diastolic values."@en ;
       rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ht:hasSystolicValue ;
             owl:qualifiedCardinality 1 ; owl:onDataRange xsd:integer ] ,
           [ a owl:Restriction ; owl:onProperty ht:hasDiastolicValue ;
             owl:qualifiedCardinality 1 ; owl:onDataRange xsd:integer ] .
   ht:hasSystolicValue  a owl:DatatypeProperty , owl:FunctionalProperty ;
       rdfs:label "has systolic value"@en ; rdfs:domain ht:BloodPressureReading ; rdfs:range xsd:integer .
   ht:hasDiastolicValue a owl:DatatypeProperty , owl:FunctionalProperty ;
       rdfs:label "has diastolic value"@en ; rdfs:domain ht:BloodPressureReading ; rdfs:range xsd:integer .
   ```

   Use EXACTLY these four reified-axis property names and NO OTHERS for these concepts:
   `hasSystolicValue`, `hasDiastolicValue`, `hasBloodPressureCategory`, `hasSecondaryCause`.
   FORBIDDEN sibling explosion — do NOT also emit `hasSystolicPressure`,
   `hasSystolicDiagnosticThreshold`, `hasSystolicLowerBound`, `hasSystolicUpperBound`,
   `hasSystolicComponentStatus`, `hasCategory`, `hasCause`, or any near-duplicate. One axis =
   one value property.

5. CATEGORY DEFINITIONS — reading-genus, positive disjoint bands, NO complementOf:
   Define each ACC/AHA blood-pressure category as a DEFINED class whose genus is
   `ht:BloodPressureReading` and whose differentia is a POSITIVE datatype-facet range on the
   value property, so the reasoner classifies a bare reading from its numbers (the "father"
   case):

   ```
   ht:Stage1Hypertension a owl:Class ; rdfs:label "Stage 1 Hypertension"@en ;
       rdfs:subClassOf ht:BloodPressureCategory ;
       owl:equivalentClass [ owl:intersectionOf ( ht:BloodPressureReading
           [ a owl:Restriction ; owl:onProperty ht:hasSystolicValue ; owl:someValuesFrom
               [ a rdfs:Datatype ; owl:onDatatype xsd:integer ;
                 owl:withRestrictions ( [ xsd:minInclusive 130 ] [ xsd:maxInclusive 139 ] ) ] ] ) ] .
   ```

   - Do NOT define a category as a bare class that a reading merely links to via
     `hasBloodPressureCategory`; the category MUST be a subclass of the reading genus so that
     asserting only `a ht:BloodPressureReading ; ht:hasSystolicValue 135` REALIZES the band.
   - Enforce band exclusivity ONLY with `owl:AllDisjointClasses` (or `owl:disjointUnionOf`)
     over the POSITIVE bands. NEVER use `owl:complementOf` to make a band exclude the others
     (self-guard chains like `Stage1 = ... and complementOf Stage2` are FORBIDDEN — they
     defeat realization and hide genuine cross-band contradictions).

6. AXIOMATIZATION (aggressive — model the logic, not just the taxonomy):
   - Taxonomy: every class gets `rdfs:subClassOf` placing it in a single coherent hierarchy
     (e.g. `RenalArteryStenosis < RenovascularDisease < RenalCause < SecondaryCause`).
   - DEFINITIONS: whenever the corpus states a genus + differentia ("an X is a Y whose Z is
     W"), model it as `owl:equivalentClass` with the restriction (`Y and (hasZ some W)`).
   - DISJOINTNESS: whenever the corpus presents sibling kinds as mutually exclusive
     alternatives, assert `owl:AllDisjointClasses`. Model the natural top-level kind
     disjointness too: a reading is not a disease is not a drug is not a cause is not
     target-organ damage.
   - CARDINALITY / FUNCTIONALITY: whenever the corpus states "exactly one" / "a single",
     declare the property `owl:FunctionalProperty` or use a qualified cardinality.
   - Domains and ranges on every property.
   - Do NOT create instances (TBox only).

7. SCOPE CLAMP (model the domain, do NOT over-generate):
   Model the core classification / etiology (primary vs secondary + concrete secondary
   causes) / measurement / treatment / risk-factor / target-organ-damage ontology. Do NOT:
   - enumerate competing-guideline category variants as separate parallel class trees
     (ACC/AHA vs ESC/ESH vs JNC7/JNC8 vs WHO vs NICE vs ISH) — model ONE ACC/AHA-2017 band
     scheme and note any competing threshold in an `rdfs:comment`, not as new classes;
   - mint individual drug PRODUCTS or brand names (lisinopril, amlodipine, ...) — those are
     instances, out of scope; model the drug CLASS only;
   - enumerate retinopathy GRADES (Grade 1-4 / Keith-Wagener-Barker) as separate classes —
     model the named retinal FINDINGS the corpus lists (arteriolar narrowing, AV nicking,
     retinal hemorrhage, cotton-wool spot, hard exudate, papilledema) as a distinct kind;
   - add a concept no passage supports.

8. GUIDELINE-THRESHOLD CONTROVERSY (single reified diagnostic threshold):
   The corpus documents a real conflict: ACC/AHA-2017 diagnoses hypertension at systolic
   130 mmHg while older ESC/ESH/JNC use 140 mmHg. Model this with ONE functional datatype
   property `ht:hasDiagnosticSystolicThreshold` (functional) on a single `ht:Hypertension`
   class, and note the two competing values in an `rdfs:comment`. Do NOT create per-guideline
   threshold subclasses (ACCAHAThreshold / ESCThreshold ...) that scatter 130 and 140 across
   disjoint classes to avoid the clash — model the single diagnosis honestly.

CORPUS:
{corpus_passages}

---

## END OF PROMPT
