from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs
from draftpaper_cli.result_validity import assess_result_validity


LITERATURE = [
    {
        "title": "X-ray Sources Classification Using Machine Learning",
        "authors": ["A. Zuo"],
        "year": "2024",
        "abstract": "Machine learning classification uses light curve and spectral features for X-ray sources with validation.",
        "publication": "arXiv",
        "citation_count": 10,
        "source": "arxiv",
    }
]


def prepare_project(project_path: Path) -> None:
    write_reference_outputs(project_path, LITERATURE, query="X-ray source classification")
    (project_path / "research_plan" / "research_plan.md").write_text(
        "# Plan\n\nUse supervised X-ray source classification with light curve and spectral features.\n",
        encoding="utf-8",
    )
    rows = "\n".join(f"{i},{i % 2},0.{i % 9}" for i in range(1, 41))
    (project_path / "data" / "raw" / "sample.csv").write_text("id,target,hardness\n" + rows + "\n", encoding="utf-8")
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["id", "target", "hardness"])
    assess_data_feasibility(project_path, min_rows=30)


class MethodPlanAndResultValidityTests(unittest.TestCase):
    def test_collect_method_plan_writes_user_and_literature_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray transient classification", field="machine learning astronomy")
            prepare_project(project.path)

            result = collect_method_plan(
                project.path,
                user_method="Use a multimodal Transformer with light-curve and spectral branches.",
                primary_metric="f1",
                minimum_primary_metric=0.8,
            )

            self.assertEqual(result["status"], "written")
            requirements = json.loads((project.path / "methods" / "method_requirements.json").read_text(encoding="utf-8"))
            self.assertEqual(requirements["method_data_fit"], "proceed")
            self.assertEqual(requirements["primary_metric"], "f1")
            self.assertEqual(requirements["minimum_primary_metric"], 0.8)
            self.assertIn("light_curve", requirements["required_data_features"])
            self.assertGreaterEqual(requirements["literature_method_count"], 1)
            plan = (project.path / "methods" / "method_plan.md").read_text(encoding="utf-8")
            self.assertIn("Literature-Informed Method Synthesis", plan)
            self.assertIn("multimodal Transformer", plan)

    def test_result_validity_blocks_weak_results_and_identifies_backtracking_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Weak result classification", field="machine learning astronomy")
            prepare_project(project.path)
            collect_method_plan(project.path, primary_metric="f1", minimum_primary_metric=0.8)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.55\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"f1": 0.55},
                }),
                encoding="utf-8",
            )

            result = assess_result_validity(project.path)

            self.assertEqual(result["decision"], "revise_required")
            self.assertIn("method", result["failure_causes"])
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))
            self.assertIn("Inspect model design", " ".join(report["recommended_actions"]))

    def test_cli_collect_method_plan_and_assess_result_validity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI validity", field="workflow engineering")
            prepare_project(project.path)
            collect_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "collect-method-plan",
                    "--project",
                    str(project.path),
                    "--method-note",
                    "Use supervised classification.",
                    "--primary-metric",
                    "f1",
                    "--minimum-primary-metric",
                    "0.7",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(collect_completed.stdout)["status"], "written")

            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
