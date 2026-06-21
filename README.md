# Python Tutorial: Fetching and Structuring NBER Environment and Energy Economics Papers

This tutorial shows how to reproduce the workflow used to collect NBER Environment and Energy Economics working-paper metadata and turn paper abstracts into structured, analysis-ready notes.

The goal is not to republish the full abstracts. Instead, the workflow uses abstracts as source material to create fields such as research question, findings, value added, data used, and method/design, while keeping links back to the original NBER pages.

## 1. What We Are Building

We will create a dataset where each row is one NBER working paper.

Useful output fields:

```text
rank
paper_number
title
authors
display_date
publication_date
doi
url
pdf_url
research_question
main_findings
literature_value_added
data_used
method_or_design
abstract_word_count
fetch_status
```

This structure is especially useful if you later want to build a network graph:

```text
paper -> author
paper -> method
paper -> data source
paper -> research question/topic
paper -> policy domain
```

## 2. Libraries

This version uses only Python standard-library modules.

```python
import csv
import html
import json
import math
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
```

If you prefer, you can use `requests`, `beautifulsoup4`, and `pandas`, but the standard library is enough.

## 3. Source URLs

The visible NBER page mounts a search/listing widget. In the page HTML, the useful endpoint is an NBER JSON API.

```python
BASE = "https://www.nber.org"

LISTING_URL = (
    "https://www.nber.org/programs-projects/programs-working-groups/"
    "environment-and-energy-economics?page=1&perPage=50"
)

API_BASE = (
    BASE
    + "/api/v1/generic_listing/nid/11636/contentType/working_paper/search/contentType"
)

PER_PAGE = 100
```

The API returns JSON records with paper titles, dates, partial abstracts, and paper URLs such as `/papers/w35317`.

## 4. Fetch Helpers

```python
def fetch_text(url: str, timeout: int = 45) -> str:
    req = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; research data fetch)"}
    )
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict:
    return json.loads(fetch_text(url))
```

A custom user agent is polite and helps avoid being treated like a broken client.

## 5. Fetch All Listing Records

First, fetch page 1 to learn the total number of results. Then page through the API.

```python
def fetch_all_listing_items() -> tuple[list[dict], int]:
    first_url = f"{API_BASE}?page=1&perPage={PER_PAGE}"
    first_page = fetch_json(first_url)

    total = int(first_page.get("totalResults", 0))
    pages = max(1, math.ceil(total / PER_PAGE))

    items = list(first_page.get("results", []))

    for page in range(2, pages + 1):
        url = f"{API_BASE}?page={page}&perPage={PER_PAGE}"
        data = fetch_json(url)
        items.extend(data.get("results", []))
        time.sleep(0.05)

    seen = set()
    deduped = []

    for item in items:
        paper_url = item.get("url", "")
        if not paper_url or paper_url in seen:
            continue
        seen.add(paper_url)
        deduped.append(item)

    return deduped, total
```

## 6. Parse Paper Pages

The listing API gives a useful starting record, but individual paper pages contain cleaner citation metadata and fuller abstract text.

```python
def clean_html(fragment: str | None) -> str:
    if not fragment:
        return ""

    fragment = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.I | re.S)
    fragment = re.sub(r"<style\b.*?</style>", " ", fragment, flags=re.I | re.S)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)

    return re.sub(r"\s+", " ", fragment).strip()


def meta_all(page: str, name: str) -> list[str]:
    pattern = rf'<meta\s+name="{re.escape(name)}"\s+content="(.*?)"\s*/?>'
    return [
        html.unescape(match).strip()
        for match in re.findall(pattern, page, flags=re.I | re.S)
    ]


def meta_one(page: str, name: str) -> str:
    values = meta_all(page, name)
    return values[0] if values else ""


def extract_abstract(page: str) -> str:
    match = re.search(
        r'<div class="page-header__intro page-header__intro--centered">\s*'
        r'<div class="page-header__intro-inner">\s*<p>\s*(.*?)\s*</p>',
        page,
        flags=re.I | re.S,
    )

    return clean_html(match.group(1)) if match else ""
```

Metadata fields available on NBER paper pages often include:

```text
citation_title
citation_author
citation_publication_date
citation_doi
citation_technical_report_number
citation_pdf_url
```

## 7. Turn Abstracts into Structured Notes

For a lightweight tutorial, we can use rule-based extraction. This is not as nuanced as reading every paper manually, but it gives useful first-pass fields.

