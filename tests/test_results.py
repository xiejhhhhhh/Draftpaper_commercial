from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def prepare_passing_result_validity(project_path: Path) -> None:
    from draftpaper_cli.result_validity import assess_result_validity

    (project_path / "methods" / "method_requirements.json").write_text(
        json.dumps({"primary_metric": "f1", "minimum_primary_metric": 0.7, "method_data_fit": "proceed"}),
        encoding="utf-8",
    )
    (project_path / "data" / "data_feasibility_report.json").write_text(
        json.dumps({"decision": "pass"}),
        encoding="utf-8",
    )
    (project_path / "methods" / "run_manifest.yaml").write_text(
        json.dumps({
            "status": "success",
            "output_files": ["results/tables/metrics.csv"],
            "metrics": {"f1": 0.88},
        }),
        encoding="utf-8",
    )
    assess_result_validity(project_path)


class ResultsManifestWriterTests(unittest.TestCase):
    def test_inventory_results_writes_manifest_for_existing_figures_and_tables(self) -> None:
        from draftpaper_cli.results import inventory_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Result manifest test", field="workflow engineering")
            (project.path / "results" / "figures" / "fig1.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\naccuracy,0.91\n", encoding="utf-8")

            result = inventory_results(project.path)

            self.assertEqual(result["status"], "written")
            manifest_path = project.path / "results" / "result_manifest.yaml"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["figures"][0]["path"], "results/figures/fig1.png")
            self.assertEqual(manifest["tables"][0]["path"], "results/tables/metrics.csv")
            self.assertIn("result_claim", manifest["figures"][0])

    def test_write_results_requires_manifest_and_existing_files(self) -> None:
        from draftpaper_cli.results import ResultsGateError, write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Missing result test", field="workflow engineering")

            with self.assertRaises(ResultsGateError):
                write_results(project.path)

            (project.path / "results" / "result_manifest.yaml").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "fig1",
                            "path": "results/figures/missing.png",
                            "caption_draft": "Missing figure",
                            "result_claim": "A missing result cannot support text.",
                        }
                    ],
                    "tables": [],
                }),
                encoding="utf-8",
            )
            with self.assertRaises(ResultsGateError):
                write_results(project.path)

    def test_write_results_creates_latex_without_citations_and_inserts_figures_at_subsection_end(self) -> None:
        from draftpaper_cli.results import inventory_results, write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN prediction results", field="machine learning astronomy")
            (project.path / "results" / "figures" / "risk_curve.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            inventory_results(project.path)

            result = write_results(project.path)

            self.assertEqual(result["status"], "written")
            tex_path = project.path / "results" / "results.tex"
            tex = tex_path.read_text(encoding="utf-8")
            self.assertTrue(tex.startswith("\\section{Results}"))
            self.assertIn("\\includegraphics", tex)
            self.assertIn("results/figures/risk_curve.png", tex)
            self.assertIn("results/tables/metrics.csv", tex)
            self.assertNotIn("\\cite", tex)
            self.assertLess(tex.index("risk_curve.png"), tex.index("\\end{figure}"))

            manifest = json.loads((project.path / "results" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertIn("results/result_validity_report.json", manifest["input_files"])
            self.assertIn("results/result_manifest.yaml", manifest["input_files"])
            self.assertIn("results/results.tex", manifest["output_files"])

    def test_write_results_rejects_citation_in_manifest_claim(self) -> None:
        from draftpaper_cli.results import ResultsGateError, write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Citation rejection", field="workflow engineering")
            (project.path / "results" / "figures" / "fig1.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            (project.path / "results" / "result_manifest.yaml").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "fig1",
                            "path": "results/figures/fig1.png",
                            "caption_draft": "A result figure",
                            "result_claim": "This result confirms prior work \\citep{Smith2024}.",
                        }
                    ],
                    "tables": [],
                }),
                encoding="utf-8",
            )

            with self.assertRaises(ResultsGateError):
                write_results(project.path)

    def test_cli_inventory_and_write_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI results", field="workflow engineering")
            (project.path / "results" / "figures" / "fig1.png").write_bytes(b"fake image")
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
            validity_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assess-result-validity",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(validity_completed.stdout)["decision"], "pass")

            inventory_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "inventory-results",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(inventory_completed.stdout)["status"], "written")

            write_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "write-results",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(write_completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["results"]).exists())


if __name__ == "__main__":
    unittest.main()
