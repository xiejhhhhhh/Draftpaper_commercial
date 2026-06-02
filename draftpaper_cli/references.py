from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from html import escape
from html import unescape
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


REFERENCE_OUTPUTS = [
    "references/library.bib",
    "references/literature_items.json",
    "references/search_queries.json",
    "references/citation_evidence.csv",
    "references/literature_review_notes.md",
    "references/literature_summaries/index.html",
]

MAX_REFERENCE_ITEMS = 30
CONTEXT_MINIMUM_ITEMS = 5
RECENT_YEAR_CUTOFF = 2021
OLD_YEAR_CUTOFF = 2011
RECENT_TARGET_RATIO = 0.60


def extract_year(raw_date: str | int | None) -> str:
    match = re.search(r"(19|20)\d{2}", str(raw_date or ""))
    return match.group(0) if match else "n.d."


def citation_key(item: dict[str, Any], index: int) -> str:
    authors = item.get("authors") or []
    first_author = str(authors[0]).split()[-1] if authors else "source"
    year = extract_year(item.get("year"))
    title_word_match = re.search(r"[A-Za-z0-9]+", item.get("title", "paper"))
    title_word = title_word_match.group(0) if title_word_match else "paper"
    raw_key = f"{first_author}{year}{title_word}{index + 1}"
    return re.sub(r"[^A-Za-z0-9_:-]", "", raw_key)


def _escape_bibtex_value(value: Any) -> str:
    clean = unescape(str(value or "")).replace("\xa0", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in clean)


