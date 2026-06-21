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
MAX_WORKERS = 8

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
OUTPUTS = ROOT / "outputs"

# Keep the same deliverable filenames from the previous runs.
CSV_PATH = OUTPUTS / "nber_environment_energy_working_papers_page1_summaries.csv"
JSON_PATH = OUTPUTS / "nber_environment_energy_working_papers_page1_summaries.json"
MD_PATH = OUTPUTS / "nber_environment_energy_working_papers_page1_summaries.md"
ERROR_PATH = WORK / "nber_environment_energy_working_papers_structured_errors.json"
SAFE_RAW_PATH = WORK / "nber_environment_energy_working_papers_structured_rows.json"

STOPWORDS = {
    "a", "about", "above", "across", "after", "against", "all", "also", "am",
    "among", "an", "and", "any", "are", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can", "could",
    "did", "do", "does", "doing", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "itself", "me", "more", "most", "my", "no",
    "nor", "not", "of", "off", "on", "once", "only", "or", "other", "our",
    "ours", "out", "over", "own", "same", "she", "should", "so", "some",
    "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "will", "with", "would",
    "you", "your", "using", "use", "uses", "used", "study", "studies", "paper",
    "papers", "find", "finds", "found", "show", "shows", "result", "results",
    "estimate", "estimates", "estimated", "analysis", "model", "models",
}

GENERIC_TERMS = STOPWORDS | {
    "abstract", "account", "accounting", "accounts", "advance", "advances",
    "affect", "affected", "affecting", "approximately", "approach",
    "associated", "available", "based", "benefits", "central", "change",
    "changes", "combine", "combines", "compared", "concerns", "context",
    "current", "different", "effects", "evidence", "framework", "general",
    "important", "increase", "increased", "increases", "large", "larger",
    "literature", "main", "major", "mechanism", "mechanisms", "new",
    "novel", "outcomes", "policy", "policies", "provide", "provides",
    "related", "relationship", "relative", "reported", "requires",
    "response", "responses", "significant", "substantial", "substantially",
    "suggest", "suggests", "using", "variation",
    "adhering", "alongside", "attention", "balancing", "careful", "condition",
    "conditions", "country-specific", "effective", "ideological", "objective",
    "objectives", "prescription", "prescriptions", "pursue", "pursues",
    "pursuing", "rather", "traditional",
    "financed", "imported", "moderate", "optimal",
}

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
NUMBER_RE = re.compile(
    r"(?<!\w)(?:\$?\d+(?:,\d{3})*(?:\.\d+)?(?:–|-| to )?\d*(?:,\d{3})*"
    r"(?:\.\d+)?\s?(?:%|percent|percentage points|pp|million|billion|trillion|"
    r"km²|km2|μg/m³|tons|TWh|years|countries|states|cities|counties|firms|"
    r"households|policies|observations|records|transactions|papers|patents)?|"
    r"\b\d{4}(?:–|-| to )\d{2,4}\b|\b\d{4}\b)",
    re.I,
)
YEAR_CONTEXT_RE = re.compile(
    r"\b(?:from|during|between|over|in)\s+\d{4}(?:\s?(?:–|-|to)\s?\d{2,4})?\b",
    re.I,
)


def fetch_text(url: str, timeout: int = 45) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Codex data fetch)"})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict:
    return json.loads(fetch_text(url))


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
    return [html.unescape(m).strip() for m in re.findall(pattern, page, flags=re.I | re.S)]


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


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", text)
    return [piece.strip() for piece in pieces if len(piece.strip()) > 20]


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9'’.-]*|\d+(?:[.,]\d+)*%?", text)


def clean_phrase(phrase: str) -> str:
    phrase = re.sub(r"\s+", " ", phrase).strip(" -–:;,.()[]{}")
    phrase = re.sub(r"^(and|or|with|using|from|for|the|a|an)\s+", "", phrase, flags=re.I)
    phrase = re.sub(r"\s+(and|or|with|using|from|for|the|a|an)$", "", phrase, flags=re.I)
    return phrase.strip()


