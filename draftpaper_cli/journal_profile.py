from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


OVERLEAF_TEMPLATE_SEARCH = "https://www.overleaf.com/latex/templates"
APJS_OVERLEAF_URL = "https://www.overleaf.com/latex/templates/aastex-template-for-submissions-to-aas-journals-apj-aj-apjs-apjl-psj-rnaas/vwyggrqvhcgz"

JOURNAL_PROFILE_INPUTS = [
    "idea/idea.md",
]

JOURNAL_PROFILE_OUTPUTS = [
    "journal_profile/journal_profile.json",
    "journal_profile/journal_guidelines.md",
    "journal_profile/template_source.html",
    "journal_profile/template_main.tex",
    "latex/template/main.tex",
]


class JournalProfileError(RuntimeError):
    """Raised when target journal template resolution cannot produce a usable profile."""


def _fetch_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "DraftPaper CLI local workflow"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _target_to_overleaf_url(target_journal: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", (target_journal or "").lower()).strip()
    if normalized in {"apjs", "apj supplement", "apj supplements", "astrophysical journal supplement", "astrophysical journal supplement series"}:
        return APJS_OVERLEAF_URL
    if normalized in {"apj", "aj", "apjl", "psj", "rnaas", "aas", "aas journals"}:
        return APJS_OVERLEAF_URL
    return None


def _search_overleaf_url(target_journal: str) -> str | None:
    mapped = _target_to_overleaf_url(target_journal)
    if mapped:
        return mapped
    query = urllib.parse.urlencode({"q": target_journal})
    try:
        html = _fetch_text(f"{OVERLEAF_TEMPLATE_SEARCH}?{query}")
    except Exception:
        return None
    match = re.search(r'href="(/latex/templates/[^"#?]+/[a-zA-Z0-9]+)"', html)
    return "https://www.overleaf.com" + match.group(1) if match else None


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "\n", text)
    return unescape(text)


def _extract_source_tex(source_html: str) -> str:
    text = _strip_tags(source_html)
    start = text.find("%% Beginning of file")
    if start == -1:
        start = text.find("\\documentclass")
    if start == -1:
        return ""
    end_match = re.search(r"\\end\{document\}", text[start:])
    end = start + end_match.end() if end_match else len(text)
    raw = text[start:end]
    lines = [re.sub(r"^\s{2,}", "", line.rstrip()) for line in raw.splitlines()]
    cleaned = "\n".join(line for line in lines if line.strip())
    return cleaned.strip() + "\n" if cleaned.strip() else ""


def _detect_documentclass(tex: str) -> str:
    match = re.search(r"\\documentclass(?:\[[^\]]+\])?\{([^}]+)\}", tex)
    return match.group(1) if match else ""


def _detect_bibliography_style(tex: str, documentclass: str) -> str:
    match = re.search(r"\\bibliographystyle\{([^}]+)\}", tex)
    if match:
        return match.group(1)
    if "aastex" in documentclass:
        return "aasjournal"
    return "plainnat"


def _journal_code(target_journal: str) -> str:
    normalized = (target_journal or "").upper()
    if "APJS" in normalized or "SUPPLEMENT" in normalized:
        return "ApJS"
    if "APJL" in normalized:
        return "ApJL"
    if normalized in {"APJ", "AJ", "PSJ", "RNAAS"}:
        return normalized
    return target_journal or "Target Journal"


