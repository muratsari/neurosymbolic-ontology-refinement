#!/usr/bin/env python
"""
Multi-source ontology-extraction corpus scraper (Python 3 stdlib only).

Builds a small, concept-dense, definitional/relation-bearing corpus for one
sub-domain from several OPEN, text-mining-permitted sources, enforcing the
project's acceptance gates and measuring how well the corpus covers the
concepts of the matching hand-built gold-standard ontology.

Supported source kinds (all configured in seeds.json):
  * Wikipedia (default)           - MediaWiki TextExtracts (clean plain text)
  * wiki_sources, mode "extracts" - any Wikimedia wiki (Wikibooks/Wikiversity/...)
  * wiki_sources, mode "parse"    - any MediaWiki w/o TextExtracts (WikiDoc,
                                    Open Risk Manual): action=parse -> HTML -> text
  * other_layers, fetch:true      - open HTML pages (NIDDK, MedlinePlus, ECB ...)
  * other_layers, fetch:false     - documented only (ToS/PDF), not auto-fetched

Usage:  python scrape.py <seeds.json> <out_dir>

Outputs in <out_dir>:
  corpus.jsonl        one JSON record per accepted text unit (+ provenance)
  units_manifest.csv  every candidate unit with its gate results (audit trail)
  coverage_report.md  ontology-concept coverage of the accepted corpus
  corpus_card.md      frozen description (per-source counts, versions, gates)
"""
import sys, os, re, json, csv, time, html, hashlib, urllib.request, urllib.parse, datetime
import subprocess, tempfile, shutil

UA = ("NeuroSymbolicOnto-CorpusBuilder/1.0 "
      "(academic ontology-learning research; contact: see the repository page)")
WP_API = "https://en.wikipedia.org/w/api.php"
MIN_UNIT_WORDS = 25
WORDS_PER_CUE = 150
DEFAULT_MAX_UNITS_PER_SOURCE = 100   # cap on *relational-extra* units; new-concept units always pass
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
NOW = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

DEFAULT_DROP = [
    "history", "society and culture", "epidemiology", "see also", "references",
    "external links", "further reading", "notes", "citations", "bibliography",
    "gallery", "in popular culture", "etymology", "footnotes", "sources",
    "media", "navigation", "contents", "references and notes", "external resources",
    "related pages", "related links", "more information", "on this page",
    # cookie / privacy / site-chrome banners (seen on rendered glossary pages)
    "our website uses cookies", "thank you!", "we have updated our privacy policy",
    "your cookie preference has expired", "cookie preference", "privacy policy",
    "cookies", "newsletter", "subscribe", "share this page", "follow us",
]
CUES = [
    "is a type of", "are a type of", "is a kind of", "is a form of", "types of",
    "is a group of", "consists of", "is composed of", "composed of", "is part of",
    "part of", "such as", "is characterized by", "characterized by",
    "is defined as", "defined as", "refers to", "is used to", "used to",
    "results in", "leads to", "caused by", "causes", "due to", "measures",
    "is measured", "requires", "is associated with", "associated with",
    "known as", "also called", "including", "for example", "classified as",
    "divided into", "consist of", "comprises", "comprising", "based on",
    "depends on", "in order to", "can be", "may be", "issued by", "backed by",
    "secured by", "represents", "entitles", "obligates", "pays",
]
DEFN = [" is a ", " is an ", " are a ", " is the ", " is any ", " is a group of ",
        " refers to ", " is defined as ", " are ", " is ", " denotes ", " means "]


# --------------------------------------------------------------------------- #
# HTTP / MediaWiki helpers
# --------------------------------------------------------------------------- #
def http_get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def api_get(api, params):
    params = dict(params); params.update({"format": "json", "formatversion": "2"})
    return json.loads(http_get(api + "?" + urllib.parse.urlencode(params)))


