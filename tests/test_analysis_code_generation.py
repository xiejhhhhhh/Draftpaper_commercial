from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.methods import verify_methods
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs


def prepare_codegen_project(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "# Research Plan\n\n"
        "Build an exploratory classifier for X-ray flaring sources using light curves, "
        "spectral hardness, and multiwavelength features.\n",
        encoding="utf-8",
    )
    write_reference_outputs(
        project_path,
        [
            {
                "title": "Transformer classification of variable X-ray sources",
                "authors": ["Smith", "Wang"],
                "year": 2024,
                "publication": "Astrophysical Journal Supplement Series",
                "doi": "10.0000/apjs.2024.001",
                "url": "https://example.org/apjs-transformer",
                "abstract": (
                    "The paper evaluates transformer and temporal convolutional networks "
                    "for light curve classification of variable X-ray sources."
                ),
                "deep_summary": {
                    "methods": (
                        "A supervised multimodal classifier combines light-curve embeddings, "
                        "spectral hardness ratios, and cross-validation metrics."
                    )
                },
                "citation_weight": 0.98,
            }
        ],
    )
    rows = "\n".join(f"{i},{i % 2},{0.1 * i:.2f},{10 + i}" for i in range(1, 41))
    (project_path / "data" / "raw" / "sources.csv").write_text(
        "source_id,target,hardness,flux\n" + rows + "\n",
        encoding="utf-8",
    )
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["source_id", "target", "hardness"])
    assess_data_feasibility(project_path, min_rows=30)
    collect_method_plan(
        project_path,
        user_method=(
            "Use 1D CNN, transformer, temporal convolutional network, multimodal fusion, "
            "and contrastive pretraining for source classification."
        ),
        primary_metric="f1",
        minimum_primary_metric=0.6,
    )


class AnalysisCodeGenerationTests(unittest.TestCase):
    def test_generate_analysis_code_writes_manifest_and_runnable_code(self) -> None:
        from draftpaper_cli.analysis_code import generate_analysis_code
        from draftpaper_cli.project_state import load_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray flaring source classification", field="astronomy machine learning")
            prepare_codegen_project(project.path)

            result = generate_analysis_code(project.path)

            self.assertEqual(result["status"], "written")
            self.assertTrue((project.path / "code" / "scripts" / "run_analysis.py").exists())
            self.assertTrue((project.path / "code" / "src" / "generated_pipeline.py").exists())
            self.assertTrue((project.path / "code" / "tests" / "test_generated_pipeline.py").exists())
            self.assertEqual(
                result["declared_outputs"],
                [
                    "results/tables/metrics.csv",
                    "results/tables/analysis_summary.csv",
                    "results/figures/data_analysis_flow.svg",
                    "results/figures/data_processing_flow.svg",
                    "results/figures/method_analysis_flow.svg",
                    "results/figures/data_to_method_outputs.svg",
                ],
            )
            state = load_project(project.path)
            self.assertEqual(state.metadata["stages"]["code"]["status"], "draft")
            self.assertTrue(state.metadata["stages"]["methods"]["stale"])

            manifest = json.loads((project.path / "methods" / "analysis_code_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("time_series_deep_learning", manifest["method_families"])
            self.assertIn("multimodal_learning", manifest["method_families"])
            self.assertEqual(manifest["selected_input_data"], "data/raw/sources.csv")
            self.assertGreaterEqual(manifest["literature_method_count"], 1)

            verify_result = verify_methods(
                project.path,
                command=result["verify_command"],
                output_files=result["declared_outputs"],
                input_data=[manifest["selected_input_data"]],
            )
            self.assertEqual(verify_result["status"], "success")
            metrics = json.loads((project.path / "methods" / "run_manifest.yaml").read_text(encoding="utf-8"))["metrics"]
            self.assertIn("f1", metrics)
            self.assertIn("row_count", metrics)
            self.assertTrue((project.path / "results" / "figures" / "data_analysis_flow.svg").exists())
            self.assertTrue((project.path / "results" / "figures" / "data_processing_flow.svg").exists())
            self.assertTrue((project.path / "results" / "figures" / "method_analysis_flow.svg").exists())
            self.assertTrue((project.path / "results" / "figures" / "data_to_method_outputs.svg").exists())

    def test_cli_generate_analysis_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI codegen", field="astronomy machine learning")
            prepare_codegen_project(project.path)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "generate-analysis-code",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertIn("verify_command", payload)
            self.assertTrue(Path(payload["analysis_code_manifest"]).exists())


if __name__ == "__main__":
    unittest.main()
