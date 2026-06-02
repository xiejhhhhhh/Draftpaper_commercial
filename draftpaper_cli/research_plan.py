from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .journal_profile import JournalProfileError, validate_journal_profile_for_writing
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


RESEARCH_PLAN_INPUTS = [
    "idea/idea.md",
    "references/literature_items.json",
    "references/citation_evidence.csv",
    "references/literature_review_notes.md",
    "journal_profile/journal_profile.json",
    "journal_profile/journal_guidelines.md",
]

RESEARCH_PLAN_OUTPUTS = [
    "research_plan/research_plan.md",
    "research_plan/research_questions.md",
    "research_plan/target_journal_anchor_papers.json",
    "research_plan/novelty_overlap_report.json",
    "research_plan/novelty_overlap_report.md",
]


class MissingReferencesError(FileNotFoundError):
    """Raised when the formal research plan is requested before references exist."""


class NoveltyOverlapError(RuntimeError):
    """Raised when retrieved literature appears too similar to the proposed study."""

    def __init__(self, message: str, report_path: Path) -> None:
        super().__init__(message)
        self.report_path = report_path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_citation_evidence(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _require_reference_inputs(project_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    missing = [relative for relative in RESEARCH_PLAN_INPUTS[1:] if not (project_path / relative).exists()]
    if missing:
        raise MissingReferencesError(
            "Formal research planning requires references outputs first. Missing: " + ", ".join(missing)
        )
    literature_items = _read_json(project_path / "references" / "literature_items.json")
    citation_rows = _read_citation_evidence(project_path / "references" / "citation_evidence.csv")
    literature_notes = (project_path / "references" / "literature_review_notes.md").read_text(encoding="utf-8")
    if not isinstance(literature_items, list) or not literature_items:
        raise MissingReferencesError("references/literature_items.json must contain at least one literature item.")
    if not citation_rows:
        raise MissingReferencesError("references/citation_evidence.csv must contain at least one evidence row.")
    return literature_items, citation_rows, literature_notes


def _compact(text: str, limit: int = 260) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."


def _top_items(literature_items: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    return sorted(literature_items, key=lambda item: int(item.get("citation_count") or 0), reverse=True)[:limit]


def _tokens(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "using", "based", "from", "this", "that", "study", "paper",
        "method", "methods", "model", "models", "data", "analysis", "research", "framework",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", (text or "").lower())
        if token not in stopwords
    }


def _study_context(project_path: Path, project_meta: dict[str, Any]) -> str:
    parts = [project_meta.get("title", ""), project_meta.get("idea", ""), project_meta.get("field", "")]
    for relative in [
        "idea/idea.md",
        "data/data_inventory.json",
        "data/data_feasibility_report.json",
        "methods/method_plan.md",
        "methods/method_requirements.json",
    ]:
        path = project_path / relative
        if path.exists():
            parts.append(path.read_text(encoding="utf-8", errors="replace")[:4000])
    return " ".join(parts)


def _journal_aliases(target_journal: str) -> set[str]:
    normalized = (target_journal or "").lower()
    aliases = {normalized} if normalized else set()
    if "apjs" in normalized or "supplement" in normalized:
        aliases.update({"apjs", "astrophysical journal supplement", "astrophysical journal supplement series", "aas journals"})
    if "apj" in normalized or "astrophysical journal" in normalized:
        aliases.update({"apj", "astrophysical journal", "aas journals"})
    return {alias for alias in aliases if alias}


def _similarity_score(study_terms: set[str], item: dict[str, Any]) -> float:
    item_text = " ".join([
        str(item.get("title") or ""),
        str(item.get("abstract") or ""),
        str((item.get("deep_summary") or {}).get("methods") or ""),
        str((item.get("deep_summary") or {}).get("data_used") or ""),
    ])
    item_terms = _tokens(item_text)
    if not study_terms or not item_terms:
        return 0.0
    return round((2 * len(study_terms & item_terms)) / (len(study_terms) + len(item_terms)), 3)


def _pair_similarity(left: str, right: str) -> float:
    left_terms = _tokens(left)
    right_terms = _tokens(right)
    if not left_terms or not right_terms:
        return 0.0
    return round((2 * len(left_terms & right_terms)) / (len(left_terms) + len(right_terms)), 3)


def analyze_target_journal_literature(
    project_path: Path,
    project_meta: dict[str, Any],
    literature_items: list[dict[str, Any]],
    *,
    high_similarity_threshold: float = 0.82,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    study_terms = _tokens(_study_context(project_path, project_meta))
    aliases = _journal_aliases(project_meta.get("target_journal", ""))
    enriched = []
    for item in literature_items:
        publication = str(item.get("publication") or "").lower()
        journal_match = any(alias in publication for alias in aliases)
        similarity = max(
            _similarity_score(study_terms, item),
            _pair_similarity(str(project_meta.get("idea") or ""), str(item.get("title") or "")),
            _pair_similarity(str(project_meta.get("title") or ""), str(item.get("title") or "")),
        )
        anchor_score = round(
            (0.55 * float(item.get("citation_weight") or 0))
            + (0.35 * similarity)
            + (0.10 if journal_match else 0.0),
            3,
        )
        enriched.append({
            "citation_key": item.get("bibtex_key", ""),
            "title": item.get("title", ""),
            "publication": item.get("publication", ""),
            "year": item.get("year", ""),
            "doi": item.get("doi", ""),
            "url": item.get("url", ""),
            "citation_weight": item.get("citation_weight", 0),
            "target_journal_match": journal_match,
            "study_similarity_score": similarity,
            "anchor_score": anchor_score,
            "evidence_summary": item.get("evidence_notes") or "",
        })
    anchors = sorted(enriched, key=lambda item: (item["anchor_score"], item["target_journal_match"]), reverse=True)[:8]
    high_similarity = sorted(
        [item for item in enriched if item["study_similarity_score"] >= high_similarity_threshold],
        key=lambda item: item["study_similarity_score"],
        reverse=True,
    )
    report = {
        "target_journal": project_meta.get("target_journal"),
        "high_similarity_threshold": high_similarity_threshold,
        "high_similarity_found": bool(high_similarity),
        "high_similarity_count": len(high_similarity),
        "highest_similarity_score": max((item["study_similarity_score"] for item in enriched), default=0.0),
        "high_similarity_items": high_similarity,
        "recommended_action": (
            "Ask the user whether to continue, revise the research question, change the data or method route, or reposition the manuscript."
            if high_similarity else
            "Proceed, using target-journal anchor papers as structural references without copying claims or wording."
        ),
    }
    return anchors, report


def _write_novelty_report_md(path: Path, report: dict[str, Any], anchors: list[dict[str, Any]]) -> None:
    lines = [
        "# Novelty and Target-Journal Anchor Report",
        "",
        f"Target journal: {report.get('target_journal')}",
        "",
        f"High similarity found: {str(report.get('high_similarity_found')).lower()}",
        "",
        f"Highest similarity score: {report.get('highest_similarity_score')}",
        "",
        "## High-Similarity Items",
        "",
    ]
    for item in report.get("high_similarity_items") or []:
        lines.append(f"- `{item.get('citation_key')}` {item.get('title')} ({item.get('publication')}, similarity={item.get('study_similarity_score')})")
    if not report.get("high_similarity_items"):
        lines.append("- None.")
    lines.extend(["", "## Target-Journal Anchor Papers", ""])
    for item in anchors:
        lines.append(f"- `{item.get('citation_key')}` {item.get('title')} ({item.get('publication')}, anchor={item.get('anchor_score')}, similarity={item.get('study_similarity_score')})")
    lines.extend(["", "## Recommended Action", "", str(report.get("recommended_action") or "")])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _evidence_by_claim(citation_rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in citation_rows:
        grouped.setdefault(row.get("claim") or "background evidence", []).append(row)
    return grouped


def _format_evidence_sentence(row: dict[str, str]) -> str:
    key = row.get("citation_key", "unknown")
    summary = _compact(row.get("evidence_summary", ""))
    return f"`{key}` supports the {row.get('claim', 'evidence')} claim: {summary}"


def _infer_data_requirements(project_meta: dict[str, Any], evidence_rows: list[dict[str, str]]) -> str:
    blob = " ".join(
        [project_meta.get("idea", ""), project_meta.get("field", "")]
        + [row.get("evidence_summary", "") for row in evidence_rows]
    ).lower()
    requirements = []
    if any(term in blob for term in ["multimodal", "photometric", "spectroscopic", "survey", "time-domain"]):
        requirements.append("multimodal survey records with aligned object identifiers, observation times, and quality flags")
    if any(term in blob for term in ["image", "figure", "vision"]):
        requirements.append("image-derived or visual feature products with reproducible preprocessing metadata")
    if any(term in blob for term in ["external validation", "validation", "generalization"]):
        requirements.append("an external validation split or independent dataset to test generalization")
    if not requirements:
        requirements.append("a documented primary dataset with reproducible preprocessing and quality-control metadata")
    return "; ".join(requirements) + "."


def _infer_method_route(project_meta: dict[str, Any], evidence_rows: list[dict[str, str]]) -> str:
    blob = " ".join(
        [project_meta.get("idea", ""), project_meta.get("field", "")]
        + [row.get("evidence_summary", "") for row in evidence_rows]
    ).lower()
    if "transformer" in blob or "attention" in blob:
        return (
            "Start with a transparent baseline model, then evaluate a transformer or attention-based model for sequence "
            "and multimodal feature fusion. The method section should report preprocessing, feature alignment, model "
            "inputs, validation protocol, ablation design, and uncertainty handling."
        )
    if "multimodal" in blob:
        return (
            "Construct modality-specific feature blocks, compare single-modality baselines with fused models, and use "
            "ablation tests to show which data source adds value."
        )
    return "Define baseline models first, then introduce the proposed method only where it directly addresses the literature-supported gap."


def _build_research_questions(project_meta: dict[str, Any], citation_rows: list[dict[str, str]]) -> list[str]:
    idea = project_meta.get("idea", "the proposed study")
    has_gap = any((row.get("claim") or "") == "current gap" for row in citation_rows)
    questions = [
        f"RQ1: How can {idea} be formulated as a reproducible empirical study grounded in the retrieved literature?",
        "RQ2: Which data sources and preprocessing steps are necessary to test the proposed research gap without relying on unsupported assumptions?",
        "RQ3: How does the proposed method compare with baseline or literature-derived alternatives under a transparent validation protocol?",
    ]
    if has_gap:
        questions.append("RQ4: Does the proposed design directly address the literature-supported gap identified in the citation evidence table?")
    return questions


def render_research_questions(project_meta: dict[str, Any], citation_rows: list[dict[str, str]]) -> str:
    lines = ["# Research Questions", ""]
    for question in _build_research_questions(project_meta, citation_rows):
        lines.extend([question, ""])
    return "\n".join(lines)


def render_research_plan(
    project_meta: dict[str, Any],
    literature_items: list[dict[str, Any]],
    citation_rows: list[dict[str, str]],
    literature_notes: str,
    anchor_papers: list[dict[str, Any]] | None = None,
) -> str:
    grouped = _evidence_by_claim(citation_rows)
    top_items = _top_items(literature_items)
    questions = _build_research_questions(project_meta, citation_rows)
    evidence_sentences = [_format_evidence_sentence(row) for row in citation_rows[:8]]

    lines = [
        "# Literature-Informed Research Plan",
        "",
        "## Project Context",
        "",
        f"Working title: {project_meta.get('title') or project_meta.get('idea')}",
        "",
        f"Research idea: {project_meta.get('idea')}",
        "",
        f"Field or aim: {project_meta.get('field')}",
        "",
        f"Target journal: {project_meta.get('target_journal')}",
        "",
        "## Literature Basis",
        "",
        f"This plan is based on {len(literature_items)} retrieved literature records and {len(citation_rows)} citation-evidence rows. It should be revised whenever the references stage changes.",
        "",
    ]

    for item in top_items:
        authors = ", ".join(item.get("authors") or ["Unknown author"])
        lines.append(f"- `{item.get('bibtex_key')}`: {item.get('title')} ({authors}, {item.get('year')}).")

    lines.extend(["", "## Evidence-Supported Gap", ""])
    gap_rows = grouped.get("current gap") or citation_rows[:2]
    for row in gap_rows[:4]:
        lines.append(f"- {_format_evidence_sentence(row)}")
    lines.extend([
        "",
        "The formal research gap should therefore be written as a literature-supported problem rather than as a free-form AI assumption. The first draft should focus on the gap that can be traced to the strongest citation evidence above.",
        "",
        "## Target-Journal Anchor Literature",
        "",
    ])
    for item in (anchor_papers or [])[:5]:
        lines.append(
            f"- `{item.get('citation_key')}` should be used as a structural reference for the target journal because it has anchor score {item.get('anchor_score')} and study similarity {item.get('study_similarity_score')}. The draft may follow its manuscript logic at a high level, but must not copy wording, claims, figures, or unsupported assumptions."
        )
    if not anchor_papers:
        lines.append("- No target-journal anchor paper was identified from the current literature set.")
    lines.extend([
        "",
        "## Research Questions",
        "",
    ])
    for question in questions:
        lines.append(f"- {question}")

    lines.extend([
        "",
        "## Hypotheses",
        "",
        "- H1: A method designed around the literature-supported gap will improve over baseline approaches when evaluated with a transparent validation protocol.",
        "- H2: The selected data construction and preprocessing steps will materially affect model reliability and should be tested through ablation or sensitivity analysis.",
        "",
        "## Data Requirements",
        "",
        _infer_data_requirements(project_meta, citation_rows),
        "",
        "## Method Route",
        "",
        _infer_method_route(project_meta, citation_rows),
        "",
        "## Expected Figures and Tables",
        "",
        "- Fig. 1: Study workflow from data construction to validation and interpretation.",
        "- Fig. 2: Proposed model or analytical framework, including the parts that address the literature-supported gap.",
        "- Table 1: Dataset summary, preprocessing choices, and validation split design.",
        "- Table 2: Baseline comparison and ablation results.",
        "",
        "## Expected Contribution",
        "",
        "The expected contribution is a traceable research design that connects the user-provided idea to explicit literature evidence, reproducible data construction, and a validation strategy that can be checked before manuscript writing.",
        "",
        "## Risks and User Confirmation",
        "",
        "- Confirm whether the available local data are sufficient for the proposed validation design.",
        "- Confirm whether the retrieved literature set is broad enough for the target journal before writing the Introduction.",
        "- Confirm whether the method route can be implemented and run before generating the Methods section.",
        "",
        "## Citation Evidence Used",
        "",
    ])
    for sentence in evidence_sentences:
        lines.append(f"- {sentence}")
    lines.extend(["", "## Literature Notes Snapshot", "", _compact(literature_notes, limit=1200), ""])
    return "\n".join(lines)


def _set_research_plan_manifest(project_path: Path) -> None:
    manifest_path = project_path / "research_plan" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = RESEARCH_PLAN_INPUTS
    manifest["output_files"] = RESEARCH_PLAN_OUTPUTS
    _write_json(manifest_path, manifest)


def generate_research_plan(project: str | Path, *, allow_high_similarity: bool = False) -> dict[str, Any]:
    """Generate a formal research plan from retrieved literature and citation evidence."""
    state = load_project(project)
    try:
        validate_journal_profile_for_writing(state.path)
    except JournalProfileError as exc:
        raise MissingReferencesError(str(exc)) from exc
    literature_items, citation_rows, literature_notes = _require_reference_inputs(state.path)
    research_plan_dir = state.path / "research_plan"
    research_plan_dir.mkdir(parents=True, exist_ok=True)
    anchor_papers, novelty_report = analyze_target_journal_literature(state.path, state.metadata, literature_items)
    _write_json(research_plan_dir / "target_journal_anchor_papers.json", {"anchor_papers": anchor_papers})
    _write_json(research_plan_dir / "novelty_overlap_report.json", novelty_report)
    _write_novelty_report_md(research_plan_dir / "novelty_overlap_report.md", novelty_report, anchor_papers)
    if novelty_report.get("high_similarity_found") and not allow_high_similarity:
        raise NoveltyOverlapError(
            "A highly similar paper was found. Review research_plan/novelty_overlap_report.md and rerun generate-plan with --allow-high-similarity only if the user chooses to continue.",
            research_plan_dir / "novelty_overlap_report.md",
        )

    plan_text = render_research_plan(state.metadata, literature_items, citation_rows, literature_notes, anchor_papers)
    questions_text = render_research_questions(state.metadata, citation_rows)
    (research_plan_dir / "research_plan.md").write_text(plan_text, encoding="utf-8")
    (research_plan_dir / "research_questions.md").write_text(questions_text, encoding="utf-8")

    update_stage_status(state.path, "research_plan", "draft")
    _set_research_plan_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "research_plan": str(research_plan_dir / "research_plan.md"),
        "research_questions": str(research_plan_dir / "research_questions.md"),
        "citation_count": len(citation_rows),
        "literature_count": len(literature_items),
        "anchor_paper_count": len(anchor_papers),
        "highest_similarity_score": novelty_report.get("highest_similarity_score"),
        "outputs": RESEARCH_PLAN_OUTPUTS,
    }
