from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .journal_profile import JournalProfileError, validate_journal_profile_for_writing
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


SECTION_INPUTS = [
    ("introduction", "introduction/introduction.tex"),
    ("data", "data/data.tex"),
    ("methods", "methods/methods.tex"),
    ("results", "results/results.tex"),
    ("discussion", "discussion/discussion.tex"),
]

LATEX_INPUTS = [relative for _name, relative in SECTION_INPUTS] + [
    "references/library.bib",
    "journal_profile/journal_profile.json",
    "latex/template/main.tex",
]

LATEX_OUTPUTS = [
    "latex/main.tex",
    "latex/library.bib",
    "latex/sections/introduction.tex",
    "latex/sections/data.tex",
    "latex/sections/methods.tex",
    "latex/sections/results.tex",
    "latex/sections/discussion.tex",
]

PDF_OUTPUTS = [
    "latex/main.pdf",
    "latex/main.compile.log",
    "latex/pdf_compile_manifest.json",
]

CITATION_PATTERN = re.compile(r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}", re.IGNORECASE)


class LatexAssemblyError(RuntimeError):
    """Raised when final LaTeX assembly would use incomplete or stale inputs."""


class LatexCitationError(LatexAssemblyError):
    """Raised when assembled LaTeX cites keys that are absent from library.bib."""


def _bibtex_keys(content: str) -> set[str]:
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", content))


def _latex_citation_keys(content: str) -> set[str]:
    keys: set[str] = set()
    for match in CITATION_PATTERN.finditer(content):
        for key in match.group(1).split(","):
            clean = key.strip()
            if clean:
                keys.add(clean)
    return keys


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


def _require_inputs(project_path: Path) -> None:
    missing = [relative for relative in LATEX_INPUTS if not (project_path / relative).exists()]
    if missing:
        raise LatexAssemblyError("LaTeX assembly requires all section files and library.bib. Missing: " + ", ".join(missing))


def _require_non_stale_input_stages(project_meta: dict[str, Any]) -> None:
    stale = []
    invalid_status = []
    stages = project_meta.get("stages") or {}
    for stage in ["introduction", "data", "method_plan", "methods", "result_validity", "results", "discussion", "references", "journal_profile"]:
        stage_meta = stages.get(stage) or {}
        if stage_meta.get("stale"):
            stale.append(stage)
        if stage_meta.get("status") not in {"draft", "approved", "completed"}:
            invalid_status.append(f"{stage}={stage_meta.get('status')}")
    if stale:
        raise LatexAssemblyError("Cannot assemble LaTeX while input stages are stale: " + ", ".join(stale))
    if invalid_status:
        raise LatexAssemblyError("Cannot assemble LaTeX before input stages are ready: " + ", ".join(invalid_status))


def _read_sections(project_path: Path) -> dict[str, str]:
    sections = {}
    for name, relative in SECTION_INPUTS:
        sections[name] = (project_path / relative).read_text(encoding="utf-8")
    return sections


def _validate_citations(project_path: Path, sections: dict[str, str]) -> tuple[set[str], set[str]]:
    bibtex = (project_path / "references" / "library.bib").read_text(encoding="utf-8")
    bib_keys = _bibtex_keys(bibtex)
    citation_keys: set[str] = set()
    for content in sections.values():
        citation_keys.update(_latex_citation_keys(content))
    missing = sorted(citation_keys - bib_keys)
    if missing:
        raise LatexCitationError("LaTeX cites keys that are missing from library.bib: " + ", ".join(missing))
    return citation_keys, bib_keys


def _copy_sections(project_path: Path, sections: dict[str, str]) -> list[str]:
    section_dir = project_path / "latex" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, content in sections.items():
        relative = f"latex/sections/{name}.tex"
        (project_path / relative).write_text(content, encoding="utf-8")
        outputs.append(relative)
    return outputs


def _copy_bibtex(project_path: Path) -> None:
    shutil.copyfile(project_path / "references" / "library.bib", project_path / "latex" / "library.bib")


def _render_default_main(project_meta: dict[str, Any]) -> str:
    title = _safe_latex_text(project_meta.get("title") or project_meta.get("idea") or "Draft Paper")
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
        f"\\title{{{title}}}",
        r"\author{}",
        r"\date{}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
        r"\input{sections/introduction}",
        r"\input{sections/data}",
        r"\input{sections/methods}",
        r"\input{sections/results}",
        r"\input{sections/discussion}",
        "",
        r"\bibliographystyle{plainnat}",
        r"\bibliography{library}",
        "",
        r"\end{document}",
        "",
    ])


