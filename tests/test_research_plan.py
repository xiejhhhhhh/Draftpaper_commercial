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


def write_generic_profile(project_path: Path, tmp: str) -> None:
    html = Path(tmp) / "journal.html"
    html.write_text("<html><body><pre>\\documentclass{article}\\n\\begin{document}\\n%%DRAFTPAPER_SECTIONS%%\\n%%DRAFTPAPER_BIBLIOGRAPHY%%\\n\\end{document}</pre></body></html>", encoding="utf-8")
    resolve_journal_template(project_path, target_journal="General Academic Journal", from_html=html)


class ResearchPlanTests(unittest.TestCase):
    def test_generate_research_plan_requires_references_outputs(self) -> None:
        from draftpaper_cli.research_plan import MissingReferencesError, generate_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN outburst prediction", field="machine learning astronomy")

            with self.assertRaises(MissingReferencesError):
                generate_research_plan(project.path)

    def test_generate_research_plan_uses_literature_evidence_and_writes_outputs(self) -> None:
        from draftpaper_cli.research_plan import generate_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Long-term AGN outburst prediction using multimodal survey data",
                field="machine learning astronomy",
                target_journal="General Academic Journal",
            )
            write_reference_outputs(project.path, SAMPLE_ITEMS, query="AGN outburst prediction")
            write_generic_profile(project.path, tmp)

            result = generate_research_plan(project.path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["citation_count"], 2)
            self.assertTrue((project.path / "research_plan" / "research_plan.md").exists())
            self.assertTrue((project.path / "research_plan" / "research_questions.md").exists())
            self.assertTrue((project.path / "research_plan" / "target_journal_anchor_papers.json").exists())
            self.assertTrue((project.path / "research_plan" / "novelty_overlap_report.md").exists())

            plan = (project.path / "research_plan" / "research_plan.md").read_text(encoding="utf-8")
            self.assertIn("Long-term AGN outburst prediction", plan)
            self.assertIn("Smith2024Transformer1", plan)
            self.assertIn("external validation", plan)
            self.assertIn("Research Questions", plan)
            self.assertIn("Data Requirements", plan)
            self.assertIn("Method Route", plan)
            self.assertIn("Target-Journal Anchor Literature", plan)
            self.assertIn("Risks and User Confirmation", plan)

            questions = (project.path / "research_plan" / "research_questions.md").read_text(encoding="utf-8")
            self.assertIn("RQ1", questions)
            self.assertIn("multimodal", questions.lower())

            manifest = json.loads((project.path / "research_plan" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertFalse(manifest["stale"])
            self.assertIn("references/citation_evidence.csv", manifest["input_files"])
            self.assertIn("research_plan/target_journal_anchor_papers.json", manifest["output_files"])
            self.assertIn("research_plan/research_plan.md", manifest["output_files"])

            project_json = json.loads((project.path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["research_plan"]["status"], "draft")
            self.assertEqual(project_json["stages"]["introduction"]["status"], "stale")

    def test_cli_generate_plan_writes_research_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN outburst prediction", field="machine learning astronomy")
            write_reference_outputs(project.path, SAMPLE_ITEMS, query="AGN outburst prediction")
            write_generic_profile(project.path, tmp)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "generate-plan",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["research_plan"]).exists())
            self.assertTrue(Path(payload["research_questions"]).exists())

    def test_cli_generate_plan_returns_blocked_high_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX",
                field="machine learning astronomy",
                target_journal="APJS",
            )
            write_generic_profile(project.path, tmp)
            write_reference_outputs(project.path, [{
                "title": "Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX",
                "authors": ["A. Similar"],
                "year": "2026",
                "abstract": "Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX.",
                "publication": "Astrophysical Journal Supplement Series",
                "citation_count": 5,
                "source": "semantic_scholar",
            }], query="Einstein Probe X-ray transient classification")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "generate-plan",
                    "--project",
                    str(project.path),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 3)
            payload = json.loads(completed.stderr)
            self.assertEqual(payload["status"], "blocked_high_similarity")
            self.assertTrue(Path(payload["novelty_overlap_report"]).exists())

    def test_generate_research_plan_blocks_when_prior_paper_is_too_similar(self) -> None:
        from draftpaper_cli.research_plan import NoveltyOverlapError, generate_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX",
                field="machine learning astronomy",
                target_journal="APJS",
            )
            write_generic_profile(project.path, tmp)
            very_similar = [{
                "title": "Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX",
                "authors": ["A. Similar"],
                "year": "2026",
                "abstract": "Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX.",
                "publication": "Astrophysical Journal Supplement Series",
                "citation_count": 5,
                "source": "semantic_scholar",
            }]
            write_reference_outputs(project.path, very_similar, query="Einstein Probe X-ray transient classification")

            with self.assertRaises(NoveltyOverlapError):
                generate_research_plan(project.path)

            report = json.loads((project.path / "research_plan" / "novelty_overlap_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["high_similarity_found"])

            result = generate_research_plan(project.path, allow_high_similarity=True)
            self.assertEqual(result["status"], "written")


if __name__ == "__main__":
    unittest.main()
