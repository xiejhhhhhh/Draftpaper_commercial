from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.introduction import write_introduction
from draftpaper_cli.journal_profile import resolve_journal_template
from draftpaper_cli.project_scaffold import create_project
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
    (project.path / "results" / "figures" / "risk_curve.png").write_bytes(b"fake image")
    (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
    (project.path / "methods" / "method_requirements.json").write_text(
        json.dumps({"primary_metric": "f1", "minimum_primary_metric": 0.7, "method_data_fit": "proceed"}),
        encoding="utf-8",
    )
    (project.path / "data" / "data_feasibility_report.json").write_text(json.dumps({"decision": "pass"}), encoding="utf-8")
    (project.path / "methods" / "run_manifest.yaml").write_text(
        json.dumps({"status": "success", "output_files": ["results/tables/metrics.csv"], "metrics": {"f1": 0.88}}),
        encoding="utf-8",
    )
    assess_result_validity(project.path)
    inventory_results(project.path)
    write_results(project.path)
    return project.path


def _write_aas_html(base: Path) -> Path:
    path = base / "aas_template.html"
    path.write_text(
        "<html><body><pre>\\documentclass[linenumbers,trackchanges]{aastex701}\n\\submitjournal{ApJS}\n\\begin{document}\n\\title{%%DRAFTPAPER_TITLE%%}\n%%DRAFTPAPER_SECTIONS%%\n\\bibliography{library}{ }\n\\bibliographystyle{aasjournal}\n\\end{document}</pre></body></html>",
        encoding="utf-8",
    )
    return path


class DiscussionWriterTests(unittest.TestCase):
    def test_write_discussion_requires_prior_sections_and_references(self) -> None:
        from draftpaper_cli.discussion import MissingDiscussionInputsError, write_discussion

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="No evidence yet", field="workflow engineering")

            with self.assertRaises(MissingDiscussionInputsError):
                write_discussion(project.path)

    def test_write_discussion_creates_latex_with_traceable_citations(self) -> None:
        from draftpaper_cli.discussion import write_discussion

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)

            result = write_discussion(project_path)

            self.assertEqual(result["status"], "written")
            self.assertGreaterEqual(result["citation_count"], 2)
            tex_path = project_path / "discussion" / "discussion.tex"
            self.assertTrue(tex_path.exists())
            tex = tex_path.read_text(encoding="utf-8")

            self.assertTrue(tex.startswith("\\section{Discussion}"))
            self.assertIn("\\citep{Smith2024Transformer1}", tex)
            self.assertIn("\\citep{Lee2023Multimodal2}", tex)
            self.assertIn("external validation", tex)
            self.assertIn("Limitations", tex)
            self.assertNotIn("\\textbf", tex)
            self.assertNotIn("\\begin{itemize}", tex)
            self.assertNotIn("As an AI", tex)

            manifest = json.loads((project_path / "discussion" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertFalse(manifest["stale"])
            self.assertIn("introduction/introduction.tex", manifest["input_files"])
            self.assertIn("results/results.tex", manifest["input_files"])
            self.assertIn("references/citation_evidence.csv", manifest["input_files"])
            self.assertIn("discussion/discussion.tex", manifest["output_files"])

            project_json = json.loads((project_path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["discussion"]["status"], "draft")
            self.assertEqual(project_json["stages"]["latex"]["status"], "stale")

    def test_write_discussion_rejects_evidence_keys_missing_from_bibtex(self) -> None:
        from draftpaper_cli.discussion import DiscussionCitationIntegrityError, write_discussion

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            library = project_path / "references" / "library.bib"
            library.write_text(library.read_text(encoding="utf-8").replace("@article{Smith2024Transformer1", "@article{OtherKey"), encoding="utf-8")

            with self.assertRaises(DiscussionCitationIntegrityError):
                write_discussion(project_path)

    def test_cli_write_discussion_outputs_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "write-discussion",
                    "--project",
                    str(project_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["discussion"]).exists())


if __name__ == "__main__":
    unittest.main()