def _render_main(project_path: Path, project_meta: dict[str, Any]) -> str:
    template_path = project_path / "latex" / "template" / "main.tex"
    if not template_path.exists():
        return _render_default_main(project_meta)
    template = template_path.read_text(encoding="utf-8")
    sections = "\n".join([
        r"\input{sections/introduction}",
        r"\input{sections/data}",
        r"\input{sections/methods}",
        r"\input{sections/results}",
        r"\input{sections/discussion}",
    ])
    journal_profile = _read_journal_profile(project_path)
    bibliography_style = journal_profile.get("bibliography_style") or "plainnat"
    if "aastex" in str(journal_profile.get("documentclass") or "").lower():
        bibliography = "\n".join([r"\bibliography{library}{ }", rf"\bibliographystyle{{{bibliography_style}}}"])
    else:
        bibliography = "\n".join([rf"\bibliographystyle{{{bibliography_style}}}", r"\bibliography{library}"])
    title = _safe_latex_text(project_meta.get("title") or project_meta.get("idea") or "Draft Paper")
    rendered = template.replace("%%DRAFTPAPER_TITLE%%", title)
    rendered = rendered.replace("%%DRAFTPAPER_SECTIONS%%", sections)
    rendered = rendered.replace("%%DRAFTPAPER_BIBLIOGRAPHY%%", bibliography)
    if "%%DRAFTPAPER_SECTIONS%%" not in template and "\\input{sections/" not in rendered:
        rendered = rendered.rstrip() + "\n\n" + sections + "\n"
    if "%%DRAFTPAPER_BIBLIOGRAPHY%%" not in template and "\\bibliography{" not in rendered:
        rendered = rendered.rstrip() + "\n\n" + bibliography + "\n"
    if "\\graphicspath" not in rendered:
        rendered = rendered.replace("\\begin{document}", "\\graphicspath{{../}}\n\\begin{document}", 1)
    return rendered.rstrip() + "\n"


def _read_journal_profile(project_path: Path) -> dict[str, Any]:
    path = project_path / "journal_profile" / "journal_profile.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _set_latex_manifest(project_path: Path) -> None:
    manifest_path = project_path / "latex" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = LATEX_INPUTS
    existing_outputs = manifest.get("output_files") or []
    pdf_outputs = [relative for relative in PDF_OUTPUTS if relative in existing_outputs or (project_path / relative).exists()]
    manifest["output_files"] = LATEX_OUTPUTS + [relative for relative in pdf_outputs if relative not in LATEX_OUTPUTS]
    _write_json(manifest_path, manifest)


