from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


DISCUSSION_INPUTS = [
    "research_plan/research_plan.md",
    "introduction/introduction.tex",
    "results/results.tex",
    "references/citation_evidence.csv",
    "references/library.bib",
]

DISCUSSION_OUTPUTS = [
    "discussion/discussion.tex",
]


class MissingDiscussionInputsError(FileNotFoundError):
    """Raised when Discussion is requested before prior sections and reference evidence exist."""


class DiscussionCitationIntegrityError(RuntimeError):
    """Raised when Discussion citation evidence cannot be matched to the BibTeX library."""


def _read_citation_evidence(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _bibtex_keys(content: str) -> set[str]:
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", content))


def _require_inputs(project_path: Path) -> tuple[str, str, str, list[dict[str, str]]]:
    missing = [relative for relative in DISCUSSION_INPUTS if not (project_path / relative).exists()]
    if missing:
        raise MissingDiscussionInputsError(
            "Discussion writing requires research plan, Introduction, Results, and references outputs first. Missing: "
            + ", ".join(missing)
        )
    plan_text = (project_path / "research_plan" / "research_plan.md").read_text(encoding="utf-8")
    introduction_text = (project_path / "introduction" / "introduction.tex").read_text(encoding="utf-8")
    results_text = (project_path / "results" / "results.tex").read_text(encoding="utf-8")
    citation_rows = _read_citation_evidence(project_path / "references" / "citation_evidence.csv")
    bibtex = (project_path / "references" / "library.bib").read_text(encoding="utf-8")
    if not citation_rows:
        raise MissingDiscussionInputsError("references/citation_evidence.csv has no evidence rows.")
    keys = _bibtex_keys(bibtex)
    missing_keys = sorted({row.get("citation_key", "") for row in citation_rows if row.get("citation_key")} - keys)
    if missing_keys:
        raise DiscussionCitationIntegrityError(
            "Citation evidence keys are missing from library.bib: " + ", ".join(missing_keys)
        )
    return plan_text, introduction_text, results_text, citation_rows


def _safe_latex_text(text: str) -> str:
    replacements = {
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
    return "".join(replacements.get(char, char) for char in str(text or ""))


def _paragraph(text: str) -> str:
    escaped = _safe_latex_text(text)
    escaped = re.sub(r"\\citep\\\{([^{}\\]+)\\\}", r"\\citep{\1}", escaped)
    return escaped


def _compact(text: str, limit: int = 300) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."


def _rows_by_claim(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row.get("claim") or "background evidence", []).append(row)
    return grouped


def _pick(rows: list[dict[str, str]], claim: str, fallback_index: int = 0) -> dict[str, str]:
    candidates = _rows_by_claim(rows).get(claim) or rows
    return candidates[min(fallback_index, len(candidates) - 1)]


def _cite(row: dict[str, str]) -> str:
    return f"\\citep{{{row.get('citation_key')}}}"


def _evidence(row: dict[str, str]) -> str:
    return _compact(row.get("evidence_summary", ""))


def _result_signal(results_text: str) -> str:
    subsection_match = re.search(r"\\subsection\{([^{}]+)\}", results_text)
    if subsection_match:
        return subsection_match.group(1)
    figure_match = re.search(r"\\includegraphics(?:\[[^\]]+\])?\{([^{}]+)\}", results_text)
    if figure_match:
        return f"the result artifact {figure_match.group(1)}"
    return "the registered local result artifacts"


def _expected_contribution(plan_text: str) -> str:
    match = re.search(r"## Expected Contribution\s+(.*?)(?:\n## |\Z)", plan_text, flags=re.S)
    if match:
        return _compact(match.group(1), 360)
    return "the traceable connection between the research gap, local evidence, verified methods, and result interpretation"


def _method_route(plan_text: str) -> str:
    match = re.search(r"## Method Route\s+(.*?)(?:\n## |\Z)", plan_text, flags=re.S)
    if match:
        return _compact(match.group(1), 360)
    return "the planned method route"


def render_discussion_tex(
    project_meta: dict[str, Any],
    plan_text: str,
    introduction_text: str,
    results_text: str,
    citation_rows: list[dict[str, str]],
) -> str:
    idea = project_meta.get("idea") or project_meta.get("title") or "the proposed study"
    field = project_meta.get("field") or "the target field"
    background = _pick(citation_rows, "background evidence", 0)
    data = _pick(citation_rows, "data background", 0)
    method = _pick(citation_rows, "method background", 0)
    gap = _pick(citation_rows, "current gap", 0)
    result_signal = _result_signal(results_text)
    contribution = _expected_contribution(plan_text)
    method_route = _method_route(plan_text)
    intro_citation_count = len(re.findall(r"\\cite[a-zA-Z*]*\{", introduction_text))

    paragraphs = [
        "\\section{Discussion}",
        (
            f"The findings should be interpreted as evidence for a reproducible workflow around {idea} rather than as an isolated modelling result. "
            f"In {field}, the literature basis identified a concrete gap: {_evidence(gap)} {_cite(gap)} The local results, especially {result_signal}, "
            f"therefore matter because they connect the planned research question to artifacts produced inside the project rather than to unsupported narrative claims."
        ),
        (
            f"The main contribution is consistent with the research plan: {contribution} This contribution extends the Introduction rather than repeating it, "
            f"because the Discussion can now relate the retrieved literature to what the result files actually show. The Introduction used {intro_citation_count} "
            f"citation-backed statements to establish the study frame, and the present section uses those same evidence records to explain why the results are meaningful."
        ),
        (
            f"Compared with existing work, the current draft should emphasize where the local findings agree with or depart from the cited evidence. "
            f"Prior data-oriented work indicates that {_evidence(data).lower()} {_cite(data)} Method-oriented work further suggests that {_evidence(method).lower()} {_cite(method)} "
            f"The present results should therefore be discussed through data construction, validation design, and method behavior rather than through a broad claim of novelty."
        ),
        (
            f"\\subsection{{Limitations and Future Work}}\n"
            f"The principal limitation is that the present Discussion remains constrained by the available project artifacts. If the local results are preliminary, sparse, "
            f"or generated from a narrow validation setting, the manuscript should state that limitation directly and avoid converting an observed pattern into a general conclusion. "
            f"The method route also requires continued checking: {method_route} Future revisions should update this section whenever the Results manifest, method verification manifest, "
            f"or citation-evidence table changes, because those files define the defensible boundary of the paper."
        ),
        (
            f"Overall, the study is best presented as a literature-informed and locally reproducible answer to the gap identified above. Background evidence shows why the topic is relevant "
            f"{_cite(background)}, while the result artifacts determine how far the manuscript can go in interpreting the specific findings. This keeps the Discussion aligned with the "
            f"paper's evidence trail and avoids adding claims that are not supported by either the retrieved literature or the generated project outputs."
        ),
    ]
    return "\n\n".join(_paragraph(paragraph) if not paragraph.startswith("\\section") else paragraph for paragraph in paragraphs) + "\n"


def _set_discussion_manifest(project_path: Path) -> None:
    manifest_path = project_path / "discussion" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = DISCUSSION_INPUTS
    manifest["output_files"] = DISCUSSION_OUTPUTS
    _write_json(manifest_path, manifest)


def write_discussion(project: str | Path) -> dict[str, Any]:
    """Write a traceable LaTeX Discussion from prior sections, results, and citation evidence."""
    state = load_project(project)
    plan_text, introduction_text, results_text, citation_rows = _require_inputs(state.path)
    discussion_dir = state.path / "discussion"
    discussion_dir.mkdir(parents=True, exist_ok=True)
    output_path = discussion_dir / "discussion.tex"
    output_path.write_text(
        render_discussion_tex(state.metadata, plan_text, introduction_text, results_text, citation_rows),
        encoding="utf-8",
    )

    update_stage_status(state.path, "discussion", "draft")
    _set_discussion_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "discussion": str(output_path),
        "citation_count": len(citation_rows),
        "outputs": DISCUSSION_OUTPUTS,
    }
