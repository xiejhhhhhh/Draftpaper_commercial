from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.discussion import write_discussion
from draftpaper_cli.introduction import write_introduction
from draftpaper_cli.journal_profile import resolve_journal_template
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.methods import verify_methods, write_methods
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import update_stage_status
from draftpaper_cli.references import write_reference_outputs
from draftpaper_cli.research_plan import generate_research_plan
from draftpaper_cli.result_validity import assess_result_validity
from draftpaper_cli.results import inventory_results, write_results


SAMPLE_ITEMS = [
    {
        "title": "Transformer models for active galactic nuclei outburst prediction",
        "authors": ["Jane Smith", "Alan Chen"],
        "year": "2024",
        "doi": "10.1000/agn.2024.1",
        "url": "https://example.org/agn-transformer",
        "abstract": "Existing models lack external validation for long-term outburst prediction in active galactic nuclei.",
        "publication": "Journal of Astroinformatics",
        "citation_count": 42,
        "source": "semantic_scholar",
    },
    {
        "title": "Multimodal survey data for time-domain astronomy",
        "authors": ["Maria Lee"],
        "year": "2023",
        "doi": "",
        "url": "https://arxiv.org/abs/2301.00001",
        "abstract": "Multimodal photometric and spectroscopic survey data improve time-domain event characterization.",
        "publication": "arXiv",
        "citation_count": 7,
        "source": "arxiv",
    },
]


def prepared_project(tmp: str) -> Path:
    project = create_project(
        root=tmp,
        idea="Long-term AGN outburst prediction using multimodal survey data",
        field="machine learning astronomy",
        target_journal="General Academic Journal",
    )
    write_reference_outputs(project.path, SAMPLE_ITEMS, query="AGN outburst prediction")
    resolve_journal_template(project.path, target_journal="APJS", from_html=_write_aas_html(Path(tmp)))
    generate_research_plan(project.path)
    write_introduction(project.path)
    (project.path / "data" / "data.tex").write_text(
        "\\section{Data}\nThe study uses locally prepared multimodal survey data.\n",
        encoding="utf-8",
    )
    rows = "\n".join(f"{i},{i % 2},0.{i % 10}" for i in range(1, 41))
    (project.path / "data" / "raw" / "sample.csv").write_text("id,target,value\n" + rows + "\n", encoding="utf-8")
    inventory_data(project.path)
    assess_data_quality(project.path, required_columns=["id", "target"])
    assess_data_feasibility(project.path, min_rows=30)
    update_stage_status(project.path, "data", "draft")
    collect_method_plan(project.path, user_method="Use supervised multimodal classification.", primary_metric="f1", minimum_primary_metric=0.7)
    output = project.path / "results" / "tables" / "metrics.csv"
    figure = project.path / "results" / "figures" / "risk_curve.png"
    command = (
        f"{sys.executable} -c \"from pathlib import Path; "
        f"Path(r'{output}').write_text('metric,value\\nf1,0.88\\n', encoding='utf-8'); "
        f"Path(r'{figure}').write_bytes(b'fake image')\""
    )
    verify_methods(
        project.path,
        command=command,
        output_files=["results/tables/metrics.csv", "results/figures/risk_curve.png"],
    )
    write_methods(project.path)
    assess_result_validity(project.path)
    inventory_results(project.path)
    write_results(project.path)
    write_discussion(project.path)
    return project.path


def _write_aas_html(base: Path) -> Path:
    path = base / "aas_template.html"
    path.write_text(
        "<html><body><pre>\\documentclass[linenumbers,trackchanges]{aastex701}\n\\submitjournal{ApJS}\n\\begin{document}\n\\title{%%DRAFTPAPER_TITLE%%}\n%%DRAFTPAPER_SECTIONS%%\n\\bibliography{library}{ }\n\\bibliographystyle{aasjournal}\n\\end{document}</pre></body></html>",
        encoding="utf-8",
    )
    return path


