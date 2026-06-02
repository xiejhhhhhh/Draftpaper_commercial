from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.discussion import write_discussion
from draftpaper_cli.introduction import write_introduction
from draftpaper_cli.journal_profile import resolve_journal_template
from draftpaper_cli.latex_assembly import assemble_latex
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


def prepared_assembled_project(tmp: str) -> Path:
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
    assemble_latex(project.path)
    return project.path


def _write_aas_html(base: Path) -> Path:
    path = base / "aas_template.html"
    path.write_text(
        "<html><body><pre>\\documentclass[linenumbers,trackchanges]{aastex701}\n\\submitjournal{ApJS}\n\\begin{document}\n\\title{%%DRAFTPAPER_TITLE%%}\n%%DRAFTPAPER_SECTIONS%%\n\\bibliography{library}{ }\n\\bibliographystyle{aasjournal}\n\\end{document}</pre></body></html>",
        encoding="utf-8",
    )
    return path


class QualityGateUpgradeTests(unittest.TestCase):
    def test_quality_check_passes_for_complete_assembled_project(self) -> None:
        from draftpaper_cli.quality_gate import run_quality_check

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_assembled_project(tmp)

            report = run_quality_check(project_path)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["error_count"], 0)
            self.assertTrue((project_path / "quality_checks" / "quality_report.json").exists())
            self.assertIn("project", report)
            self.assertEqual(report["project"]["validation_status"], "passed")
            self.assertEqual(report["methods"]["run_manifest_status"], "success")
            self.assertEqual(report["results"]["citation_command_count"], 0)
            self.assertEqual(report["bibliography"]["missing_citation_keys"], [])

            manifest = json.loads((project_path / "quality_checks" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertIn("latex/main.tex", manifest["input_files"])
            self.assertIn("quality_checks/quality_report.json", manifest["output_files"])

    def test_quality_check_fails_when_latex_or_inputs_are_stale(self) -> None:
        from draftpaper_cli.quality_gate import run_quality_check

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_assembled_project(tmp)
            update_stage_status(project_path, "results", "stale")

            report = run_quality_check(project_path)

            self.assertEqual(report["status"], "failed")
            codes = {issue["code"] for issue in report["issues"]}
            self.assertIn("stale_stage_in_final_latex", codes)

    def test_quality_check_fails_results_citations_and_missing_artifacts(self) -> None:
        from draftpaper_cli.quality_gate import run_quality_check

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_assembled_project(tmp)
            results_tex = project_path / "results" / "results.tex"
            results_tex.write_text(results_tex.read_text(encoding="utf-8") + "\nUnsupported citation \\citep{Smith2024Transformer1}.\n", encoding="utf-8")
            (project_path / "results" / "figures" / "risk_curve.png").unlink()

            report = run_quality_check(project_path)

            self.assertEqual(report["status"], "failed")
            codes = {issue["code"] for issue in report["issues"]}
            self.assertIn("results_contains_citation", codes)
            self.assertIn("result_artifact_missing", codes)

    def test_quality_check_fails_missing_bibtex_key_and_untraced_citation(self) -> None:
        from draftpaper_cli.quality_gate import run_quality_check

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_assembled_project(tmp)
            main_tex = project_path / "latex" / "main.tex"
            main_tex.write_text(main_tex.read_text(encoding="utf-8").replace("\\bibliography{library}", "Extra citation \\citep{Unknown2026}.\n\\bibliography{library}"), encoding="utf-8")
            discussion = project_path / "discussion" / "discussion.tex"
            discussion.write_text(discussion.read_text(encoding="utf-8") + "\nUntraced citation \\citep{Unknown2026}.\n", encoding="utf-8")

            report = run_quality_check(project_path)

            self.assertEqual(report["status"], "failed")
            codes = {issue["code"] for issue in report["issues"]}
            self.assertIn("citation_key_missing", codes)
            self.assertIn("citation_not_in_evidence_table", codes)

    def test_quality_check_warns_when_context_references_are_not_cited_in_matching_sections(self) -> None:
        from draftpaper_cli.quality_gate import run_quality_check

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_assembled_project(tmp)
            evidence = project_path / "references" / "citation_evidence.csv"
            evidence.write_text(
                evidence.read_text(encoding="utf-8")
                + "Smith2024Transformer1,data,data background,Data support,semantic_scholar,10.1000/agn.2024.1,https://example.org/agn-transformer\n"
                + "Lee2023Multimodal1,methods,method background,Method support,arxiv,,https://arxiv.org/abs/2301.00001\n",
                encoding="utf-8",
            )

            report = run_quality_check(project_path)

            codes = {issue["code"] for issue in report["issues"]}
            self.assertIn("data_context_references_not_cited", codes)
            self.assertIn("methods_context_references_not_cited", codes)
            self.assertEqual(report["bibliography"]["section_context_citations"]["data"]["matched_citation_count"], 0)

    def test_cli_quality_check_writes_report_and_uses_exit_code_for_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_assembled_project(tmp)
            passed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "quality-check",
                    "--project",
                    str(project_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(passed.stdout)["status"], "passed")

            (project_path / "latex" / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            failed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "quality-check",
                    "--project",
                    str(project_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(json.loads(failed.stdout)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
