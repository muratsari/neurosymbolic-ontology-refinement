# Corpus Source Selection - Criteria & Acceptance Gates

**Purpose.** Build a small, high-quality corpus suitable for **ontology extraction** - i.e. concept-dense, definitional, relation-bearing text - and explicitly avoid large, repetitive, instance-level data. Part A defines which sources are eligible. **Part B is the decisive part:** measurable pass/fail gates applied to every text unit, so that "the right kind of text" is enforced by tests rather than left to judgment. Part C defines the output manifest.

> These criteria operate **per sub-domain** and depend on a fixed **boundary contract** (an explicit in-scope / out-of-scope statement). Supply that contract together with this document; gates 4–5 and Acceptance Gate 3 rely on it.

---

# Part A - Source selection criteria

## 1. Language
- All texts in **English**. No translated or non-English sources.
## 2. Text type (eligibility)
Include only **concept-dense, definitional, relation-bearing** prose.
- **Must express:** term definitions; is-a / subtype relations; part-of relations; and domain relations (causal, functional, treatment, alignment, etc.).
- **Exclude:** bulk or repetitive **instance** data (regulatory filings, transactional records, individual syllabi, raw full-text article dumps); narrative, anecdotal, or historical text; news; opinion / blog-style content.
## 3. Required source layers (combine all four)
- **Encyclopedic** - definitional backbone + taxonomy (article leads + structural sections).
- **Terminological** - a domain glossary (term → definition pairs).
- **Reference** - a textbook / monograph section, relation-dense.
- **Normative / standards** - declarative rule text stating constraints (thresholds, mandatory relations); the source of disjointness and cardinality axioms.
## 4. Scope discipline (most critical)
- **Corpus scope = manual reference-ontology scope = sub-domain boundary contract.** All three identical.
- Every source must fall **inside the boundary**; exclude related-but-out-of-scope material.
- **No recursive link-following.** Selection by expert judgment plus at most **one** controlled expansion step; stop at the boundary.
## 5. Coverage (bidirectional)
- **Concept → text:** every in-scope concept the reference ontology models is supported by at least one definitional or relational passage.
- **Text → concept:** every concept the corpus introduces is in-scope; otherwise trim it.
## 6. Size & redundancy
- **Small but comprehensive:** target **20–60 curated units** per sub-domain, not thousands.
- **Low redundancy:** remove near-duplicates; no single source dominates.
## 7. Granularity & cleaning (a quality gate, not cosmetic)
- **Unit of text** = definitional lead + structural sections (self-contained, information-dense passages).
- **Strip:** markup, reference lists, navigation, infoboxes, and out-of-scope sections (e.g. *History*, *Society and culture*, *Epidemiology*).
- **Keep:** only definition- and relation-bearing paragraphs.
## 8. Authority & licensing
- Sources must be **authoritative** (reference works, official glossaries, standards bodies, peer-reviewed or textbook material) - not user-generated or unreliable.
- **Prefer openly licensed / text-mining-permitted** sources; record the license and any access restrictions.
## 9. Provenance & reproducibility
- For each unit, capture: **source type, title, URL, retrieval date, version / revision ID** (e.g. Wikipedia `oldid`).
- **Freeze** the corpus once assembled; document it in a **corpus card** (source list, versions, boundary contract, cleaning steps).

---

# Part B - Acceptance gates (apply to every text unit)

A unit enters the corpus **only if it passes Gates 1–3**. Gate 4 is a per-source spot-check. Thresholds are sensible defaults - tune once, then apply uniformly.

## Gate 1 - Definitional lead (pass/fail)
The unit's opening paragraph must **define a concept** - pattern "*X is a [kind of] Y that …*".
- **Pass:** opens with a definitional statement. **Fail:** opens into detail/examples/procedure/history with no definition.
## Gate 2 - Relation density (pass/fail)
The unit must contain explicit **definition/relation cues at minimum density**: **at least one lexico-syntactic pattern per ~150 words** (e.g. *is a type of, consists of, such as, is characterized by, is defined as, is used to, results in, causes, measures, requires*).
## Gate 3 - Concept yield / anti-redundancy (pass/fail)
The unit must introduce **at least one new in-scope concept** not already covered. *(Unit-level test against the "repetitive data" problem.)*
## Gate 4 - Manual extraction sanity test (per-source spot-check)
From a small sample of a source's units, **manually extract**: do a coherent mini-taxonomy + relations emerge? If a source yields only isolated facts/narrative → **reject the source**.

---

# Part C - Output format (corpus list = structured manifest)

One row per candidate **source**, with per-unit gate results recorded so acceptance is auditable.

| Field | Description |
|---|---|
| `domain` / `sub_domain` | Target domain and sub-domain |
| `source_type` | Layer: encyclopedic / terminological / reference / normative |
| `title` | Source title (and section, if a sub-part) |
| `url` | Source URL |
| `language` | Must be English |
| `in_scope` | yes / no + one-line justification against the boundary contract |
| `expected_concepts_relations` | What this source is expected to contribute |
| `definitional_lead` | Gate 1: pass / fail |
| `relation_density_ok` | Gate 2: pass / fail |
| `new_concepts` | Gate 3: count or short list of new in-scope concepts |
| `extraction_test` | Gate 4: pass / fail / n-a |
| `license` | License / reuse terms |
| `version_or_access_note` | Revision ID, retrieval date, access restrictions |

**Accept a source only if:** `in_scope = yes` **and** its units pass Gates 1–3 **and** `extraction_test ≠ fail`.

---

### Reminder
Quality is determined as much by **granularity & cleaning (§7)** and the **acceptance gates (Part B)** as by which sources are picked - the same encyclopedic article is gold when reduced to its definitional/structural sections and noise when taken whole. Always pair this document with the sub-domain's **boundary contract**.