def mw_search(api, query, limit):
    try:
        d = api_get(api, {"action": "query", "list": "search", "srsearch": query,
                          "srlimit": str(limit), "srnamespace": "0"})
        return [s["title"] for s in d.get("query", {}).get("search", [])]
    except Exception as e:
        sys.stderr.write(f"  ! search failed {api} {query!r}: {e}\n")
        return []


def fetch_extracts(api, title):
    """Wikimedia TextExtracts -> (title, revid, ts, plaintext w/ == headers ==)."""
    try:
        d = api_get(api, {"action": "query", "prop": "extracts|revisions",
                          "titles": title, "explaintext": "1",
                          "exsectionformat": "wiki", "rvprop": "ids|timestamp",
                          "redirects": "1"})
        pages = d.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return None
        pg = pages[0]; rev = pg.get("revisions", [{}])[0]
        ex = pg.get("extract", "")
        if len(ex) < 80:
            return None
        return (pg["title"], rev.get("revid"), rev.get("timestamp"), ex)
    except Exception as e:
        sys.stderr.write(f"  ! extracts failed {title!r}: {e}\n")
        return None


def html_to_sectioned_text(htmltext):
    """Convert an HTML fragment/page to plain text with == headers == markers."""
    t = re.sub(r"(?is)<(script|style|noscript|nav|header|footer|aside|form|"
               r"figure|figcaption)\b.*?</\1>", " ", htmltext)
    t = re.sub(r"(?is)<table\b.*?</table>", " ", t)            # drop tables (nav/infobox)
    t = re.sub(r'(?is)<h([1-4])\b[^>]*>(.*?)</h\1>',
               lambda m: "\n\n== " + re.sub(r"(?s)<[^>]+>", "", m.group(2)).strip()
                         + " ==\n\n", t)
    t = re.sub(r"(?is)</(p|li|div|tr|h[5-6]|dt|dd)>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\[\s*edit\s*\]", " ", t, flags=re.I)
    t = re.sub(r"\[\d+\]", " ", t)                              # ref markers
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n[ \t]+", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def fetch_parse(api, title):
    """action=parse for MediaWiki without TextExtracts (WikiDoc, Open Risk Manual)."""
    try:
        d = api_get(api, {"action": "parse", "page": title,
                          "prop": "text|revid", "redirects": "1", "disabletoc": "1"})
        p = d.get("parse")
        if not p or "text" not in p:
            return None
        text = html_to_sectioned_text(p["text"])
        if len(text) < 80:
            return None
        return (p.get("title", title), p.get("revid"), None, text)
    except Exception as e:
        sys.stderr.write(f"  ! parse failed {title!r}: {e}\n")
        return None


def fetch_html_page(url):
    """Generic open HTML page (gov / open glossary) -> (title, None, None, text)."""
    try:
        raw = http_get(url)
        title = ""
        m = re.search(r"(?is)<title>(.*?)</title>", raw)
        if m:
            title = html.unescape(re.sub(r"(?s)<[^>]+>", "", m.group(1))).strip()
        return (title or url, None, None, html_to_sectioned_text(raw))
    except Exception as e:
        sys.stderr.write(f"  ! html fetch failed {url}: {e}\n")
        return None


def find_chrome(explicit=None):
    """Locate a headless-capable Chromium browser (system Chrome/Chromium/Edge)."""
    for c in [explicit, os.environ.get("CHROME_BIN")] + CHROME_CANDIDATES + [
            shutil.which("google-chrome"), shutil.which("chromium"),
            shutil.which("chromium-browser"), shutil.which("chrome")]:
        if c and os.path.exists(c):
            return c
    return None


_CHROME_PROFILE = None


def _chrome_profile():
    """One persistent profile per process (fast after first launch; no cross-process
    lock conflicts because the name includes the PID)."""
    global _CHROME_PROFILE
    if _CHROME_PROFILE is None:
        _CHROME_PROFILE = os.path.join(tempfile.gettempdir(), f"nso-chrome-{os.getpid()}")
        os.makedirs(_CHROME_PROFILE, exist_ok=True)
    return _CHROME_PROFILE


