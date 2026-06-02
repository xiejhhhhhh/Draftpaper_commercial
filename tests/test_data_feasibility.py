from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


class DataFeasibilityGateTests(unittest.TestCase):
    def test_inventory_data_records_local_raw_and_processed_files(self) -> None:
        from draftpaper_cli.data_feasibility import inventory_data

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Data inventory", field="workflow engineering")
            (project.path / "data" / "raw" / "sample.csv").write_text("id,value\n1,2\n", encoding="utf-8")

            result = inventory_data(project.path)

            self.assertEqual(result["status"], "written")
            inventory = json.loads((project.path / "data" / "data_inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(inventory["file_count"], 1)
            self.assertEqual(inventory["files"][0]["path"], "data/raw/sample.csv")
            self.assertEqual(inventory["files"][0]["row_count"], 1)
            self.assertEqual(inventory["files"][0]["column_count"], 2)

    def test_assess_data_quality_reports_missingness_and_required_columns(self) -> None:
        from draftpaper_cli.data_feasibility import assess_data_quality, inventory_data

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Data quality", field="workflow engineering")
            (project.path / "data" / "raw" / "sample.csv").write_text("id,target,value\n1,,2\n2,1,3\n", encoding="utf-8")
            inventory_data(project.path)

            result = assess_data_quality(project.path, required_columns=["id", "target", "external_validation_id"])

            self.assertEqual(result["status"], "written")
            report = json.loads((project.path / "data" / "data_quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["overall_status"], "warning")
            self.assertIn("external_validation_id", report["missing_required_columns"])
            self.assertGreater(report["overall_missing_cell_ratio"], 0)

    def test_assess_data_feasibility_blocks_when_data_cannot_support_goal(self) -> None:
        from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
        from draftpaper_cli.methods import MethodsGateError, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="External validation prediction", field="machine learning astronomy")
            (project.path / "research_plan" / "research_plan.md").write_text(
                "# Plan\n\nThe study requires external validation and generalizable prediction.\n",
                encoding="utf-8",
            )
            (project.path / "data" / "raw" / "tiny.csv").write_text("id,target\n1,0\n2,1\n", encoding="utf-8")
            inventory_data(project.path)
            assess_data_quality(project.path, required_columns=["id", "target", "external_validation_id"])

            result = assess_data_feasibility(project.path, min_rows=30)

            self.assertEqual(result["decision"], "blocked")
            report = json.loads((project.path / "data" / "data_feasibility_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report["scientific_goal_supported"])
            self.assertIn("supported_claim_level", report)
            self.assertTrue((project.path / "data" / "data_feasibility_report.md").exists())

            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "command": "manual",
                    "input_data": [],
                    "output_files": [],
                    "metrics": {},
                    "figures_generated": [],
                    "tables_generated": [],
                }),
                encoding="utf-8",
            )
            with self.assertRaises(MethodsGateError):
                write_methods(project.path)

    def test_assess_data_feasibility_conditional_pass_allows_methods_with_lower_claim_strength(self) -> None:
        from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
        from draftpaper_cli.method_plan import collect_method_plan
        from draftpaper_cli.methods import write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Pilot association study", field="workflow engineering")
            (project.path / "research_plan" / "research_plan.md").write_text(
                "# Plan\n\nThe study is an exploratory pilot analysis.\n",
                encoding="utf-8",
            )
            rows = "\n".join(f"{i},{i % 2},0.{i % 10}" for i in range(1, 41))
            (project.path / "data" / "raw" / "sample.csv").write_text("id,target,value\n" + rows + "\n", encoding="utf-8")
            inventory_data(project.path)
            assess_data_quality(project.path, required_columns=["id", "target"])

            result = assess_data_feasibility(project.path, min_rows=30)

            self.assertEqual(result["decision"], "conditional_pass")
            collect_method_plan(project.path, user_method="Use supervised pilot classification.", primary_metric="f1", minimum_primary_metric=0.7)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.75\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "command": "manual",
                    "input_data": ["data/raw/sample.csv"],
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"f1": "0.75"},
                    "figures_generated": [],
                    "tables_generated": ["results/tables/metrics.csv"],
                }),
                encoding="utf-8",
            )
            methods_result = write_methods(project.path)
            self.assertEqual(methods_result["status"], "written")

    def test_cli_data_feasibility_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI data gate", field="workflow engineering")
            (project.path / "research_plan" / "research_plan.md").write_text("# Plan\n\nExploratory pilot analysis.\n", encoding="utf-8")
            (project.path / "data" / "raw" / "sample.csv").write_text("id,target\n1,0\n2,1\n3,0\n", encoding="utf-8")

            inventory_completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "inventory-data", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(inventory_completed.stdout)["status"], "written")

            quality_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assess-data-quality",
                    "--project",
                    str(project.path),
                    "--required-column",
                    "id",
                    "--required-column",
                    "target",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(quality_completed.stdout)["status"], "written")

            feasibility_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assess-data-feasibility",
                    "--project",
                    str(project.path),
                    "--min-rows",
                    "3",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(feasibility_completed.stdout)
            self.assertIn(payload["decision"], {"pass", "conditional_pass"})


if __name__ == "__main__":
    unittest.main()
