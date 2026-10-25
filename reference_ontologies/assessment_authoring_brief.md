# Manual Reference Ontology - Brief
## Domain: Educational Assessment & Evaluation (Education)

You are building a **manual reference ("gold standard") ontology** for the sub-domain of **Educational Assessment & Evaluation**. This ontology will later be the target against which an automatically (AI-) generated ontology is compared. Please read the whole brief before starting; the logical-axiom requirements are not optional - they are the point of the study.

---

## 1. What this ontology is for

A neuro-symbolic framework generates ontologies from text and uses a Description Logic (DL) reasoner to detect and repair logical inconsistencies. Your hand-built ontology is the **independent reference** that the system's output will be measured against (precision / recall / F1) and the benchmark of what a logically well-formed ontology in this domain looks like.

Two properties matter above all:

1. **Logical richness.** The ontology must contain **disjointness** and **cardinality** axioms. This domain was chosen specifically because assessments are classified along **several independent (orthogonal) axes** - a single assessment can be simultaneously summative, norm-referenced, and written-performance. These cross-classifications are exactly what stresses a DL reasoner. Model each axis as its own disjoint set.
2. **Consistency.** The ontology you deliver must itself be **logically consistent** and contain **no unsatisfiable classes**, verified with a reasoner (see §7).

---

## 2. Independence rule (please respect strictly)

- Build the ontology from **authoritative domain sources + your own expertise** (see §6).
- **Do not** consult any experimental text corpus, and **do not** look at any AI-generated ontology. The value of this reference depends on it being produced independently.
- Work alone. If several people are assigned to this same domain, do **not** coordinate your modelling; differences between independent versions are wanted and will be reconciled afterwards.

---

## 3. General modelling constraints (apply throughout)

**Language & scale**
- All labels and definitions in **English**.
- Target **35–55 named classes**. Hard ceiling **~80**. If you exceed it you have drifted out of scope (typically into curriculum structure, education policy, or general statistical theory) - pull back to the scope contract in §4.

**Every class**
- Must have an `rdfs:label` and a **one-sentence definition** (`skos:definition` or `rdfs:comment`), citing the source where you can.

**Properties**
- Object properties must declare **explicit `rdfs:domain` and `rdfs:range`** (e.g. `measures` domain `Assessment`, range `LearningOutcome`).
- Use **data properties** where natural.

**Mandatory logical axioms - the core of the task**
- **Disjointness:** model the natural mutually-exclusive sets (`owl:DisjointClasses`; use `owl:DisjointUnion` when an axis is exhaustively partitioned). **Each classification axis must be internally disjoint** (see §4).
- **Cardinality / functionality:** model the natural numeric constraints (e.g. an assessment takes `exactly 1` value on each axis).
- **Existential restrictions** where appropriate, to enable inference (e.g. `FormativeAssessment SubClassOf providesFeedbackTo some Learner`).
- **Do not over-constrain** to the point of making the ontology inconsistent. The delivered ontology must be consistent.

> **Important polyhierarchy note:** a concrete assessment instance legitimately belongs to **one value per axis across several axes** (e.g. formative + criterion-referenced + written). This multiple membership across axes is intended. What must be impossible is **two values within the same axis** (e.g. an assessment cannot be both formative and summative). Encode disjointness **within** each axis, not across axes.

**Naming convention (mandatory - enables comparison/merging across annotators)**
- Classes: `UpperCamelCase`, singular noun - `FormativeAssessment`, `CriterionReferencedTest`.
- Object properties: `lowerCamelCase` verb phrase - `measures`, `isAlignedWith`, `hasFormat`.
- Data properties: `lowerCamelCase` - `hasReliabilityCoefficient`.
- **Base IRI (use exactly this):** `http://example.org/onto/assessment#` - suggested prefix `ea:`. If more than one annotator works on this domain, **all must use this identical base IRI**.

**Modelling level**
- Model the **schema (TBox) only**: classes, properties, axioms. Individuals are not required (a few example individuals are allowed only if you want to sanity-check a cardinality axiom).

**Method (recommended)**
- Before modelling, answer the competency questions in §5 - they surface the right classes and axioms and serve as a final checklist.

---

## 4. Scope contract (binding)