def fetch_rendered(url, chrome, budget_ms=15000, timeout=80):
    """Render a JS page with headless Chrome and return cleaned, sectioned text.
    Used for client-side-rendered sources (e.g. the ECB glossary). Robust to a
    lingering browser process: --dump-dom emits the DOM at the end, so even if the
    process must be killed on timeout we keep whatever it already printed."""
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
           "--no-default-browser-check", "--hide-scrollbars", "--mute-audio",
           "--disable-extensions", "--disable-sync", "--no-pings",
           "--user-data-dir=" + _chrome_profile(),
           "--virtual-time-budget=" + str(budget_ms), "--dump-dom", url]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
    except Exception as e:
        sys.stderr.write(f"  ! render launch failed {url}: {e}\n")
        return None
    try:
        raw, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        try:
            raw, _ = p.communicate(timeout=10)
        except Exception:
            raw = ""
    if not raw or len(raw) < 200:
        sys.stderr.write(f"  ! render returned too little for {url}\n")
        return None
    title = ""
    m = re.search(r"(?is)<title>(.*?)</title>", raw)
    if m:
        title = html.unescape(re.sub(r"(?s)<[^>]+>", "", m.group(1))).strip()
    return (title or url, None, None, html_to_sectioned_text(raw))


# --------------------------------------------------------------------------- #
# Text processing
# --------------------------------------------------------------------------- #
def split_units(text, drop_set):
    units = []
    parts = re.split(r'(?m)^(=+)\s*(.*?)\s*\1\s*$', text)
    lead = parts[0].strip()
    if lead:
        units.append(("Lead", lead, True))
    stack = []
    i = 1
    while i + 2 <= len(parts):
        lvl = len(parts[i]); name = parts[i + 1].strip(); body = (parts[i + 2] or "").strip()
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        stack.append((lvl, name))
        path = [n for (_, n) in stack]
        dropped = any(n.strip().lower() in drop_set for n in path)
        if body:
            units.append((" > ".join(path), body, not dropped))
        i += 3
    return units


def load_concepts(ttl_path):
    concepts = {}
    if not ttl_path or not os.path.isfile(ttl_path):
        return concepts
    txt = open(ttl_path, encoding="utf-8").read()
    for block in re.split(r'\n\s*\n', txt):
        if "owl:Class" not in block:
            continue
        m = re.search(r'rdfs:label\s+"([^"]+)"', block)
        if m:
            concepts[m.group(1).strip().lower()] = m.group(1).strip()
    return concepts


def build_matcher(concepts, synonyms):
    matcher = {low: orig for low, orig in concepts.items()}
    for canon, variants in (synonyms or {}).items():
        for v in variants:
            v = v.strip().lower()
            if v:
                matcher[v] = canon
    return matcher


def concept_hits(text, matcher):
    low = text.lower(); hits = set()
    for surface, canon in matcher.items():
        pat = r'\b' + re.escape(surface).replace(r'\ ', r'[ \-]') + r'\b'
        if re.search(pat, low):
            hits.add(canon)
    return hits


def gate1_definitional(body):
    first = re.split(r'(?<=[.!?])\s', body.strip(), maxsplit=1)[0]
    fl = " " + first.lower() + " "
    return any(d in fl for d in DEFN)


def gate2_density(body):
    words = max(1, len(body.split()))
    low = body.lower()
    cues = sum(low.count(c) for c in CUES)
    return cues >= max(1, round(words / WORDS_PER_CUE)), cues, words