def _find_latex_executable(names: list[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    candidate_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
        Path("C:/Program Files/MiKTeX/miktex/bin/x64"),
    ]
    for directory in candidate_dirs:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return str(candidate)
    return None


def _write_pdf_manifest(project_path: Path, payload: dict[str, Any]) -> None:
    _write_json(project_path / "latex" / "pdf_compile_manifest.json", payload)
    _set_latex_manifest(project_path)


def compile_latex_pdf(project: str | Path, *, timeout_seconds: int = 120) -> dict[str, Any]:
    """Compile latex/main.tex into latex/main.pdf when a local LaTeX engine is available."""
    state = load_project(project)
    tex_file = state.path / "latex" / "main.tex"
    bib_file = state.path / "latex" / "library.bib"
    log_file = state.path / "latex" / "main.compile.log"
    if not tex_file.exists():
        raise LatexAssemblyError("latex/main.tex is required before compiling a review PDF.")
    if not bib_file.exists():
        raise LatexAssemblyError("latex/library.bib is required before compiling a review PDF.")

    engine = _find_latex_executable(["xelatex", "xelatex.exe", "pdflatex", "pdflatex.exe"])
    if not engine:
        message = "Skipped PDF generation: no local LaTeX engine was found. Install MiKTeX or TeX Live and retry."
        manifest = {
            "status": "skipped",
            "message": message,
            "engine": None,
            "bibtex": None,
            "commands": [],
            "pdf": None,
            "log": str(log_file),
        }
        log_file.write_text(message + "\n", encoding="utf-8")
        _write_pdf_manifest(state.path, manifest)
        return {
            "status": "skipped",
            "project_path": str(state.path),
            "pdf": None,
            "compile_log": str(log_file),
            "pdf_compile_manifest": str(state.path / "latex" / "pdf_compile_manifest.json"),
            "message": message,
        }

    bibtex = _find_latex_executable(["bibtex", "bibtex.exe"])
    commands = [
        [engine, "-interaction=nonstopmode", "-halt-on-error", tex_file.name],
    ]
    if bibtex and bib_file.exists():
        commands.append([bibtex, tex_file.stem])
    commands.extend([
        [engine, "-interaction=nonstopmode", "-halt-on-error", tex_file.name],
        [engine, "-interaction=nonstopmode", "-halt-on-error", tex_file.name],
    ])

    command_reports: list[dict[str, Any]] = []
    log_chunks: list[str] = []
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                cwd=tex_file.parent,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except Exception as exc:
            message = f"PDF generation failed while running {' '.join(command)}: {exc}"
            command_reports.append({"command": command, "returncode": None, "error": str(exc)})
            log_chunks.append(message)
            log_file.write_text("\n\n".join(log_chunks), encoding="utf-8")
            manifest = {
                "status": "failed",
                "message": message,
                "engine": str(engine),
                "bibtex": str(bibtex) if bibtex else None,
                "commands": command_reports,
                "pdf": None,
                "log": str(log_file),
            }
            _write_pdf_manifest(state.path, manifest)
            return {
                "status": "failed",
                "project_path": str(state.path),
                "pdf": None,
                "compile_log": str(log_file),
                "pdf_compile_manifest": str(state.path / "latex" / "pdf_compile_manifest.json"),
                "message": message,
            }
        command_reports.append({"command": command, "returncode": completed.returncode})
        log_chunks.append(
            f"$ {' '.join(command)}\n"
            f"exit={completed.returncode}\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}"
        )
        if completed.returncode != 0:
            message = f"PDF generation failed while running {' '.join(command)}. See {log_file.name}."
            log_file.write_text("\n\n".join(log_chunks), encoding="utf-8")
            manifest = {
                "status": "failed",
                "message": message,
                "engine": str(engine),
                "bibtex": str(bibtex) if bibtex else None,
                "commands": command_reports,
                "pdf": None,
                "log": str(log_file),
            }
            _write_pdf_manifest(state.path, manifest)
            return {
                "status": "failed",
                "project_path": str(state.path),
                "pdf": None,
                "compile_log": str(log_file),
                "pdf_compile_manifest": str(state.path / "latex" / "pdf_compile_manifest.json"),
                "message": message,
            }

    log_file.write_text("\n\n".join(log_chunks), encoding="utf-8")
    pdf_file = tex_file.with_suffix(".pdf")
    status = "success" if pdf_file.exists() else "failed"
    message = (
        f"PDF generated successfully using {Path(engine).name}."
        if pdf_file.exists()
        else f"PDF generation finished but {pdf_file.name} was not created. See {log_file.name}."
    )
    manifest = {
        "status": status,
        "message": message,
        "engine": str(engine),
        "bibtex": str(bibtex) if bibtex else None,
        "commands": command_reports,
        "pdf": str(pdf_file) if pdf_file.exists() else None,
        "log": str(log_file),
    }
    _write_pdf_manifest(state.path, manifest)
    return {
        "status": status,
        "project_path": str(state.path),
        "pdf": str(pdf_file) if pdf_file.exists() else None,
        "compile_log": str(log_file),
        "pdf_compile_manifest": str(state.path / "latex" / "pdf_compile_manifest.json"),
        "message": message,
    }


def assemble_latex(project: str | Path, *, compile_pdf: bool = False) -> dict[str, Any]:
    """Assemble staged manuscript sections into latex/main.tex and latex/library.bib."""
    state = load_project(project)
    try:
        validate_journal_profile_for_writing(state.path)
    except JournalProfileError as exc:
        raise LatexAssemblyError(str(exc)) from exc
    _require_inputs(state.path)
    _require_non_stale_input_stages(state.metadata)
    sections = _read_sections(state.path)
    citation_keys, bib_keys = _validate_citations(state.path, sections)
    latex_dir = state.path / "latex"
    latex_dir.mkdir(parents=True, exist_ok=True)
    _copy_sections(state.path, sections)
    _copy_bibtex(state.path)
    main_tex = latex_dir / "main.tex"
    main_tex.write_text(_render_main(state.path, state.metadata), encoding="utf-8")

    update_stage_status(state.path, "latex", "draft")
    _set_latex_manifest(state.path)
    result = {
        "status": "written",
        "project_path": str(state.path),
        "main_tex": str(main_tex),
        "library_bib": str(latex_dir / "library.bib"),
        "section_count": len(sections),
        "citation_count": len(citation_keys),
        "bibtex_entry_count": len(bib_keys),
        "outputs": LATEX_OUTPUTS,
    }
    if compile_pdf:
        pdf_result = compile_latex_pdf(state.path)
        result["pdf_status"] = pdf_result["status"]
        result["pdf"] = pdf_result["pdf"]
        result["compile_log"] = pdf_result["compile_log"]
        result["pdf_compile_manifest"] = pdf_result["pdf_compile_manifest"]
        result["pdf_message"] = pdf_result["message"]
    return result
