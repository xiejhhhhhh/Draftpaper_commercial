from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .paper_fetch_adapter import enrich_with_paper_fetch
from .project_state import load_project
from .references import normalize_reference_items, write_reference_outputs


def _read_text_if_exists(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def build_search_query(project: str | Path, query: str | None = None) -> str:
    if query:
        return query.strip()
    state = load_project(project)
    parts = [
        state.metadata.get("idea", ""),
        state.metadata.get("field", ""),
        state.metadata.get("target_journal", ""),
    ]
    return " ".join(part for part in parts if part).strip()


def _keywords_from_text(text: str, limit: int = 14) -> str:
    stopwords = {
        "using", "based", "with", "from", "data", "model", "models", "study", "research", "paper",
        "analysis", "method", "methods", "framework", "classification", "result", "results",
        "project", "target", "journal", "general", "academic",
        "file", "files", "count", "path", "raw", "description", "txt", "kind", "suffix", "size",
        "bytes", "readable", "null", "column", "columns", "row", "rows", "missing", "cells", "total", "cell",
    }
    tokens = []
    seen = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text or ""):
        lowered = token.lower()
        if lowered in stopwords or lowered in seen or len(lowered) > 36:
            continue
        tokens.append(token)
        seen.add(lowered)
        if len(tokens) >= limit:
            break
    return " ".join(tokens)


def _compact_query(text: str, limit: int = 220) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit].strip()


def _unique_queries(queries: list[str], limit: int = 5) -> list[str]:
    unique = []
    seen = set()
    for query in queries:
        compact = _compact_query(query)
        key = compact.lower()
        if not compact or key in seen:
            continue
        unique.append(compact)
        seen.add(key)
        if len(unique) >= limit:
            break
    return unique


def _method_phrases(method_text: str) -> list[str]:
    phrases = []
    for raw_line in method_text.splitlines():
        line = raw_line.strip(" -;\t")
        if not line:
            continue
        lowered = line.lower()
        if line.startswith("#") or lowered.startswith(("research idea", "user-provided", "formal ")):
            continue
        phrase = re.split(r"[:：]", line, maxsplit=1)[0].strip()
        if phrase:
            phrases.append(phrase)
    fallback = [
        "1D CNN ResNet",
        "Transformer irregular time series",
        "Temporal Convolutional Network",
        "multimodal network",
        "contrastive learning self-supervised pretraining",
    ]
    return _unique_queries(phrases + fallback, limit=5)


def _data_terms(data_text: str) -> str:
    allowed = [
        "light curve",
        "spectral",
        "hardness ratio",
        "multi-band",
        "multiband",
        "catalog",
        "WXT",
        "FXT",
        "Einstein Probe",
        "X-ray",
    ]
    found = []
    lowered = data_text.lower()
    for term in allowed:
        if term.lower() in lowered:
            found.append(term)
    return " ".join(found)


def _domain_anchor(project_text: str, field: str, target_journal: str) -> str:
    field_keywords = _keywords_from_text(field, limit=8)
    return _compact_query(field_keywords or _keywords_from_text(project_text, limit=8), limit=140)