class LatexAssemblyTests(unittest.TestCase):
    def test_assemble_latex_requires_all_sections_and_bibtex(self) -> None:
        from draftpaper_cli.latex_assembly import LatexAssemblyError, assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="No sections yet", field="workflow engineering")

            with self.assertRaises(LatexAssemblyError):
                assemble_latex(project.path)

    def test_assemble_latex_rejects_stale_input_stage(self) -> None:
        from draftpaper_cli.latex_assembly import LatexAssemblyError, assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            update_stage_status(project_path, "results", "stale")

            with self.assertRaises(LatexAssemblyError):
                assemble_latex(project_path)

    def test_assemble_latex_writes_main_sections_and_bibtex(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)

            result = assemble_latex(project_path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["section_count"], 5)
            main_tex = project_path / "latex" / "main.tex"
            library = project_path / "latex" / "library.bib"
            self.assertTrue(main_tex.exists())
            self.assertTrue(library.exists())
            for name in ["introduction", "data", "methods", "results", "discussion"]:
                self.assertTrue((project_path / "latex" / "sections" / f"{name}.tex").exists())

            content = main_tex.read_text(encoding="utf-8")
            self.assertIn("\\documentclass", content)
            self.assertIn("\\graphicspath{{../}}", content)
            self.assertIn("\\input{sections/introduction}", content)
            self.assertIn("\\bibliography{library}", content)
            self.assertIn("Long-term AGN outburst prediction", content)

            manifest = json.loads((project_path / "latex" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertFalse(manifest["stale"])
            self.assertIn("discussion/discussion.tex", manifest["input_files"])
            self.assertIn("latex/main.tex", manifest["output_files"])

            project_json = json.loads((project_path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["latex"]["status"], "draft")
            self.assertEqual(project_json["stages"]["quality_checks"]["status"], "stale")

    def test_assemble_latex_rejects_citation_missing_from_bibtex(self) -> None:
        from draftpaper_cli.latex_assembly import LatexCitationError, assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            discussion = project_path / "discussion" / "discussion.tex"
            discussion.write_text(discussion.read_text(encoding="utf-8") + "\nMissing citation \\citep{Unknown2026}.\n", encoding="utf-8")

            with self.assertRaises(LatexCitationError):
                assemble_latex(project_path)

    def test_cli_assemble_latex_outputs_main_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assemble-latex",
                    "--project",
                    str(project_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["main_tex"]).exists())
            self.assertTrue(Path(payload["library_bib"]).exists())

    def test_compile_latex_pdf_skips_cleanly_without_engine(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex, compile_latex_pdf

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            assemble_latex(project_path)

            with patch.dict(os.environ, {"PATH": "", "LOCALAPPDATA": str(Path(tmp) / "no-localappdata")}):
                result = compile_latex_pdf(project_path)

            self.assertEqual(result["status"], "skipped")
            self.assertIsNone(result["pdf"])
            manifest = json.loads((project_path / "latex" / "pdf_compile_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "skipped")
            self.assertIn("no local LaTeX engine", manifest["message"])

    def test_compile_latex_pdf_uses_local_engine_and_writes_manifest(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex, compile_latex_pdf

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            assemble_latex(project_path)
            tool_dir = Path(tmp) / "tools"
            tool_dir.mkdir()
            xelatex = tool_dir / "xelatex.cmd"
            xelatex.write_text(
                "@echo off\r\n"
                "echo fake xelatex %* >> compile-tools.log\r\n"
                "echo PDF > main.pdf\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )
            bibtex = tool_dir / "bibtex.cmd"
            bibtex.write_text(
                "@echo off\r\n"
                "echo fake bibtex %* >> compile-tools.log\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )

            old_path = os.environ.get("PATH", "")
            with patch.dict(os.environ, {"PATH": str(tool_dir) + os.pathsep + old_path, "LOCALAPPDATA": str(Path(tmp) / "no-localappdata")}):
                result = compile_latex_pdf(project_path)

            self.assertEqual(result["status"], "success")
            self.assertTrue(Path(result["pdf"]).exists())
            self.assertTrue((project_path / "latex" / "main.compile.log").exists())
            manifest = json.loads((project_path / "latex" / "pdf_compile_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "success")
            self.assertIn("xelatex", manifest["engine"])

    def test_cli_assemble_latex_can_compile_pdf_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            tool_dir = Path(tmp) / "tools"
            tool_dir.mkdir()
            (tool_dir / "xelatex.cmd").write_text(
                "@echo off\r\n"
                "echo PDF > main.pdf\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )
            old_path = os.environ.get("PATH", "")
            env = os.environ.copy()
            env["PATH"] = str(tool_dir) + os.pathsep + old_path
            env["LOCALAPPDATA"] = str(Path(tmp) / "no-localappdata")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assemble-latex",
                    "--project",
                    str(project_path),
                    "--compile-pdf",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertEqual(payload["pdf_status"], "success")
            self.assertTrue(Path(payload["pdf"]).exists())


if __name__ == "__main__":
    unittest.main()