def key_phrases(text: str, max_phrases: int = 6) -> list[str]:
    candidates: list[str] = []
    single_word_fallbacks: list[str] = []
    chunks: list[list[str]] = []
    current: list[str] = []
    for token in words(text):
        lower = token.lower().strip("'’.-")
        if lower in GENERIC_TERMS or len(lower) < 3:
            if current:
                chunks.append(current)
                current = []
            continue
        current.append(token)
    if current:
        chunks.append(current)

    for chunk in chunks:
        if len(chunk) <= 3:
            phrase = clean_phrase(" ".join(chunk))
            if len(chunk) >= 2 and phrase:
                candidates.append(phrase)
            elif phrase and (re.search(r"\d", phrase) or phrase.isupper()):
                single_word_fallbacks.append(phrase)
            continue
        for size in (3, 2):
            for i in range(0, len(chunk) - size + 1):
                phrase = clean_phrase(" ".join(chunk[i : i + size]))
                if not phrase:
                    continue
                lower_words = [part.lower().strip("'’.-") for part in phrase.split()]
                if all(part in GENERIC_TERMS or len(part) < 3 for part in lower_words):
                    continue
                candidates.append(phrase)

    selected: list[str] = []
    seen = set()
    for phrase in candidates + single_word_fallbacks:
        normalized = phrase.lower()
        if normalized in seen:
            continue
        if any(normalized in existing.lower() or existing.lower() in normalized for existing in selected):
            continue
        selected.append(phrase)
        seen.add(normalized)
        if len(selected) >= max_phrases:
            break
    return selected


def key_numbers(text: str, max_numbers: int = 8) -> list[str]:
    numbers = [match.group(0).strip() for match in NUMBER_RE.finditer(text)]
    selected: list[str] = []
    seen = set()
    for number in numbers:
        normalized = number.lower()
        if normalized not in seen:
            selected.append(number)
            seen.add(normalized)
        if len(selected) >= max_numbers:
            break
    return selected


def choose_sentences(sentences: list[str], pattern: re.Pattern[str], limit: int = 3) -> list[str]:
    matches = [sentence for sentence in sentences if pattern.search(sentence)]
    return matches[:limit]


def choose_sentences_with_followups(
    sentences: list[str], pattern: re.Pattern[str], limit: int = 4
) -> list[str]:
    selected: list[str] = []
    used: set[int] = set()
    for index, sentence in enumerate(sentences):
        if not pattern.search(sentence):
            continue
        if index not in used:
            selected.append(sentence)
            used.add(index)
        next_index = index + 1
        if next_index < len(sentences) and next_index not in used:
            next_sentence = sentences[next_index]
            if NUMBER_RE.search(next_sentence) or re.match(r"^(For|Relative|These|This|The)\b", next_sentence):
                selected.append(next_sentence)
                used.add(next_index)
        if len(selected) >= limit:
            break
    return selected[:limit]


def choose_data_sentences(sentences: list[str], limit: int = 4) -> list[str]:
    selected: list[str] = []
    for sentence in sentences:
        has_data_cue = DATA_CUES.search(sentence)
        has_time_context = YEAR_CONTEXT_RE.search(sentence)
        if has_data_cue or has_time_context:
            selected.append(sentence)
        if len(selected) >= limit:
            break
    return selected


def phrase_note(label: str, source_text: str, missing: str) -> str:
    phrases = key_phrases(source_text, max_phrases=6)
    numbers = key_numbers(source_text, max_numbers=8)
    if not phrases and not numbers:
        return missing
    parts = []
    if phrases:
        parts.append(f"{label}: " + "; ".join(phrases))
    if numbers:
        parts.append("quantitative/time-scale details: " + "; ".join(numbers))
    return ". ".join(parts) + "."


def research_question(title: str, abstract: str, sentences: list[str]) -> str:
    if title.endswith("?"):
        lead = f"Asks: {title}"
    else:
        lead = f"Examines: {title}"
    question_sentences = choose_sentences(sentences[:4], QUESTION_CUES, limit=2)
    if not question_sentences:
        question_sentences = sentences[:2]
    context = " ".join(question_sentences)
    phrases = key_phrases(context, max_phrases=5)
    if phrases:
        return f"{lead}. Abstract focus: " + "; ".join(phrases) + "."
    if abstract:
        return f"{lead}. Abstract gives the motivating context but no compact research-question wording was detected."
    return f"{lead}. No abstract text was found."