def normalize_reference_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    title = " ".join(str(item.get("title") or f"Untitled source {index + 1}").split())
    authors = [str(author).strip() for author in (item.get("authors") or []) if str(author).strip()]
    search_context = str(item.get("search_context") or "idea").strip().lower()
    search_contexts = [str(context).strip().lower() for context in (item.get("search_contexts") or []) if str(context).strip()]
    if search_context and search_context not in search_contexts:
        search_contexts.append(search_context)
    normalized = {
        "title": title,
        "authors": authors,
        "year": extract_year(item.get("year")),
        "doi": str(item.get("doi") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "abstract": " ".join(str(item.get("abstract") or "").split()),
        "venue": str(item.get("venue") or item.get("publication") or "").strip(),
        "publication": str(item.get("publication") or item.get("venue") or "").strip(),
        "citation_count": int(item.get("citation_count") or item.get("citationCount") or 0),
        "source": str(item.get("source") or "unknown").strip(),
        "pdf_url": str(item.get("pdf_url") or item.get("openAccessPdf") or "").strip(),
        "pdf_path": str(item.get("pdf_path") or "").strip(),
        "pdf_text_excerpt": str(item.get("pdf_text_excerpt") or "").strip(),
        "pdf_read_status": str(item.get("pdf_read_status") or "").strip(),
        "search_context": search_context,
        "search_contexts": search_contexts or [search_context or "idea"],
        "search_query": str(item.get("search_query") or "").strip(),
        "search_queries": [str(query).strip() for query in (item.get("search_queries") or []) if str(query).strip()],
    }
    normalized["bibtex_key"] = str(item.get("bibtex_key") or citation_key(normalized, index))
    normalized["evidence_notes"] = item.get("evidence_notes") or infer_evidence_summary(normalized)
    return normalized


def normalize_reference_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        key = (str(item.get("doi") or "") or re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()).lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(normalize_reference_item(item, len(normalized)))
    return normalized


def tokenize_for_relevance(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "using", "based", "from", "this", "that",
        "study", "research", "paper", "method", "methods", "model", "models",
        "data", "analysis", "classification", "framework",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", (text or "").lower())
        if token not in stopwords
    }


def rank_text_to_score(rank_text: str) -> float:
    rank = (rank_text or "").strip().upper()
    if rank in {"TOP", "T", "Q1", "A+", "AA", "A*"}:
        return 1.0
    if rank in {"A", "Q2"}:
        return 0.85
    if rank in {"B+", "B", "Q3"}:
        return 0.65
    if rank in {"C", "Q4"}:
        return 0.4
    if rank in {"D", "E"}:
        return 0.2
    return 0.0


def infer_journal_score(publication: str) -> tuple[float, list[str]]:
    """Assign a conservative journal authority score without requiring paid rank APIs."""
    pub = (publication or "").lower()
    if not pub or pub == "arxiv":
        return (0.25 if pub == "arxiv" else 0.0), (["preprint:arXiv"] if pub == "arxiv" else [])
    top_patterns = {
        "nature": 1.0,
        "science": 1.0,
        "astrophysical journal": 0.9,
        "monthly notices": 0.9,
        "astronomy & astrophysics": 0.9,
        "astronomy and astrophysics": 0.9,
        "research in astronomy and astrophysics": 0.75,
        "publications of the astronomical society": 0.75,
        "astronomical journal": 0.85,
    }
    for pattern, score in top_patterns.items():
        if pattern in pub:
            return score, [f"heuristic:{pattern}"]
    if any(term in pub for term in ["journal", "transactions", "proceedings"]):
        return 0.45, ["heuristic:scholarly-venue"]
    return 0.2, ["heuristic:unknown-venue"]


def weight_literature_items(items: list[dict[str, Any]], idea: str = "", target_journal: str = "") -> list[dict[str, Any]]:
    """Rank literature by topic relevance, citation authority, and journal authority."""
    idea_terms = tokenize_for_relevance(idea)
    weighted = []
    for item in items:
        item_terms = tokenize_for_relevance(
            " ".join([str(item.get("title") or ""), str(item.get("abstract") or ""), str(item.get("publication") or "")])
        )
        overlap = len(idea_terms & item_terms)
        relevance = overlap / max(len(idea_terms), 1)
        citation_count = int(item.get("citation_count") or 0)
        citation_authority = min(1.0, citation_count / 300.0)
        journal_score, journal_labels = infer_journal_score(str(item.get("publication") or ""))
        venue_bonus = 0.08 if target_journal and target_journal.lower() in str(item.get("publication") or "").lower() else 0.0
        authority = (0.45 * citation_authority) + (0.55 * journal_score)
        citation_weight = min(1.0, (0.55 * relevance) + (0.30 * authority) + venue_bonus + 0.10)
        copied = dict(item)
        copied["relevance_score"] = round(relevance, 3)
        copied["authority_score"] = round(authority, 3)
        copied["citation_authority_score"] = round(citation_authority, 3)
        copied["journal_score"] = round(journal_score, 3)
        copied["journal_rank_labels"] = journal_labels
        copied["citation_weight"] = round(citation_weight, 3)
        weighted.append(copied)
    weighted.sort(key=lambda entry: (entry.get("citation_weight", 0), entry.get("citation_count", 0)), reverse=True)
    return weighted


def has_sufficient_metadata_or_pdf(item: dict[str, Any]) -> bool:
    if item.get("pdf_url") or item.get("pdf_path"):
        return True
    return bool(
        item.get("title")
        and item.get("authors")
        and item.get("year")
        and item.get("year") != "n.d."
        and item.get("abstract")
    )


def _extract_pdf_text_from_bytes(content: bytes, *, max_pages: int = 5, max_chars: int = 5000) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception:
        return ""
    parts = []
    for page in reader.pages[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
        if sum(len(part) for part in parts) >= max_chars:
            break
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:max_chars]


def _extract_pdf_text_from_path(path: str, *, max_pages: int = 5, max_chars: int = 5000) -> str:
    try:
        content = Path(path).read_bytes()
    except Exception:
        return ""
    return _extract_pdf_text_from_bytes(content, max_pages=max_pages, max_chars=max_chars)


def _extract_pdf_text_from_url(url: str, *, timeout: int = 8, max_bytes: int = 8_000_000) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return ""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "DraftPaper CLI literature metadata reader"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read(max_bytes + 1)
    except Exception:
        return ""
    if len(content) > max_bytes:
        return ""
    return _extract_pdf_text_from_bytes(content)


def enrich_pdf_text(item: dict[str, Any]) -> dict[str, Any]:
    copied = dict(item)
    if copied.get("pdf_text_excerpt"):
        return copied
    text = ""
    if copied.get("pdf_path"):
        text = _extract_pdf_text_from_path(str(copied.get("pdf_path") or ""))
    if not text and copied.get("pdf_url"):
        text = _extract_pdf_text_from_url(str(copied.get("pdf_url") or ""))
    if text:
        copied["pdf_text_excerpt"] = text
        if not copied.get("abstract"):
            copied["abstract"] = text[:1200]
        copied["pdf_read_status"] = "quick_read"
    elif copied.get("pdf_url") or copied.get("pdf_path"):
        copied["pdf_read_status"] = "pdf_available_unreadable"
    return copied


def has_readable_evidence(item: dict[str, Any]) -> bool:
    return bool(item.get("abstract") or item.get("pdf_text_excerpt"))


def _year_int(item: dict[str, Any]) -> int | None:
    try:
        return int(str(item.get("year") or ""))
    except ValueError:
        return None


def _rank_for_context(items: list[dict[str, Any]], context: str, query: str, target_journal: str) -> list[dict[str, Any]]:
    weighted = weight_literature_items(items, query, target_journal)
    ranked = []
    for item in weighted:
        copied = dict(item)
        copied["context_rank_score"] = copied.get("citation_weight", 0)
        copied["search_context"] = context
        copied["search_query"] = copied.get("search_query") or query
        ranked.append(copied)
    return ranked


def _dedupe_ranked(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    by_key: dict[str, dict[str, Any]] = {}
    deduped = []
    for item in items:
        key = (str(item.get("doi") or "") or re.sub(r"[^a-z0-9]+", " ", str(item.get("title") or "").lower()).strip()).lower()
        if not key:
            continue
        if key in seen:
            existing = by_key[key]
            contexts = list(existing.get("search_contexts") or [existing.get("search_context") or "idea"])
            for context in item.get("search_contexts") or [item.get("search_context") or "idea"]:
                clean = str(context).strip().lower()
                if clean and clean not in contexts:
                    contexts.append(clean)
            queries = list(existing.get("search_queries") or [])
            for query in [existing.get("search_query"), item.get("search_query"), *(item.get("search_queries") or [])]:
                clean_query = str(query or "").strip()
                if clean_query and clean_query not in queries:
                    queries.append(clean_query)
            existing["search_contexts"] = contexts
            existing["search_queries"] = queries
            continue
        seen.add(key)
        by_key[key] = item
        deduped.append(item)
    return deduped


def _apply_age_preference(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(candidates) < limit:
        return candidates[:limit]
    not_too_old = [item for item in candidates if (_year_int(item) or 9999) >= OLD_YEAR_CUTOFF]
    pool = not_too_old if len(not_too_old) >= limit else candidates
    recent = [item for item in pool if (_year_int(item) or 0) >= RECENT_YEAR_CUTOFF]
    other = [item for item in pool if item not in recent]
    target_recent = int(limit * RECENT_TARGET_RATIO + 0.999)
    if len(recent) >= target_recent:
        selected = recent[:target_recent]
        selected.extend(item for item in pool if item not in selected)
        return selected[:limit]
    return pool[:limit]


def select_references_by_context(
    items: list[dict[str, Any]],
    *,
    project_text: str,
    target_journal: str,
    limit: int = MAX_REFERENCE_ITEMS,
) -> list[dict[str, Any]]:
    normalized = [
        normalize_reference_item(item, index)
        for index, item in enumerate(items or [])
        if str(item.get("title") or "").strip()
    ]
    normalized = [item for item in normalized if has_sufficient_metadata_or_pdf(item)]
    by_context: dict[str, list[dict[str, Any]]] = {"idea": [], "data": [], "methods": []}
    for item in normalized:
        context = str(item.get("search_context") or "idea").lower()
        if context not in by_context:
            context = "idea"
        by_context[context].append(item)
    ranked_by_context = {
        context: _rank_for_context(
            context_items,
            context,
            " ".join([project_text, " ".join(str(item.get("search_query") or "") for item in context_items)]),
            target_journal,
        )
        for context, context_items in by_context.items()
    }
    selected = []
    for context in ["data", "methods"]:
        for item in ranked_by_context[context][:CONTEXT_MINIMUM_ITEMS]:
            selected.append(item)
    remainder = _dedupe_ranked(
        selected
        + ranked_by_context["idea"]
        + ranked_by_context["data"][CONTEXT_MINIMUM_ITEMS:]
        + ranked_by_context["methods"][CONTEXT_MINIMUM_ITEMS:]
    )
    return _apply_age_preference(remainder, limit)


def generate_bibtex(items: list[dict[str, Any]]) -> str:
    entries = []
    for item in items:
        entry_type = "article" if item.get("publication") else "misc"
        fields = {
            "title": item.get("title", ""),
            "author": " and ".join(item.get("authors") or []) or "Unknown Author",
            "year": item.get("year", "n.d."),
            "journal": item.get("publication", ""),
            "doi": item.get("doi", ""),
            "url": item.get("url", ""),
        }
        populated_fields = [
            f"  {name} = {{{_escape_bibtex_value(value)}}}"
            for name, value in fields.items()
            if value
        ]
        entries.append(
            f"@{entry_type}{{{item['bibtex_key']},\n"
            + ",\n".join(populated_fields)
            + "\n}"
        )
    return "\n\n".join(entries) + ("\n" if entries else "")


def _first_sentence(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return fallback
    match = re.search(r"(.+?[.!?])(?:\s|$)", cleaned)
    return (match.group(1) if match else cleaned[:300]).strip()


def infer_claim(item: dict[str, Any]) -> str:
    text = f"{item.get('title', '')} {item.get('abstract', '')}".lower()
    if any(word in text for word in ["gap", "limitation", "lack", "challenge", "not yet", "remain"]):
        return "current gap"
    if any(word in text for word in ["method", "model", "framework", "algorithm", "transformer"]):
        return "method background"
    if any(word in text for word in ["data", "dataset", "survey", "catalog", "multimodal"]):
        return "data background"
    return "background evidence"


def infer_evidence_summary(item: dict[str, Any]) -> str:
    fallback = f"{item.get('title', 'This source')} provides relevant context for the proposed study."
    return _first_sentence(str(item.get("abstract") or ""), fallback)


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if len(part.strip()) > 30]


def _pick_sentences(text: str, keywords: list[str], fallback: str, limit: int = 3) -> str:
    chosen = []
    for sentence in _sentences(text):
        lower = sentence.lower()
        if any(keyword in lower for keyword in keywords):
            chosen.append(sentence)
        if len(chosen) >= limit:
            break
    return " ".join(chosen) if chosen else fallback


def analyze_reference_item(item: dict[str, Any]) -> dict[str, str]:
    title = item.get("title") or "this paper"
    abstract = item.get("abstract") or item.get("pdf_text_excerpt") or ""
    return {
        "read_status": str(item.get("pdf_read_status") or "metadata_abstract_only"),
        "research_question": _pick_sentences(
            abstract,
            ["aim", "objective", "investigate", "classify", "detect", "identify", "transient"],
            f"The paper appears to address a topic related to {title}.",
            limit=2,
        ),
        "data_used": _pick_sentences(
            abstract,
            ["data", "dataset", "survey", "telescope", "light curve", "spectral", "observation", "sample"],
            "The available metadata does not state the dataset clearly; inspect the full paper before final manuscript claims.",
            limit=3,
        ),
        "methods": _pick_sentences(
            abstract,
            ["model", "method", "algorithm", "classification", "machine learning", "deep learning", "transformer", "cnn"],
            "The method family is not explicit in the available metadata.",
            limit=3,
        ),
        "scientific_results": _pick_sentences(
            abstract,
            ["result", "performance", "accuracy", "f1", "detect", "discover", "classified", "identified"],
            infer_evidence_summary(item),
            limit=3,
        ),
        "limitations": _pick_sentences(
            abstract,
            ["limitation", "limited", "future", "however", "challenge", "uncertain", "validation", "lack"],
            "No explicit limitation statement was identified in the available metadata.",
            limit=3,
        ),
        "relevance_to_study": _pick_sentences(
            abstract,
            ["x-ray", "transient", "einstein probe", "light curve", "spectral", "classification", "wxt", "fxt"],
            "Relevance should be judged from the title, abstract, citation weight, and method overlap.",
            limit=3,
        ),
        "pdf_excerpt": str(item.get("pdf_text_excerpt") or "")[:1200],
    }


def synthesize_cross_literature(items: list[dict[str, Any]]) -> dict[str, str]:
    summaries = [item.get("deep_summary") or {} for item in items]

    def join(key: str, fallback: str) -> str:
        text = " ".join(str(summary.get(key) or "") for summary in summaries)
        return re.sub(r"\s+", " ", text).strip()[:1800] or fallback

    return {
        "data_patterns": join("data_used", "No shared data pattern was extracted from the available metadata."),
        "method_patterns": join("methods", "No shared method pattern was extracted from the available metadata."),
        "limitation_patterns": join("limitations", "No shared limitation pattern was extracted from the available metadata."),
        "result_patterns": join("scientific_results", "No shared result pattern was extracted from the available metadata."),
    }


def citation_evidence_rows(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for item in items:
        contexts = item.get("search_contexts") or [item.get("search_context") or "idea"]
        for context_value in contexts:
            context = str(context_value or "idea").lower()
            section = {"idea": "introduction", "data": "data", "methods": "methods"}.get(context, "introduction")
            rows.append({
                "citation_key": item["bibtex_key"],
                "section": section,
                "claim": infer_claim(item),
                "evidence_summary": str(item.get("evidence_notes") or infer_evidence_summary(item)),
                "source": str(item.get("source") or "unknown"),
                "doi": str(item.get("doi") or ""),
                "url": str(item.get("url") or ""),
            })
    return rows


def literature_review_notes(items: list[dict[str, Any]], query: str = "") -> str:
    lines = ["# Literature Review Notes", ""]
    if query:
        lines.extend([f"Search query: {query}", ""])
    synthesis = synthesize_cross_literature(items)
    lines.extend([
        "## Cross-Paper Synthesis",
        "",
        "### Data Patterns",
        synthesis["data_patterns"],
        "",
        "### Method Patterns",
        synthesis["method_patterns"],
        "",
        "### Result Patterns",
        synthesis["result_patterns"],
        "",
        "### Limitation Patterns",
        synthesis["limitation_patterns"],
        "",
        "## Ranked Paper Notes",
        "",
    ])
    for index, item in enumerate(items, start=1):
        authors = ", ".join(item.get("authors") or ["Unknown author"])
        summary = item.get("deep_summary") or {}
        recommended_section = {"idea": "introduction", "data": "data", "methods": "methods"}.get(
            str(item.get("search_context") or "idea"),
            "introduction",
        )
        lines.extend([
            f"## {index}. {item['title']}",
            "",
            f"- Citation key: `{item['bibtex_key']}`",
            f"- Source: {item.get('source') or 'unknown'}",
            f"- Search context: {', '.join(item.get('search_contexts') or [item.get('search_context') or 'idea'])}",
            f"- Search query: {'; '.join(item.get('search_queries') or [item.get('search_query') or query])}",
            f"- Recommended section: {recommended_section}",
            f"- Authors/year: {authors} ({item.get('year')})",
            f"- Venue: {item.get('publication') or 'n/a'}",
            f"- Citation weight: {item.get('citation_weight', 0)}",
            f"- Relevance score: {item.get('relevance_score', 0)}",
            f"- Authority score: {item.get('authority_score', 0)}",
            f"- Journal authority: {item.get('journal_score', 0)}",
            f"- Evidence role: {infer_claim(item)}",
            f"- Evidence summary: {item.get('evidence_notes') or infer_evidence_summary(item)}",
            f"- Data used: {summary.get('data_used', '')}",
            f"- Methods: {summary.get('methods', '')}",
            f"- Limitations: {summary.get('limitations', '')}",
            "",
        ])
    return "\n".join(lines)


def _safe_filename(text: str, fallback: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").lower()
    return (name[:70].strip("_") or fallback)


def write_literature_html_summaries(references_dir: Path, items: list[dict[str, Any]]) -> list[str]:
    summary_dir = references_dir / "literature_summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    for old_summary in summary_dir.glob("*.html"):
        old_summary.unlink()
    output_files = []
    index_rows = []
    for index, item in enumerate(items, start=1):
        summary = item.get("deep_summary") or {}
        filename = f"{index:02d}_{_safe_filename(item.get('bibtex_key', ''), 'paper')}.html"
        relative = f"references/literature_summaries/{filename}"
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(item.get('title') or 'Literature Summary')}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 980px; margin: 32px auto; line-height: 1.55; color: #202124; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    .score {{ font-weight: 600; }}
  </style>
</head>
<body>
  <h1>{escape(item.get('title') or 'Literature Summary')}</h1>
  <table>
    <tr><th>Citation key</th><td>{escape(item.get('bibtex_key') or '')}</td></tr>
    <tr><th>Authors/year</th><td>{escape(', '.join(item.get('authors') or ['Unknown author']))} ({escape(str(item.get('year') or 'n.d.'))})</td></tr>
    <tr><th>Venue</th><td>{escape(item.get('publication') or 'n/a')}</td></tr>
    <tr><th>Search context</th><td>{escape(', '.join(item.get('search_contexts') or [item.get('search_context') or 'idea']))}</td></tr>
    <tr><th>Search query</th><td>{escape('; '.join(item.get('search_queries') or [item.get('search_query') or '']))}</td></tr>
    <tr><th>Recommended section</th><td>{escape({'idea': 'introduction', 'data': 'data', 'methods': 'methods'}.get(str(item.get('search_context') or 'idea'), 'introduction'))}</td></tr>
    <tr><th>Citation weight</th><td class="score">{escape(str(item.get('citation_weight', 0)))}</td></tr>
    <tr><th>Relevance to Study</th><td>{escape(str(item.get('relevance_score', 0)))}</td></tr>
    <tr><th>Journal authority</th><td>{escape(str(item.get('journal_score', 0)))} {escape(', '.join(item.get('journal_rank_labels') or []))}</td></tr>
    <tr><th>Citation authority</th><td>{escape(str(item.get('citation_authority_score', 0)))}</td></tr>
    <tr><th>DOI / URL</th><td>{escape(item.get('doi') or '')} {escape(item.get('url') or '')}</td></tr>
  </table>
  <h2>Abstract Summary</h2>
  <p>{escape(item.get('abstract') or 'No abstract metadata is available.')}</p>
  <h2>Structured Reading Notes</h2>
  <h3>Read Status</h3><p>{escape(summary.get('read_status') or '')}</p>
  <h3>Research Question</h3><p>{escape(summary.get('research_question') or '')}</p>
  <h3>Data Used</h3><p>{escape(summary.get('data_used') or '')}</p>
  <h3>Methods</h3><p>{escape(summary.get('methods') or '')}</p>
  <h3>Scientific Results</h3><p>{escape(summary.get('scientific_results') or '')}</p>
  <h3>Limitations</h3><p>{escape(summary.get('limitations') or '')}</p>
  <h3>Relevance to Study</h3><p>{escape(summary.get('relevance_to_study') or '')}</p>
  <h3>PDF Quick-Read Excerpt</h3><p>{escape(summary.get('pdf_excerpt') or 'No readable PDF excerpt was available.')}</p>
</body>
</html>
"""
        (summary_dir / filename).write_text(html, encoding="utf-8")
        output_files.append(relative)
        index_rows.append(
            f"<tr><td>{index}</td><td><a href=\"{escape(filename)}\">{escape(item.get('title') or '')}</a></td>"
            f"<td>{escape(item.get('bibtex_key') or '')}</td><td>{escape(', '.join(item.get('search_contexts') or [item.get('search_context') or 'idea']))}</td>"
            f"<td>{escape(str(item.get('citation_weight', 0)))}</td>"
            f"<td>{escape(str(item.get('relevance_score', 0)))}</td><td>{escape(str(item.get('journal_score', 0)))}</td></tr>"
        )
    index_html = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Literature Summary Index</title></head>
<body>
<h1>Literature Summary Index</h1>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>#</th><th>Title</th><th>Citation key</th><th>Context</th><th>Citation weight</th><th>Relevance</th><th>Journal authority</th></tr>
""" + "\n".join(index_rows) + "\n</table>\n</body>\n</html>\n"
    (summary_dir / "index.html").write_text(index_html, encoding="utf-8")
    return ["references/literature_summaries/index.html", *output_files]


def _write_citation_evidence(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["citation_key", "section", "claim", "evidence_summary", "source", "doi", "url"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _set_reference_manifest_outputs(project_path: Path) -> None:
    manifest_path = project_path / "references" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = ["idea/idea.md"]
    manifest["output_files"] = REFERENCE_OUTPUTS
    _write_json(manifest_path, manifest)


def write_reference_outputs(project: str | Path, items: list[dict[str, Any]], *, query: str = "", search_queries: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write normalized references, BibTeX, citation evidence, and review notes."""
    state = load_project(project)
    references_dir = state.path / "references"
    references_dir.mkdir(parents=True, exist_ok=True)

    project_text = " ".join([state.metadata.get("idea", ""), state.metadata.get("field", ""), query])
    normalized = select_references_by_context(
        items,
        project_text=project_text,
        target_journal=state.metadata.get("target_journal", ""),
        limit=MAX_REFERENCE_ITEMS,
    )
    normalized = [enrich_pdf_text(item) for item in normalized]
    normalized = [item for item in normalized if has_readable_evidence(item)]
    normalized = [{**item, "deep_summary": analyze_reference_item(item)} for item in normalized]
    _write_json(references_dir / "literature_items.json", normalized)
    _write_json(references_dir / "search_queries.json", search_queries or {"idea": query})
    (references_dir / "library.bib").write_text(generate_bibtex(normalized), encoding="utf-8")
    _write_citation_evidence(references_dir / "citation_evidence.csv", citation_evidence_rows(normalized))
    (references_dir / "literature_review_notes.md").write_text(
        literature_review_notes(normalized, query=query),
        encoding="utf-8",
    )
    html_outputs = write_literature_html_summaries(references_dir, normalized)

    update_stage_status(state.path, "references", "draft")
    _set_reference_manifest_outputs(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "item_count": len(normalized),
        "outputs": REFERENCE_OUTPUTS + [item for item in html_outputs if item not in REFERENCE_OUTPUTS],
    }