def _render_aas_template(project_meta: dict[str, Any], target_journal: str) -> str:
    journal_code = _journal_code(target_journal)
    return "\n".join([
        r"\documentclass[linenumbers,trackchanges]{aastex701}",
        r"\graphicspath{{../}}",
        f"\\submitjournal{{{journal_code}}}",
        "",
        r"\begin{document}",
        "",
        r"\title{%%DRAFTPAPER_TITLE%%}",
        "",
        r"\author{Draft Author}",
        r"\affiliation{Draft affiliation}",
        r"\email{author@example.com}",
        "",
        r"\begin{abstract}",
        r"This draft abstract is a placeholder. AAS journal submissions require a concise abstract; ApJ, AJ, ApJS, ApJL, and PSJ use a 250 word limit, while RNAAS uses a 150 word limit.",
        r"\end{abstract}",
        "",
        r"\keywords{High energy astrophysics --- Time domain astronomy --- Machine learning}",
        "",
        r"%%DRAFTPAPER_SECTIONS%%",
        "",
        r"\bibliography{library}{ }",
        r"\bibliographystyle{aasjournal}",
        "",
        r"\end{document}",
        "",
    ])


def _render_generic_template(project_meta: dict[str, Any]) -> str:
    return "\n".join([
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{natbib}",
        r"\usepackage{xurl}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\graphicspath{{../}}",
        "",
        r"\title{%%DRAFTPAPER_TITLE%%}",
        r"\author{}",
        r"\date{}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
        r"%%DRAFTPAPER_SECTIONS%%",
        "",
        r"%%DRAFTPAPER_BIBLIOGRAPHY%%",
        "",
        r"\end{document}",
        "",
    ])


def _render_profile(
    *,
    project_meta: dict[str, Any],
    target_journal: str,
    source_type: str,
    source_url: str,
    source_html: str,
    source_tex: str,
    guideline_text: str,
) -> tuple[dict[str, Any], str]:
    documentclass = _detect_documentclass(source_tex)
    if not source_tex:
        if _target_to_overleaf_url(target_journal):
            source_tex = _render_aas_template(project_meta, target_journal)
            documentclass = "aastex701"
        else:
            source_tex = _render_generic_template(project_meta)
            documentclass = "article"
    bibliography_style = _detect_bibliography_style(source_tex, documentclass)
    is_aas = "aastex" in documentclass.lower() or "aas journal" in guideline_text.lower() or "aas journals" in source_html.lower()
    profile = {
        "project_id": project_meta.get("project_id"),
        "target_journal": target_journal,
        "source_type": source_type,
        "source_url": source_url,
        "documentclass": documentclass,
        "bibliography_style": bibliography_style,
        "template_main": "journal_profile/template_main.tex",
        "latex_template": "latex/template/main.tex",
        "requires_template": True,
        "rules": {
            "abstract_word_limit": 250 if is_aas else None,
            "rnaas_abstract_word_limit": 150 if is_aas else None,
            "requires_linenumbers": bool(is_aas),
            "requires_keywords": bool(is_aas),
            "keywords_system": "Unified Astronomy Thesaurus" if is_aas else "",
            "requires_submitjournal": bool(is_aas),
            "figure_guidance": "Use AASTeX figure environments and project-relative figure paths." if is_aas else "Use the target journal template figure conventions.",
            "table_guidance": "Use AASTeX table or deluxetable conventions where appropriate." if is_aas else "Use the target journal template table conventions.",
            "writing_scope": "Follow the target journal template before drafting Introduction, Methods, Results, Discussion, and final LaTeX.",
        },
    }
    guidelines = [
        "# Journal Guidelines",
        "",
        f"Target journal: {target_journal}",
        "",
        f"Source type: {source_type}",
        "",
        f"Source URL: {source_url or 'local/manual'}",
        "",
        f"LaTeX document class: `{documentclass}`",
        "",
        f"Bibliography style: `{bibliography_style}`",
        "",
        "## Formatting Rules",
        "",
    ]
    for key, value in profile["rules"].items():
        guidelines.append(f"- {key}: {value}")
    if guideline_text.strip():
        guidelines.extend(["", "## Source Notes", "", guideline_text.strip()[:4000]])
    return profile, "\n".join(guidelines) + "\n"


def _set_journal_profile_manifest(project_path: Path) -> None:
    manifest_path = project_path / "journal_profile" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = JOURNAL_PROFILE_INPUTS
    manifest["output_files"] = JOURNAL_PROFILE_OUTPUTS
    _write_json(manifest_path, manifest)