```python
QUESTION_CUES = re.compile(
    r"\b(study|studies|examine|examines|investigate|investigates|ask|asks|"
    r"estimate|estimates|measure|measures|evaluate|evaluates|analy[sz]e|"
    r"analy[sz]es|explore|explores|quantif(?:y|ies)|compare|compares|"
    r"develop|develops|provide|provides|revisit|revisits|document|documents|"
    r"assess|assesses|test|tests|focus(?:es)?|consider|considers)\b",
    re.I,
)

FINDING_CUES = re.compile(
    r"\b(find|finds|finding|findings|found|show|shows|result|results|evidence|"
    r"indicate|indicates|suggest|suggests|imply|implies|document|documents|"
    r"demonstrate|demonstrates|conclude|concludes|reveal|reveals)\b",
    re.I,
)

VALUE_CUES = re.compile(
    r"\b(first|novel|new|fill(?:s)? (?:this )?gap|gap|contribut(?:e|es|ion)|"
    r"provide(?:s)? evidence|little evidence|scarce|limited|introduce|"
    r"introduces|develop|develops|extend|extends|advance|advances|address|"
    r"addresses|revisit|revisits|challenge|challenges|data product)\b",
    re.I,
)

DATA_CUES = re.compile(
    r"\b((?<!-)using|data|dataset|datasets|panel|survey|administrative|census|"
    r"satellite|experiment|rct|field experiment|microdata|records|transactions|"
    r"scanner|monitor|monitors|sample|observations|measurements|linked|"
    r"confidential|proprietary|registry|interviews|surveyed)\b",
    re.I,
)

METHOD_CUES = re.compile(
    r"\b(model|instrument|event[- ]study|difference[- ]in[- ]differences|"
    r"synthetic|experiment|rct|regression|simulation|calibrat|estimate|"
    r"structural|causal|counterfactual|machine learning|randomiz|panel)\b",
    re.I,
)
```

Split the abstract into sentences:

```python
def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", text)
    return [piece.strip() for piece in pieces if len(piece.strip()) > 20]


def choose_sentences(sentences: list[str], pattern: re.Pattern, limit: int = 3) -> list[str]:
    matches = [sentence for sentence in sentences if pattern.search(sentence)]
    return matches[:limit]
```

Create compact notes. This example avoids storing full abstract text in the final dataset.

```python
def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z][A-Za-z0-9'’.-]*|\d+(?:[.,]\d+)*%?", text))


def compact_note(label: str, sentences: list[str], missing: str) -> str:
    if not sentences:
        return missing

    text = " ".join(sentences)
    text = re.sub(r"\s+", " ", text).strip()

    # Keep this compact and nonverbatim. For better summaries, use an LLM
    # or a more careful NLP pipeline over this selected source text.
    words = text.split()
    shortened = " ".join(words[:45])
    if len(words) > 45:
        shortened += " ..."

    return f"{label}: {shortened}"


def analyze_abstract(title: str, abstract: str) -> dict:
    sentences = split_sentences(abstract)

    question_sentences = choose_sentences(sentences[:4], QUESTION_CUES, limit=2)
    finding_sentences = choose_sentences(sentences, FINDING_CUES, limit=3)
    value_sentences = choose_sentences(sentences, VALUE_CUES, limit=3)
    data_sentences = choose_sentences(sentences, DATA_CUES, limit=3)
    method_sentences = choose_sentences(sentences, METHOD_CUES, limit=3)

    return {
        "research_question": compact_note(
            "Research question or focus",
            question_sentences,
            f"Examines: {title}",
        ),
        "main_findings": compact_note(
            "Main findings",
            finding_sentences,
            "Not clearly stated in the abstract.",
        ),
        "literature_value_added": compact_note(
            "Contribution/value added",
            value_sentences,
            "Not explicitly discussed in the abstract.",
        ),
        "data_used": compact_note(
            "Data used",
            data_sentences,
            "Not explicitly discussed in the abstract.",
        ),
        "method_or_design": compact_note(
            "Method or design",
            method_sentences,
            "Not explicitly discussed in the abstract.",
        ),
        "abstract_word_count": word_count(abstract),
    }
```

## 8. Fetch One Paper Record

```python
def listing_authors(item: dict) -> str:
    authors = item.get("authors") or []
    return "; ".join(clean_html(author) for author in authors)


def fetch_paper(item_with_rank: tuple[int, dict]) -> tuple[dict | None, dict | None]:
    rank, item = item_with_rank
    url = BASE + item["url"]

    try:
        page = fetch_text(url)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return None, {
            "rank": rank,
            "title": item.get("title", ""),
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
        }

    title = meta_one(page, "citation_title") or item.get("title", "")
    abstract = extract_abstract(page) or clean_html(item.get("abstract", ""))
    analysis = analyze_abstract(title, abstract)

    row = {
        "rank": rank,
        "paper_number": meta_one(page, "citation_technical_report_number")
        or item["url"].split("/")[-1],
        "title": title,
        "authors": "; ".join(meta_all(page, "citation_author")) or listing_authors(item),
        "display_date": item.get("displaydate", ""),
        "publication_date": meta_one(page, "citation_publication_date"),
        "doi": meta_one(page, "citation_doi"),
        "url": url,
        "pdf_url": meta_one(page, "citation_pdf_url"),
        **analysis,
        "fetch_status": "ok" if abstract else "ok_no_abstract_found",
    }

    return row, None
```

## 9. Run the Full Crawl

