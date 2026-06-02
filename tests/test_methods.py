from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.method_plan import collect_method_plan


def prepare_passing_data_gate(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text("# Plan\n\nExploratory pilot analysis.\n", encoding="utf-8")
    rows = "\n".join(f"{i},{i % 2}" for i in range(1, 41))
    (project_path / "data" / "raw" / "sample.csv").write_text("id,target\n" + rows + "\n", encoding="utf-8")
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["id", "target"])
    assess_data_feasibility(project_path, min_rows=30)
    collect_method_plan(project_path, user_method="Use supervised classification with light-curve features.", primary_metric="f1", minimum_primary_metric=0.7)


class MethodsHardGateTests(unittest.TestCase):
    def test_write_methods_requires_successful_run_manifest(self) -> None:
        from draftpaper_cli.methods import MethodsGateError, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Method gate test", field="workflow engineering")

            with self.assertRaises(MethodsGateError):
                write_methods(project.path)

            self.assertTrue((project.path / "methods" / "method_plan.md").exists())
            self.assertFalse((project.path / "methods" / "methods.tex").exists())

    def test_write_methods_rejects_missing_declared_outputs(self) -> None:
        from draftpaper_cli.methods import MethodsGateError, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Missing output test", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "command": "manual",
                    "input_data": [],
                    "output_files": ["results/tables/missing_metrics.csv"],
                    "metrics": {"accuracy": 0.91},
                    "figures_generated": [],
                    "tables_generated": ["results/tables/missing_metrics.csv"],
                    "started_at": "2026-05-29T00:00:00Z",
                    "finished_at": "2026-05-29T00:00:01Z",
                }),
                encoding="utf-8",
            )

            with self.assertRaises(MethodsGateError):
                write_methods(project.path)

    def test_verify_methods_and_write_methods_success(self) -> None:
        from draftpaper_cli.methods import verify_methods, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer AGN prediction", field="machine learning astronomy")
            prepare_passing_data_gate(project.path)
            output = project.path / "results" / "tables" / "metrics.csv"
            command = f"{sys.executable} -c \"from pathlib import Path; Path(r'{output}').write_text('metric,value\\naccuracy,0.91\\n', encoding='utf-8')\""

            verify_result = verify_methods(project.path, command=command, output_files=["results/tables/metrics.csv"])
            self.assertEqual(verify_result["status"], "success")
            self.assertTrue((project.path / "methods" / "run_manifest.yaml").exists())

            write_result = write_methods(project.path)
            self.assertEqual(write_result["status"], "written")
            methods_tex = (project.path / "methods" / "methods.tex").read_text(encoding="utf-8")
            self.assertIn("\\section{Methods}", methods_tex)
            self.assertIn("results/tables/metrics.csv", methods_tex)
            self.assertIn("accuracy", methods_tex)

            manifest = json.loads((project.path / "methods" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertIn("methods/method_requirements.json", manifest["input_files"])
            self.assertIn("methods/run_manifest.yaml", manifest["input_files"])
            self.assertIn("methods/methods.tex", manifest["output_files"])

    def test_cli_verify_and_write_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI method gate", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            output = project.path / "results" / "tables" / "metrics.csv"
            command = f"{sys.executable} -c \"from pathlib import Path; Path(r'{output}').write_text('metric,value\\nf1,0.88\\n', encoding='utf-8')\""

            verify_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "verify-methods",
                    "--project",
                    str(project.path),
                    "--command",
                    command,
                    "--output",
                    "results/tables/metrics.csv",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(verify_completed.stdout)["status"], "success")

            write_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "write-methods",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(write_completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["methods"]).exists())

    def test_write_methods_escapes_windows_command_text_for_latex(self) -> None:
        from draftpaper_cli.methods import write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Windows command escaping", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "command": r"C:\download\Anaconda\python.exe code\scripts\run_method.py --rate 50%",
                    "input_data": [],
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"f1_score": "0.88"},
                    "figures_generated": [],
                    "tables_generated": ["results/tables/metrics.csv"],
                    "started_at": "2026-05-29T00:00:00Z",
                    "finished_at": "2026-05-29T00:00:01Z",
                }),
                encoding="utf-8",
            )

            write_methods(project.path)

            tex = (project.path / "methods" / "methods.tex").read_text(encoding="utf-8")
            self.assertNotIn("`", tex)
            self.assertNotIn(r"C:\download", tex)
            self.assertIn(r"\textbackslash{}", tex)
            self.assertIn(r"50\%", tex)


if __name__ == "__main__":
    unittest.main()
