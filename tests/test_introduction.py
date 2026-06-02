from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.journal_profile import resolve_journal_template
from draftpaper_cli.references import write_reference_outputs
from draftpaper_cli.research_plan import generate_research_plan


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
    html = Path(tmp) / "journal.html"
    html.write_text("<html><body><pre>\\documentclass{article}\\n\\begin{document}\\n%%DRAFTPAPER_SECTIONS%%\\n%%DRAFTPAPER_BIBLIOGRAPHY%%\\n\\end{document}</pre></body></html>", encoding="utf-8")
    resolve_journal_template(project.path, target_journal="General Academic Journal", from_html=html)
    generate_research_plan(project.path)
    return project.path


class IntroductionTests(unittest.TestCase):
    def test_write_introduction_requires_research_plan_and_references(self) -> None:
        from draftpaper_cli.introduction import MissingIntroductionInputsError, write_introduction

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="No plan yet", field="workflow engineering")

            with self.assertRaises(MissingIntroductionInputsError):
                write_introduction(project.path)

    def test_write_introduction_creates_latex_with_traceable_citations(self) -> None:
        from draftpaper_cli.introduction import write_introduction

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            result = write_introduction(project_path)

            self.assertEqual(result["status"], "written")
            tex_path = project_path / "introduction" / "introduction.tex"
            self.assertTrue(tex_path.exists())
            tex = tex_path.read_text(encoding="utf-8")

            self.assertTrue(tex.startswith("\\section{Introduction}"))
            self.assertIn("\\citep{Smith2024Transformer1}", tex)
            self.assertIn("\\citep{Lee2023Multimodal2}", tex)
            self.assertIn("external validation", tex)
            self.assertNotIn("\\textbf", tex)
            self.assertNotIn("\\begin{itemize}", tex)
            self.assertNotIn("As an AI", tex)

            manifest = json.loads((project_path / "introduction" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertFalse(manifest["stale"])
            self.assertIn("research_plan/research_plan.md", manifest["input_files"])
            self.assertIn("references/citation_evidence.csv", manifest["input_files"])
            self.assertIn("introduction/introduction.tex", manifest["output_files"])

            project_json = json.loads((project_path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["introduction"]["status"], "draft")
            self.assertEqual(project_json["stages"]["discussion"]["status"], "stale")

    def test_cli_write_introduction_outputs_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "write-introduction",
                    "--project",
                    str(project_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["introduction"]).exists())


if __name__ == "__main__":
    unittest.main()