def sig_of(body):
    # full normalized text: dedups only EXACT repeats (e.g. the same article fetched
    # twice); different glossary pages that share a nav/cookie prefix stay distinct,
    # and differently-worded passages of the same concept are kept (useful variety).
    norm = re.sub(r"\s+", " ", body.lower()).strip()
    return hashlib.md5(norm.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    if len(sys.argv) != 3:
        print("Usage: python scrape.py <seeds.json> <out_dir>"); sys.exit(2)
    seeds = json.load(open(sys.argv[1], encoding="utf-8"))
    outdir = sys.argv[2]; os.makedirs(outdir, exist_ok=True)
    seeds_dir = os.path.dirname(os.path.abspath(sys.argv[1]))

    drop_set = set(DEFAULT_DROP) | {s.strip().lower()
                                    for s in seeds.get("drop_sections", [])}
    ttl = seeds.get("concept_ttl")
    if ttl and not os.path.isabs(ttl):
        ttl = os.path.normpath(os.path.join(seeds_dir, ttl))
    concepts = load_concepts(ttl)
    matcher = build_matcher(concepts, seeds.get("concept_synonyms", {}))
    max_per = seeds.get("max_units_per_source", DEFAULT_MAX_UNITS_PER_SOURCE)
    print(f"[{seeds['sub_domain']}] {len(concepts)} concept labels, "
          f"{len(matcher)} surface forms")

    # ---- assemble source jobs ----
    jobs = []  # (name, kind, license, source_type, fetcher, items)
    wp_titles = list(dict.fromkeys(seeds.get("wikipedia_seeds", [])))
    exp = seeds.get("expansion", {})
    if exp.get("enabled") and wp_titles:
        seed_set = set(wp_titles); cand = set()
        for t in wp_titles:
            try:
                d = api_get(WP_API, {"action": "query", "prop": "links",
                                     "titles": t, "pllimit": "500",
                                     "plnamespace": "0", "redirects": "1"})
                for pg in d.get("query", {}).get("pages", []):
                    for l in pg.get("links", []):
                        cand.add(l["title"])
            except Exception:
                pass
            time.sleep(0.2)
        add = [t for t in sorted(cand) if t not in seed_set
               and (not exp.get("concept_matched_only", True)
                    or t.lower() in concepts)]
        wp_titles += add
        print(f"  Wikipedia expansion: +{len(add)} concept-matched articles")
    if wp_titles:
        jobs.append({"name": "Wikipedia (en)", "license": "CC BY-SA 4.0",
                     "source_type": "encyclopedic", "mode": "extracts",
                     "api": WP_API, "titles": wp_titles})

    for ws in seeds.get("wiki_sources", []):
        titles = list(ws.get("titles", []))
        for q in ws.get("search", []):
            titles += mw_search(ws["api"], q, ws.get("search_limit", 3))
            time.sleep(0.2)
        jobs.append({"name": ws["name"], "license": ws.get("license", ""),
                     "source_type": ws.get("source_type", "encyclopedic"),
                     "mode": ws.get("mode", "extracts"), "api": ws["api"],
                     "titles": list(dict.fromkeys(titles))})

    # ---- process jobs ----
    records, manifest_rows, pages_meta = [], [], []
    seen_concepts, seen_sigs = set(), set()
    per_source_counts = {}

    def process_unit(rec_src, title, url, revid, section, body, mode):
        words = len(body.split())
        hits = concept_hits(body, matcher)
        new = hits - seen_concepts
        is_lead = (section == "Lead")
        g1 = gate1_definitional(body) if (is_lead and mode == "extracts") else None
        g2_ok, cues, _ = gate2_density(body)
        too_short = words < MIN_UNIT_WORDS
        dup = sig_of(body) in seen_sigs
        in_scope = (len(hits) > 0) or (is_lead and mode == "extracts")
        # Gate 3: new concept OR a genuinely relational unit (>=2 concepts + density)
        relational = (len(hits) >= 2 and g2_ok)
        g3_ok = (len(new) >= 1) or relational
        # cap bounds only RELATIONAL-EXTRA units; units adding a NEW concept always pass
        has_new = len(new) >= 1
        over_cap = per_source_counts.get(rec_src, 0) >= max_per
        accepted = bool(in_scope and (g1 is not False) and g2_ok and g3_ok
                        and not too_short and not dup and (has_new or not over_cap))
        reasons = []
        if not in_scope: reasons.append("no in-scope concept")
        if g1 is False: reasons.append("no definitional lead")
        if not g2_ok: reasons.append("low relation density")
        if not g3_ok: reasons.append("no new concept/relation")
        if too_short: reasons.append("too short")
        if dup: reasons.append("near-duplicate")
        if over_cap and not has_new: reasons.append("source cap (relational extra)")
        if accepted:
            seen_concepts.update(new); seen_sigs.add(sig_of(body))
            per_source_counts[rec_src] = per_source_counts.get(rec_src, 0) + 1
            records.append({
                "doc_id": f"{seeds['domain']}:{rec_src}:{title}#{len(records)}",
                "domain": seeds["domain"], "sub_domain": seeds["sub_domain"],
                "source": rec_src, "source_type": job_source_type,
                "title": title, "section": section, "url": url,
                "revision_id": revid, "retrieved_at": NOW, "license": job_license,
                "in_scope": True, "word_count": words, "relation_cues": cues,
                "concepts": sorted(hits), "text": body,
            })
        manifest_rows.append({
            "source": rec_src, "title": title, "section": section,
            "words": words, "relation_cues": cues, "in_scope": in_scope,
            "gate1_def_lead": "" if g1 is None else g1, "gate2_density": g2_ok,
            "gate3_new": len(new), "duplicate": dup, "accepted": accepted,
            "reject_reason": "; ".join(reasons),
        })

    for job in jobs:
        job_license = job["license"]; job_source_type = job["source_type"]
        fetch = fetch_extracts if job["mode"] == "extracts" else fetch_parse
        print(f"  -> {job['name']} ({job['mode']}, {len(job['titles'])} titles)")
        for t in job["titles"]:
            page = fetch(job["api"], t)
            time.sleep(0.3)
            if not page:
                continue
            rtitle, revid, _ts, text = page
            url = (job["api"].replace("/w/api.php", "/wiki/")
                   .replace("/api.php", "/index.php?title=")
                   + urllib.parse.quote(rtitle.replace(" ", "_")))
            pages_meta.append((job["name"], rtitle, revid))
            for (section, body, ok_section) in split_units(text, drop_set):
                if not ok_section:
                    continue
                process_unit(job["name"], rtitle, url, revid, section, body, job["mode"])

    # ---- open HTML / JS-rendered other-layers (fetch:true) ----
    other = seeds.get("other_layers", [])
    chrome = find_chrome(seeds.get("chrome_path"))
    if any(o.get("fetch") and o.get("render") for o in other):
        print("  JS rendering via:",
              chrome if chrome else "NO browser found -> render sources fall back to static")
    for src in other:
        if not src.get("fetch"):
            continue
        job_license = src.get("license", ""); job_source_type = src.get("source_type", "reference")
        if src.get("render") and chrome:
            page = fetch_rendered(src["url"], chrome)
        else:
            page = fetch_html_page(src["url"])
        time.sleep(0.3)
        if not page:
            continue
        rtitle, _r, _t, text = page
        name = src.get("title", rtitle)[:80]
        pages_meta.append((name, rtitle, None))
        print(f"  -> (html) {name}")
        for (section, body, ok_section) in split_units(text, drop_set):
            if not ok_section:
                continue
            process_unit(name, src.get("title", rtitle), src["url"], None,
                         section, body, "html")

    # ---- write outputs ----
    with open(os.path.join(outdir, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if manifest_rows:
        with open(os.path.join(outdir, "units_manifest.csv"), "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
            w.writeheader(); w.writerows(manifest_rows)

    covered = {c for r in records for c in r["concepts"]}
    missing = sorted(set(concepts.values()) - covered)
    total_words = sum(r["word_count"] for r in records)
    cov = (100.0 * len(covered) / len(concepts)) if concepts else 0.0
    by_source = {}
    for r in records:
        by_source.setdefault(r["source"], [0, 0])
        by_source[r["source"]][0] += 1
        by_source[r["source"]][1] += r["word_count"]

    with open(os.path.join(outdir, "coverage_report.md"), "w", encoding="utf-8") as f:
        f.write(f"# Corpus concept coverage - {seeds['sub_domain']}\n\n")
        f.write(f"- Gold-ontology class concepts: **{len(concepts)}**\n")
        f.write(f"- Concepts mentioned in accepted corpus: **{len(covered)}** "
                f"({cov:.1f}%)\n")
        f.write(f"- Accepted text units: **{len(records)}** "
                f"(~{total_words:,} words) from {len(by_source)} sources\n\n")
        f.write("## Accepted units & words per source\n\n| Source | units | words |\n"
                "|---|---|---|\n")
        for s, (u, w) in sorted(by_source.items(), key=lambda kv: -kv[1][0]):
            f.write(f"| {s} | {u} | {w:,} |\n")
        f.write("\n## Uncovered concepts (abstract grouping classes may never "
                "surface as text)\n\n")
        f.write("\n".join(f"- {m}" for m in missing) if missing
                else "_All ontology concepts are covered._\n")
        f.write("\n")

    with open(os.path.join(outdir, "corpus_card.md"), "w", encoding="utf-8") as f:
        b = seeds.get("boundary", {})
        f.write(f"# Corpus Card - {seeds['sub_domain']} ({seeds['domain']})\n\n")
        f.write(f"- **Frozen:** {NOW}\n")
        f.write(f"- **Accepted units:** {len(records)} (~{total_words:,} words) "
                f"from {len(by_source)} auto-scraped sources\n")
        f.write(f"- **Concept coverage:** {len(covered)}/{len(concepts)} "
                f"({cov:.1f}%) of the gold ontology's class concepts\n")
        f.write("- **Acceptance gates:** Gate1 definitional lead (Wikipedia leads); "
                "Gate2 >=1 relation cue / ~150 words; Gate3 new concept OR relational "
                f"(>=2 concepts); min {MIN_UNIT_WORDS} words; near-duplicate removal; "
                "out-of-scope sections dropped.\n\n")
        f.write("## Boundary contract\n\n")
        f.write(f"**In scope:** {b.get('in_scope','')}\n\n")
        f.write(f"**Out of scope:** {b.get('out_of_scope','')}\n\n")
        f.write("## Auto-scraped sources (with frozen revision IDs where applicable)\n\n")
        f.write("| Source | units | words | license |\n|---|---|---|---|\n")
        lic = {}
        for r in records:
            lic[r["source"]] = r["license"]
        for s, (u, w) in sorted(by_source.items(), key=lambda kv: -kv[1][0]):
            f.write(f"| {s} | {u} | {w:,} | {lic.get(s,'')} |\n")
        docs = [s for s in other if not s.get("fetch")]
        if docs:
            f.write("\n## Documented but NOT auto-fetched (ToS / PDF / login - "
                    "consult manually)\n\n")
            f.write("| Type | Title | URL | License | Access note |\n|---|---|---|---|---|\n")
            for s in docs:
                f.write(f"| {s.get('source_type','')} | {s.get('title','')} | "
                        f"{s.get('url','')} | {s.get('license','')} | "
                        f"{s.get('access_note','')} |\n")
        f.write("\n## Cleaning\n\nMediaWiki sources: plain-text extracts or parsed "
                "HTML with markup/tables/infoboxes/refs removed. Open HTML pages: "
                "nav/header/footer/script/table removed, headings preserved. "
                "Out-of-scope sections dropped by name; units gated and de-duplicated.\n")

    print(f"\n[{seeds['sub_domain']}] accepted {len(records)} units "
          f"(~{total_words:,} words) | coverage {len(covered)}/{len(concepts)} "
          f"({cov:.1f}%) | sources: "
          + ", ".join(f"{s}={u}" for s, (u, _w) in by_source.items()))
    if missing:
        print(f"  uncovered ({len(missing)}): {', '.join(missing[:10])}"
              + (" ..." if len(missing) > 10 else ""))


if __name__ == "__main__":
    main()