def build_context_search_queries(project: str | Path, query: str | None = None) -> dict[str, str | list[str]]:
    state = load_project(project)
    idea_query = query or build_search_query(project)
    domain_anchor = _domain_anchor(
        str(state.metadata.get("idea", "")),
        str(state.metadata.get("field", "")),
        str(state.metadata.get("target_journal", "")),
    )
    data_text = " ".join([
        _read_text_if_exists(state.path / "data" / "data_inventory.json"),
        _read_text_if_exists(state.path / "data" / "data_feasibility_report.json"),
        _read_text_if_exists(state.path / "idea" / "idea.md"),
    ])
    method_text = " ".join([
        _read_text_if_exists(state.path / "methods" / "method_plan.md"),
        _read_text_if_exists(state.path / "methods" / "method_requirements.json"),
        _read_text_if_exists(state.path / "research_plan" / "research_plan.md"),
    ])
    data_terms = _data_terms(data_text)
    data_queries = _unique_queries([
        f"{domain_anchor} light curve dataset catalog {data_terms}",
        f"{domain_anchor} spectral features hardness ratio dataset {data_terms}",
        f"{domain_anchor} multi-band counterpart catalog source classification {data_terms}",
        f"{domain_anchor} WXT FXT observation data release {data_terms}",
        f"{domain_anchor} X-ray transient sample construction {data_terms}",
    ])
    method_queries = _unique_queries([
        f"{domain_anchor} {phrase} X-ray transient classification"
        for phrase in _method_phrases(method_text)
    ])
    return {
        "idea": idea_query.strip(),
        "data": data_queries or [idea_query.strip()],
        "methods": method_queries or [idea_query.strip()],
    }


