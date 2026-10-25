# Prompts

## extraction/

`finance.md`, `healthcare.md`, `education.md`: the frozen extraction prompt of each domain
(paper Section 4.4), the same for both extractors. `src/pipeline.py` reads the text between
the `## PROMPT` heading and the next `##` heading. The part before `CORPUS:` is sent as the
system message; `{corpus_passages}` is replaced by the corpus passages and sent, together
with whatever follows the placeholder, as the user message.

## correction/

`rewrite.md`: free-form correction, the model returns the whole corrected ontology
(`--correct-mode rewrite`, the default; used for both extractors; paper Section 3.5).

`patch.md`: compact edit list, the model returns only the edits (`--correct-mode patch`; an
option of `src/pipeline.py`, not used by the reported runs).

Both are followed by the same validation gate: a candidate is committed only if the reasoner
reports strictly fewer errors and no new hard error (global inconsistency or unsatisfiable
class).

The files in `correction/` mirror string constants of `src/pipeline.py`, which is what the
program actually sends. Two further prompts live only in the code: the alias-resolution prompt
used when a corpus is extracted in several chunks (`MERGE_ALIAS_SYS`) and a generic fallback for
a domain without a frozen prompt (`EXTRACT_SYS`); neither is used by the reported runs.