def analyze_abstract(title: str, abstract: str) -> dict:
    sentences = split_sentences(abstract)
    finding_text = " ".join(choose_sentences_with_followups(sentences, FINDING_CUES, limit=5))
    value_text = " ".join(choose_sentences(sentences, VALUE_CUES, limit=3))
    data_text = " ".join(choose_data_sentences(sentences, limit=4))
    method_text = " ".join(choose_sentences(sentences, METHOD_CUES, limit=3))

    value_cues = sorted({match.group(0).lower() for match in VALUE_CUES.finditer(value_text)})[:8]
    value_note = phrase_note(
        "Contribution/value-added signals",
        value_text,
        "Not explicitly discussed in the abstract.",
    )
    if value_cues and value_note != "Not explicitly discussed in the abstract.":
        value_note += " Novelty/value cues: " + "; ".join(value_cues) + "."

    return {
        "research_question": research_question(title, abstract, sentences),
        "main_findings": phrase_note(
            "Reported findings concern",
            finding_text,
            "Not clearly stated in the abstract.",
        ),
        "literature_value_added": value_note,
        "data_used": phrase_note(
            "Data/evidence mentioned",
            data_text,
            "Not explicitly discussed in the abstract.",
        ),
        "method_or_design": phrase_note(
            "Method/design mentioned",
            method_text,
            "Not explicitly discussed in the abstract.",
        ),
        "abstract_word_count": len(words(abstract)),
    }


def listing_authors(item: dict) -> str:
    return "; ".join(clean_html(author) for author in item.get("authors") or [])


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


def fetch_paper(item_with_rank: tuple[int, dict]) -> tuple[dict | None, dict | None]:
    listing_rank, item = item_with_rank
    url = BASE + item["url"]
    try:
        page = fetch_text(url)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return None, {
            "listing_rank": listing_rank,
            "title": item.get("title", ""),
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
        }

    title = meta_one(page, "citation_title") or item.get("title", "")
    abstract = extract_abstract(page) or clean_html(item.get("abstract", ""))
    analysis = analyze_abstract(title, abstract)

    row = {
        "rank": listing_rank,
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


def write_outputs(rows: list[dict], errors: list[dict], listed_total: int) -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    JSON_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    SAFE_RAW_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    ERROR_PATH.write_text(json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")

    fieldnames = [
        "rank",
        "paper_number",
        "title",
        "authors",
        "display_date",
        "publication_date",
        "doi",
        "url",
        "pdf_url",
        "research_question",
        "main_findings",
        "literature_value_added",
        "data_used",
        "method_or_design",
        "abstract_word_count",
        "fetch_status",
    ]
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
        (
            "Note: The fields below are structured, nonverbatim notes generated from "
            "the abstracts. Use the NBER link for the original abstract text."
        ),
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


def main() -> None:
    items, listed_total = fetch_all_listing_items()
    print(f"NBER reported {listed_total} working-paper results; {len(items)} unique URLs found")

    rows: list[dict] = []
    errors: list[dict] = []
    jobs = list(enumerate(items, start=1))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_paper, job) for job in jobs]
        for completed, future in enumerate(as_completed(futures), start=1):
            row, error = future.result()
            if row:
                rows.append(row)
            if error:
                errors.append(error)
            if completed % 100 == 0 or completed == len(futures):
                print(f"Processed {completed}/{len(futures)} pages")

    rows.sort(key=lambda row: row["rank"])
    errors.sort(key=lambda error: error["listing_rank"])
    write_outputs(rows, errors, listed_total)
    print(f"Wrote {len(rows)} structured rows to {CSV_PATH}")
    print(f"Wrote {len(errors)} skipped-page errors to {ERROR_PATH}")


if __name__ == "__main__":
    main()