def resolve_journal_template(
    project: str | Path,
    *,
    target_journal: str | None = None,
    overleaf_url: str | None = None,
    guideline_url: str | None = None,
    from_html: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve a target journal's writing and LaTeX constraints into local artifacts."""
    state = load_project(project)
    journal = (target_journal or state.metadata.get("target_journal") or "General Academic Journal").strip()
    source_url = (overleaf_url or "").strip()
    source_type = "overleaf"
    if not source_url and guideline_url:
        source_url = guideline_url.strip()
        source_type = "guideline_url"
    if not source_url and not from_html:
        source_url = _search_overleaf_url(journal) or ""
        if not source_url:
            raise JournalProfileError(
                "No Overleaf template was found for the target journal. Provide --overleaf-url or --guideline-url."
            )

    if from_html:
        source_html = Path(from_html).read_text(encoding="utf-8-sig")
        source_type = "local_html"
    else:
        try:
            source_html = _fetch_text(source_url)
        except Exception as exc:
            raise JournalProfileError(f"Failed to fetch journal template or guideline page: {source_url}") from exc
    source_tex = _extract_source_tex(source_html)
    guideline_text = _strip_tags(source_html)
    profile, guidelines = _render_profile(
        project_meta=state.metadata,
        target_journal=journal,
        source_type=source_type,
        source_url=source_url,
        source_html=source_html,
        source_tex=source_tex,
        guideline_text=guideline_text,
    )
    template_tex = source_tex or (_render_aas_template(state.metadata, journal) if _target_to_overleaf_url(journal) else _render_generic_template(state.metadata))
    if "%%DRAFTPAPER_SECTIONS%%" not in template_tex:
        template_tex = _render_aas_template(state.metadata, journal) if "aastex" in profile["documentclass"].lower() else _render_generic_template(state.metadata)

    journal_dir = state.path / "journal_profile"
    journal_dir.mkdir(parents=True, exist_ok=True)
    (journal_dir / "template_source.html").write_text(source_html, encoding="utf-8")
    (journal_dir / "template_main.tex").write_text(template_tex, encoding="utf-8")
    _write_json(journal_dir / "journal_profile.json", profile)
    (journal_dir / "journal_guidelines.md").write_text(guidelines, encoding="utf-8")
    latex_template_dir = state.path / "latex" / "template"
    latex_template_dir.mkdir(parents=True, exist_ok=True)
    (latex_template_dir / "main.tex").write_text(template_tex, encoding="utf-8")

    if state.metadata.get("target_journal") != journal:
        state.metadata["target_journal"] = journal
        _write_json(state.path / "project.json", state.metadata)
    update_stage_status(state.path, "journal_profile", "draft")
    _set_journal_profile_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "target_journal": journal,
        "source_type": source_type,
        "source_url": source_url,
        "documentclass": profile["documentclass"],
        "journal_profile": str(journal_dir / "journal_profile.json"),
        "journal_guidelines": str(journal_dir / "journal_guidelines.md"),
        "latex_template": str(latex_template_dir / "main.tex"),
        "outputs": JOURNAL_PROFILE_OUTPUTS,
    }


def validate_journal_profile_for_writing(project_path: Path) -> dict[str, Any]:
    """Return journal profile if writing/assembly may use it; otherwise raise."""
    state = load_project(project_path)
    stage = (state.metadata.get("stages") or {}).get("journal_profile") or {}
    if stage.get("stale") or stage.get("status") not in {"draft", "approved", "completed"}:
        raise JournalProfileError("A current journal_profile stage is required before journal-constrained writing or LaTeX assembly.")
    profile_path = project_path / "journal_profile" / "journal_profile.json"
    if not profile_path.exists():
        raise JournalProfileError("journal_profile/journal_profile.json is required.")
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise JournalProfileError("journal_profile/journal_profile.json is invalid JSON.") from exc
    return profile if isinstance(profile, dict) else {}
