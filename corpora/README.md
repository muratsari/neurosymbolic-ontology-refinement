# Corpora

One corpus per domain, as JSON Lines: one unit (passage) per line.

| Paper | Folder | File |
|---|---|---|
| Finance | `finance/` | `corpus.jsonl` |
| Healthcare | `healthcare/` | `corpus.jsonl` |
| Education | `education/` | `corpus.jsonl` |

These files are the frozen experimental input and are provided exactly as used in the runs.
`corpus_source_selection_criteria.md` states how sources were chosen and which acceptance
gates a text unit had to pass. `scrape.py` is the retrieval and preprocessing script
(`python scrape.py <seeds.json> <output folder>`); `finance/seeds.json` and
`education/seeds.json` are its inputs (seed articles, section drops, concept synonyms, the
glossary pages of the terminological layer). Units that carry a `register` field, and the whole
healthcare corpus, were collected by hand from the source named in the unit and have no seeds
file. `concept_ttl` in the seeds points to the current reference ontology; the frozen corpora
were gated against the first version of that concept inventory, so a new scrape does not
reproduce them unit for unit (and source pages change).

## Fields

Every unit has `source`, `url` and `license`, and `text` unless the text is withheld. Depending
on how a unit was collected it also has `doc_id`, `title`, `section`, `revision_id`,
`retrieved_at`, `register` or `retrieved`. Units whose licence was checked against the source
page for this package also carry `license_verified` (date) and `license_evidence_url`.

## Licences and withheld text

The corpora are third-party text and each unit keeps the licence of its source. Text is
included where the source licence allows redistribution. Where it does not, the unit is listed
without its text:

```json
{"source": "...", "url": "...", "license": "...", "text_withheld": true,
 "text_withheld_reason": "...", "text_word_count": 123, "text_sha256": "..."}
```

| Domain | Units | Words | Units without text | Words withheld | Share of words withheld |
|---|---:|---:|---:|---:|---:|
| Finance | 234 | 78,349 | 33 | 4,908 | 6.3% |
| Healthcare | 135 | 19,747 | 67 | 8,522 | 43.2% |
| Education | 173 | 51,998 | 0 | 0 | 0.0% |

### Finance

Text included, by licence:

- 162 units: CC BY-SA 4.0
- 14 units: © European Central Bank - reproduction permitted with acknowledgement of source
- 11 units: US government work (public domain)
- 9 units: CC BY 4.0
- 5 units: ECB copyright notice (free use of website information permitted, ECB must be cited as the source)

Text withheld, by reason:

- 29 units: source terms do not permit redistribution. Sources: Corporate Finance Institute; FINRA; IFRS Foundation - IAS 32; IFRS Foundation - IFRS 9
- 4 units: redistribution rights not established. Sources: Bank for International Settlements glossary

### Healthcare

Text included, by licence:

- 42 units: CC BY-SA 4.0
- 9 units: CC BY 4.0
- 6 units: CC BY-NC-SA 3.0 IGO
- 4 units: public domain
- 3 units: CC BY 4.0 (Creative Commons Attribution 4.0 International)
- 2 units: Public domain (US government work - National High Blood Pressure Education Program / National Heart, Lung, and Blood Institute (US), NIH Publication No. 04-5230)
- 1 unit: CC BY
- 1 unit: CC BY 4.0 (Creative Commons Attribution License CC-BY 4.0)

Text withheld, by reason:

- 31 units: source terms do not permit redistribution. Sources: 2017 ACC/AHA Hypertension Guideline (summary); 2018 ESC/ESH Guidelines (definition and pressure goals); 2018 ESC/ESH Guidelines (diagnostic evaluation); 2018 ESC/ESH Guidelines (out-of-office measurement); 2018 ESC/ESH Guidelines for the management of arterial hypertension; 2020 International Society of Hypertension Global Hypertension Practice Guidelines; 2023 ESH Guidelines for the management of arterial hypertension; 2023 ESH Hypertension Guideline Update (ACC.org); American College of Cardiology; Cleveland Clinic; Cleveland Clinic: Antihypertensives; European Society of Cardiology; Hypertension phenotypes (Hypertension Research overview); Merck Manual (Professional); Merck Manual Professional Edition: Overview of Hypertension; Thresholds for Hypertension Definition, Treatment Initiation, and Treatment Targets (Circulation); Types and stages of hypertension (overview)
- 30 units: source licence (CC BY-NC-ND) permits redistribution of unmodified copies only. Sources: Hypertension-mediated organ damage overview (PMC/StatPearls); StatPearls (NCBI Bookshelf)
- 4 units: source licence is territorially restricted. Sources: NICE NG136 / hypertension phenotypes; NICE NG136 Hypertension in adults: diagnosis and management
- 2 units: redistribution rights not established. Sources: JNC 7 (NCBI Bookshelf)

### Education

Text included, by licence:

- 142 units: CC BY-SA 4.0
- 31 units: CC BY-NC-SA 4.0 (Great Schools Partnership)

## Obtaining the withheld text

The source of every withheld unit can be consulted at its `url`. The unit text used in the
runs is available from the authors on request for research use; `text_sha256` and
`text_word_count` identify it.

## What depends on the corpora

Scoring and statistics do not read the corpora: every table and figure of the paper is
reproducible from `results/` without them. `src/pipeline.py` skips withheld units and says so,
which means a new extraction run sees less text than the reported runs did.
