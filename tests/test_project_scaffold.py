from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ProjectScaffoldTests(unittest.TestCase):
    def test_create_project_writes_expected_directory_model(self) -> None:
        from draftpaper_cli.project_scaffold import create_project

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = create_project(
                root=root,
                idea="Long-term AGN outburst prediction using multimodal survey data",
                field="machine learning astronomy",
                target_journal="General Academic Journal",
            )

            self.assertEqual(project.project_slug, "long-term-agn-outburst-prediction-using-multimodal-survey-data")
            self.assertTrue(project.path.exists())
            expected_dirs = [
                "idea",
                "research_plan",
                "references",
                "journal_profile",
                "introduction",
                "data/raw",
                "data/processed",
                "method_plan",
                "methods",
                "code/src",
                "code/scripts",
                "code/tests",
                "result_validity",
                "results/figures",
                "results/tables",
                "discussion",
                "latex/sections",
                "latex/template",
                "quality_checks",
            ]
            for relative in expected_dirs:
                self.assertTrue((project.path / relative).is_dir(), relative)

            metadata = json.loads((project.path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["idea"], "Long-term AGN outburst prediction using multimodal survey data")
            self.assertEqual(metadata["field"], "machine learning astronomy")
            self.assertEqual(metadata["target_journal"], "General Academic Journal")
            self.assertEqual(metadata["current_stage"], "idea")
            self.assertEqual(metadata["stages"]["research_plan"]["status"], "pending")
            self.assertEqual(metadata["stages"]["references"]["status"], "pending")
            self.assertEqual(metadata["stages"]["journal_profile"]["depends_on"], ["idea"])
            self.assertEqual(metadata["stages"]["research_plan"]["depends_on"], ["references", "journal_profile"])
            self.assertEqual(metadata["stages"]["method_plan"]["depends_on"], ["research_plan", "references", "data"])
            self.assertEqual(metadata["stages"]["results"]["depends_on"], ["result_validity"])

            idea_note = (project.path / "idea" / "idea.md").read_text(encoding="utf-8")
            self.assertIn("Long-term AGN outburst prediction", idea_note)
            self.assertIn("machine learning astronomy", idea_note)

    def test_existing_project_is_not_overwritten_without_flag(self) -> None:
        from draftpaper_cli.project_scaffold import ProjectAlreadyExistsError, create_project

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_project(root=root, idea="Reusable project", field="test field")

            with self.assertRaises(ProjectAlreadyExistsError):
                create_project(root=root, idea="Reusable project", field="test field")

    def test_cli_create_project_outputs_project_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "create-project",
                "--root",
                tmp,
                "--idea",
                "Multimodal crop disease early warning",
                "--field",
                "precision agriculture",
            ]
            completed = subprocess.run(command, check=True, capture_output=True, text=True)

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "created")
            self.assertTrue(Path(payload["project_path"]).exists())
            self.assertTrue((Path(payload["project_path"]) / "project.json").exists())


if __name__ == "__main__":
    unittest.main()
