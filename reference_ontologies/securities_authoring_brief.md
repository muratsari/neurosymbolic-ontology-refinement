# Manual Reference Ontology - Brief
## Domain: Financial Instruments & Securities (Finance)

You are building a **manual reference ("gold standard") ontology** for the sub-domain of **Financial Instruments & Securities**. This ontology will later be the target against which an automatically (AI-) generated ontology is compared. Please read the whole brief before starting; the logical-axiom requirements are not optional - they are the point of the study.

---

## 1. What this ontology is for

A neuro-symbolic framework generates ontologies from text and uses a Description Logic (DL) reasoner to detect and repair logical inconsistencies. Your hand-built ontology is the **independent reference** that the system's output will be measured against (precision / recall / F1) and the benchmark of what a logically well-formed ontology in this domain looks like.

Two properties matter above all:

1. **Logical richness.** The ontology must contain **disjointness** and **cardinality** axioms. Financial instruments are *defined by rules*, so this domain is rich in hard constraints: every security has exactly one issuer, every derivative references an underlying asset, debt instruments have a maturity. These are precisely what a reasoner can check. Model them explicitly.
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
- Target **30–50 named classes**. Hard ceiling **~80**. If you exceed it you have drifted out of scope (typically into trading mechanics, market microstructure, or accounting/tax detail) - pull back to the scope contract in §4.

**Every class**
- Must have an `rdfs:label` and a **one-sentence definition** (`skos:definition` or `rdfs:comment`), citing the source where you can.

**Properties**
- Object properties must declare **explicit `rdfs:domain` and `rdfs:range`** (e.g. `hasIssuer` domain `Security`, range `Issuer`).
- Use **data properties** where natural (e.g. maturity date, coupon rate, face value).

**Mandatory logical axioms - the core of the task**
- **Disjointness:** model the natural mutually-exclusive sets (`owl:DisjointClasses`; use `owl:DisjointUnion` when a class is exhaustively partitioned).
- **Cardinality / functionality:** model the natural numeric constraints (e.g. `hasIssuer exactly 1`).
- **Existential restrictions** where appropriate, to enable inference (e.g. `Derivative SubClassOf hasUnderlying some Asset`) - derivatives referencing an underlying asset make a good test bed for chained inference.
- **Do not over-constrain** to the point of making the ontology inconsistent. The delivered ontology must be consistent.

**Naming convention (mandatory - enables comparison/merging across annotators)**
- Classes: `UpperCamelCase`, singular noun - `DebtInstrument`, `MutualFund`.
- Object properties: `lowerCamelCase` verb phrase - `hasIssuer`, `hasUnderlying`, `paysCoupon`.
- Data properties: `lowerCamelCase` - `hasMaturityDate`, `hasFaceValue`.
- **Base IRI (use exactly this):** `http://example.org/onto/securities#` - suggested prefix `fis:`. If more than one annotator works on this domain, **all must use this identical base IRI**.

**Modelling level**
- Model the **schema (TBox) only**: classes, properties, axioms. Individuals are not required (a few example individuals are allowed only if you want to sanity-check a cardinality axiom).

**Method (recommended)**
- Before modelling, answer the competency questions in §5 - they surface the right classes and axioms and serve as a final checklist.

---

## 4. Scope contract (binding)

**In scope**
- **Instrument taxonomy:** equity/stock; debt/bond; derivative (option, future, swap); fund (mutual fund, ETF).
- **Defining attributes:** issuer, maturity, coupon, dividend, face value, underlying asset.
- **Relations:** `issuedBy`, `hasUnderlying`, `paysCoupon`, `hasMaturity`, etc.

**Out of scope**
- Trading mechanics, order types, market microstructure.
- Specific companies / tickers / real instances.
- Accounting and tax treatment beyond plain definitions.
- Regulatory filing procedures.

**Mandatory disjointness**
- `Equity`, `DebtInstrument`, `Derivative`, `Fund` are pairwise disjoint (ideally a `DisjointUnion` of `FinancialInstrument` or `Security`).

**Mandatory cardinality / restrictions**
- `Security SubClassOf hasIssuer exactly 1`.
- `Derivative SubClassOf hasUnderlying some Asset`.
- Represent debt attributes as restrictions (e.g. `DebtInstrument SubClassOf hasMaturity some ...`).

**Target size:** ~30–50 classes.

---

## 5. Competency questions (answer these first)

1. What are the main classes of financial instrument, and how do they differ?
2. What must **every** security have? (Exactly one issuer.)
3. What distinguishes a bond from a stock?
4. What must **every** derivative reference? (An underlying asset.)
5. Which attributes characterise a debt instrument? (Maturity, coupon, face value.)
6. Can an instrument be **both** equity and debt? (It must be impossible - disjointness.)

---

## 6. Anchor sources (consult these, not the experimental corpus)

- **Normative / rule source:** SEC (U.S. Securities and Exchange Commission) summary material on securities, or **IFRS 9 (Financial Instruments)** summary (defines the legal/ontological boundaries of instrument classes).
- **Glossary:** **BIS (Bank for International Settlements) Glossary** or **Nasdaq Glossary** - formal, structured definitions (prefer these over blog-style sources).
- **Structured reference:** CFA Institute Level 1 readings - Fixed Income / Equity / Alternative Investments (information-dense, purely conceptual definitions).
- **Encyclopedic backbone:** Wikipedia - *Security (finance)*, *Financial instrument*, *Stock*, *Bond*, *Derivative*, *Option*, *Mutual fund*, *Exchange-traded fund*, etc.

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
1. The ontology file - `securities_<annotatorID>.owl` (or `.ttl`).
2. **Ontology card** (`.md` or `.txt`, ~half page): scope contract used; sources consulted; class count; **the list of disjointness axioms**; **the list of cardinality/restriction axioms**; naming convention confirmed; reasoner name + version + result.
3. **Decision log** (`.md` or `.txt`): ambiguous or contested modelling choices you made, with brief rationale.
4. **Reasoner report** (export or screenshot) showing consistency + no unsatisfiable classes.

---

## 8. Final checklist

- [ ] 30–50 classes (≤ ~80), all in scope.
- [ ] Every class has a label + one-sentence definition.
- [ ] Object properties have explicit domain & range.
- [ ] Equity / DebtInstrument / Derivative / Fund modelled as disjoint.
- [ ] `hasIssuer exactly 1` present.
- [ ] `Derivative hasUnderlying some Asset` present.
- [ ] Naming convention + exact base IRI followed.
- [ ] Reasoner run: consistent, no unsatisfiable classes.
- [ ] All four deliverables included.