```python
def run_pipeline(max_workers: int = 8) -> tuple[list[dict], list[dict], int]:
    items, listed_total = fetch_all_listing_items()
    print(f"NBER reported {listed_total} working-paper results.")
    print(f"Unique paper URLs found: {len(items)}")

    rows = []
    errors = []
    jobs = list(enumerate(items, start=1))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_paper, job) for job in jobs]

        for completed, future in enumerate(as_completed(futures), start=1):
            row, error = future.result()

            if row:
                rows.append(row)
            if error:
                errors.append(error)

            if completed % 100 == 0 or completed == len(futures):
                print(f"Processed {completed}/{len(futures)} paper pages")

    rows.sort(key=lambda row: row["rank"])
    errors.sort(key=lambda error: error["rank"])

    return rows, errors, listed_total
```

## 10. Export CSV, JSON, and Markdown

```python
OUTPUTS = Path("outputs")
OUTPUTS.mkdir(exist_ok=True)

CSV_PATH = OUTPUTS / "nber_environment_energy_structured.csv"
JSON_PATH = OUTPUTS / "nber_environment_energy_structured.json"
MD_PATH = OUTPUTS / "nber_environment_energy_structured.md"
ERROR_PATH = OUTPUTS / "nber_environment_energy_errors.json"


def write_outputs(rows: list[dict], errors: list[dict], listed_total: int) -> None:
    JSON_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    ERROR_PATH.write_text(json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")

    fieldnames = list(rows[0].keys())

    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# NBER Environment and Energy Economics Working Papers",
        "",
        f"Source listing: {LISTING_URL}",
        f"NBER reported working-paper results: {listed_total}",
        f"Fetched paper pages included: {len(rows)}",
        f"Skipped paper pages: {len(errors)}",
        "",
        "Fields are structured notes generated from paper abstracts.",
        "Use each NBER link for the original abstract text.",
        "",
    ]

    for row in rows:
        lines.append(f"## {row['rank']}. {row['title']}")
        lines.append("")
        lines.append(f"- Authors: {row['authors']}")
        lines.append(f"- Date: {row['display_date']}")
        lines.append(f"- NBER: {row['url']}")
        lines.append(f"- DOI: {row['doi']}")
        lines.append(f"- Research question: {row['research_question']}")
        lines.append(f"- Main findings: {row['main_findings']}")
        lines.append(f"- Literature value added: {row['literature_value_added']}")
        lines.append(f"- Data used: {row['data_used']}")
        lines.append(f"- Method/design: {row['method_or_design']}")
        lines.append("")

    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
```

Run it:

```python
if __name__ == "__main__":
    rows, errors, listed_total = run_pipeline(max_workers=8)
    write_outputs(rows, errors, listed_total)
```

## 11. Quality Checks

After running, verify row counts and error counts.

```python
print(len(rows))
print(len(errors))
print(rows[0]["title"])
print(rows[0]["research_question"])
```

You can also inspect missing fields:

```python
missing_data = [
    row for row in rows
    if row["data_used"] == "Not explicitly discussed in the abstract."
]

print(len(missing_data))
```

## 12. Turning This into a Network Dataset

Once the structured table exists, create edge lists for network visualization.

Example: paper-author edges.

```python
paper_author_edges = []

for row in rows:
    paper_id = row["paper_number"]
    authors = [author.strip() for author in row["authors"].split(";") if author.strip()]

    for author in authors:
        paper_author_edges.append({
            "source": paper_id,
            "target": author,
            "edge_type": "authored_by",
        })
```

Example: paper-topic edges from simple keyword matching.

```python
TOPIC_KEYWORDS = {
    "air pollution": ["air pollution", "pm2.5", "particulate", "ozone"],
    "climate policy": ["carbon tax", "climate policy", "emissions", "carbon"],
    "energy": ["electricity", "energy", "natural gas", "oil"],
    "water": ["water", "drinking water", "flood"],
    "transportation": ["electric vehicle", "ev", "fuel economy", "charging"],
}

paper_topic_edges = []

for row in rows:
    text = " ".join([
        row["title"],
        row["research_question"],
        row["main_findings"],
        row["data_used"],
        row["method_or_design"],
    ]).lower()

    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            paper_topic_edges.append({
                "source": row["paper_number"],
                "target": topic,
                "edge_type": "has_topic",
            })
```

Then export edges:

```python
with open("outputs/nber_edges.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["source", "target", "edge_type"])
    writer.writeheader()
    writer.writerows(paper_author_edges + paper_topic_edges)
```

## 13. Practical Notes

Respect the source site:

- Keep request rates reasonable.
- Keep source URLs and DOIs in your dataset.
- Do not redistribute bulk full abstract text unless you have permission.
- For public outputs, prefer structured notes, summaries, keywords, and source links.

Improve the analysis:

- Use an LLM or NLP model to produce higher-quality structured summaries.
- Add named-entity recognition for places, policies, pollutants, datasets, and institutions.
- Create coauthor and topic co-occurrence networks.
- Use embeddings to connect papers by semantic similarity.