def _get_json(url: str, params: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 12) -> dict[str, Any]:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(full_url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def search_semantic_scholar(query: str, limit: int = 30) -> list[dict[str, Any]]:
    if not query:
        return []
    fields = ",".join([
        "title",
        "abstract",
        "year",
        "authors",
        "venue",
        "publicationVenue",
        "citationCount",
        "externalIds",
        "openAccessPdf",
        "url",
    ])
    headers = {}
    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    try:
        payload = _get_json(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            {"query": query, "limit": min(limit, 100), "fields": fields},
            headers=headers,
        )
    except Exception:
        return []

    items = []
    for paper in payload.get("data", []):
        external_ids = paper.get("externalIds") or {}
        publication_venue = paper.get("publicationVenue") or {}
        open_access_pdf = paper.get("openAccessPdf") or {}
        items.append({
            "title": paper.get("title", ""),
            "authors": [author.get("name", "") for author in paper.get("authors", []) if author.get("name")],
            "year": str(paper.get("year") or ""),
            "doi": external_ids.get("DOI", ""),
            "url": paper.get("url", ""),
            "abstract": paper.get("abstract") or "",
            "publication": publication_venue.get("name") or paper.get("venue", ""),
            "citation_count": paper.get("citationCount") or 0,
            "pdf_url": open_access_pdf.get("url", "") if isinstance(open_access_pdf, dict) else "",
            "source": "semantic_scholar",
        })
    return normalize_reference_items(items)


def _query_tokens(query: str, limit: int = 6) -> list[str]:
    stopwords = {"using", "based", "with", "from", "data", "model", "models", "study", "research"}
    tokens = []
    seen = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", query):
        lowered = token.lower()
        if lowered not in stopwords and lowered not in seen:
            tokens.append(token)
            seen.add(lowered)
        if len(tokens) >= limit:
            break
    return tokens


def search_arxiv(query: str, limit: int = 30) -> list[dict[str, Any]]:
    tokens = _query_tokens(query)
    if not tokens:
        return []
    params = urllib.parse.urlencode({
        "search_query": " AND ".join(f"all:{token}" for token in tokens[:5]),
        "start": 0,
        "max_results": min(limit, 20),
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    try:
        with urllib.request.urlopen(f"https://export.arxiv.org/api/query?{params}", timeout=12) as response:
            root = ET.fromstring(response.read().decode("utf-8"))
    except Exception:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        authors = [
            (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            for author in entry.findall("atom:author", ns)
        ]
        items.append({
            "title": title,
            "authors": [author for author in authors if author],
            "year": published[:4],
            "doi": "",
            "url": url,
            "abstract": summary,
            "publication": "arXiv",
            "citation_count": 0,
            "source": "arxiv",
        })
    return normalize_reference_items(items)


def search_crossref(query: str, limit: int = 30) -> list[dict[str, Any]]:
    if not query:
        return []
    try:
        payload = _get_json(
            "https://api.crossref.org/works",
            {
                "query.bibliographic": query,
                "rows": min(limit, 20),
                "select": "DOI,title,author,container-title,published-print,published-online,issued,URL,is-referenced-by-count,abstract",
            },
            headers={"User-Agent": "DraftPaper CLI local workflow (mailto:local@example.com)"},
        )
    except Exception:
        return []

    items = []
    for work in (payload.get("message") or {}).get("items", []):
        title = " ".join((work.get("title") or [""])[0].split())
        authors = []
        for author in work.get("author") or []:
            name = " ".join([author.get("given", ""), author.get("family", "")]).strip()
            if name:
                authors.append(name)
        date_parts = (
            ((work.get("published-print") or {}).get("date-parts") or [[]])[0]
            or ((work.get("published-online") or {}).get("date-parts") or [[]])[0]
            or ((work.get("issued") or {}).get("date-parts") or [[]])[0]
        )
        abstract = re.sub(r"<[^>]+>", " ", work.get("abstract") or "")
        items.append({
            "title": title,
            "authors": authors,
            "year": str(date_parts[0]) if date_parts else "",
            "doi": work.get("DOI", ""),
            "url": work.get("URL", ""),
            "abstract": " ".join(abstract.split()),
            "publication": " ".join((work.get("container-title") or [""])[0].split()),
            "citation_count": work.get("is-referenced-by-count") or 0,
            "source": "crossref",
        })
    return normalize_reference_items(items)


def search_serpapi(query: str, limit: int = 30) -> list[dict[str, Any]]:
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key or not query:
        return []
    try:
        payload = _get_json(
            "https://serpapi.com/search.json",
            {"engine": "google_scholar", "q": query, "api_key": api_key, "num": min(limit, 20)},
        )
    except Exception:
        return []
    items = []
    for index, paper in enumerate(payload.get("organic_results", [])[:limit]):
        publication_info = paper.get("publication_info") or {}
        year_match = re.search(r"(19|20)\d{2}", f"{publication_info.get('summary', '')} {paper.get('snippet', '')}")
        items.append({
            "title": paper.get("title", ""),
            "authors": [author.get("name", "") for author in publication_info.get("authors", []) if author.get("name")],
            "year": year_match.group(0) if year_match else "",
            "doi": "",
            "url": paper.get("link", ""),
            "abstract": paper.get("snippet", ""),
            "publication": publication_info.get("summary", ""),
            "citation_count": int((paper.get("inline_links") or {}).get("cited_by", {}).get("total", 0) or 0),
            "source": "google_scholar_serpapi",
        })
    return normalize_reference_items(items)


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return normalize_reference_items(items)


def search_free_literature(query: str, limit: int = 30) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for provider in (search_semantic_scholar, search_arxiv, search_crossref, search_serpapi):
        results.extend(provider(query, limit=limit))
        results = dedupe_items(results)
    return results[:limit]


def _as_query_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def search_literature_for_project(
    project: str | Path,
    *,
    query: str | None = None,
    limit: int = 30,
    from_json: str | Path | None = None,
) -> dict[str, Any]:
    final_query = build_search_query(project, query)
    search_queries = build_context_search_queries(project, query)
    if from_json:
        payload = json.loads(Path(from_json).read_text(encoding="utf-8-sig"))
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        if isinstance(payload, dict) and isinstance(payload.get("search_queries"), dict):
            search_queries.update({str(key): value for key, value in payload["search_queries"].items()})
    else:
        items = []
        for context, context_query_value in search_queries.items():
            for context_query in _as_query_list(context_query_value):
                per_query_limit = min(limit, 2) if context in {"data", "methods"} else limit
                context_items = search_free_literature(context_query, limit=per_query_limit)
                for item in context_items:
                    item["search_context"] = context
                    item["search_query"] = context_query
                items.extend(context_items)
        items, _manifest = enrich_with_paper_fetch(project, items)
    return write_reference_outputs(project, list(items or []), query=final_query, search_queries=search_queries)