**In scope**
- **Purpose axis:** formative / summative / diagnostic.
- **Score-interpretation axis:** norm-referenced / criterion-referenced / ipsative.
- **Formality axis:** formal / informal.
- **Format axis:** written / oral / performance-based.
- **Measurement properties:** validity (and its types) and reliability (and its types).
- **Relations to learning outcomes:** `measures`, `isAlignedWith` (constructive alignment).
- **Components:** rubric, item, feedback.

**Out of scope**
- Curriculum structure (except the alignment link to learning outcomes).
- Branded/named standardized exams.
- Education policy / administration.
- Statistical theory beyond validity and reliability.

**Mandatory disjointness - the reason this sub-domain was chosen**
- Each of the four axes must be modelled as **internally disjoint** (multiple orthogonal disjointness). E.g. `FormativeAssessment`, `SummativeAssessment`, `DiagnosticAssessment` are pairwise disjoint within the purpose axis; likewise for each other axis.

**Mandatory cardinality**
- An `Assessment` takes **exactly one** value on each classification axis.

**Target size:** ~35–55 classes.

---

## 5. Competency questions (answer these first)

1. Along which independent axes can an assessment be classified?
2. Can an assessment be both formative **and** summative? (Impossible - within-axis disjointness.)
3. Can an assessment be simultaneously formative, criterion-referenced, **and** written? (Allowed - different axes.)
4. Which properties characterise the quality of an assessment? (Validity types, reliability types.)
5. How does an assessment relate to learning outcomes?
6. What is the relationship between validity and reliability?

---

## 6. Anchor sources (consult these, not the experimental corpus)

- **Normative / rule source:** AERA / APA / NCME, *Standards for Educational and Psychological Testing* - especially the **Validity** and **Reliability** chapters (the authoritative source for the mandatory relations among quality concepts).
- **Glossary:** *The Glossary of Education Reform* (EdGlossary) (term → definition).
- **Structured reference:** Linn & Gronlund, *Measurement and Assessment in Teaching* - the foundational-concepts chapters.
- **Encyclopedic backbone:** Wikipedia - *Educational assessment*, *Formative assessment*, *Summative assessment*, *Norm-referenced test*, *Criterion-referenced test*, *Validity (statistics)*, *Reliability (statistics)*, etc.

Using the same anchor sources is what lets independent versions converge.

---

## 7. Output format & constraints (please follow exactly)

**File / serialization**
- Deliver one **OWL 2 ontology** file.
- Serialization: **RDF/XML (`.owl`) preferred**, or **Turtle (`.ttl`)** accepted. UTF-8.
- **Stay within OWL 2 DL.** Protégé shows the active profile; if it reports the ontology is outside OWL 2 DL, adjust. In particular, do **not** combine property characteristics that violate DL simplicity (e.g. a property that is both transitive and functional/irreflexive/cardinality-restricted).

**Entity & metadata requirements**
- Every entity IRI = base IRI (§3) + CamelCase local name.
- Every class and property carries `rdfs:label` + a definition annotation.
- The ontology header must include: `owl:versionInfo`, a creator annotation (your anonymous annotator ID, e.g. `annotator-A`), and an `rdfs:comment` stating the scope in one sentence.

**Reasoner validation (required)**
- Run **HermiT** or **ELK** in Protégé.
- The ontology must be **consistent** with **no unsatisfiable classes** (no class inferred equivalent to `owl:Nothing`).
- Export/screenshot the reasoner result and include it (see deliverables).

**Deliverable bundle** (4 items)
1. The ontology file - `assessment_<annotatorID>.owl` (or `.ttl`).
2. **Ontology card** (`.md` or `.txt`, ~half page): scope contract used; sources consulted; class count; **the list of disjointness axioms (per axis)**; **the list of cardinality/restriction axioms**; naming convention confirmed; reasoner name + version + result.
3. **Decision log** (`.md` or `.txt`): ambiguous or contested modelling choices you made, with brief rationale.
4. **Reasoner report** (export or screenshot) showing consistency + no unsatisfiable classes.

---

## 8. Final checklist

- [ ] 35–55 classes (≤ ~80), all in scope.
- [ ] Every class has a label + one-sentence definition.
- [ ] Object properties have explicit domain & range.
- [ ] **Each of the four axes** modelled as internally disjoint.
- [ ] Cross-axis multiple membership left possible; within-axis membership constrained to one.
- [ ] At least one cardinality/`exactly` constraint per axis.
- [ ] Naming convention + exact base IRI followed.
- [ ] Reasoner run: consistent, no unsatisfiable classes.
- [ ] All four deliverables included.
