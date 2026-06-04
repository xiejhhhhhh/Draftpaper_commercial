from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project

from tests.test_orchestrator_passport import read_jsonl


class ArtifactDriftTests(unittest.TestCase):
    def test_status_reports_drift_before_refreshing_passport(self) -> None:
        from draftpaper_cli.orchestrator import status_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Artifact drift", field="workflow engineering")
            (project.path / "idea" / "idea.md").write_text("# Research Idea\n\nChanged by user.\n", encoding="utf-8")

            status = status_project(project.path)

            self.assertEqual(status["pipeline_state"], "drift_detected")
            self.assertEqual(status["next_action"]["command"], "sync-artifact-stale")
            self.assertIn("idea/idea.md", {item["path"] for item in status["drift"]["changed_artifacts"]})

    def test_sync_artifact_stale_marks_dependent_stages_and_refreshes_baseline(self) -> None:
        from draftpaper_cli.orchestrator import status_project
        from draftpaper_cli.stale_sync import sync_artifact_stale

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Artifact sync", field="workflow engineering")
            (project.path / "idea" / "idea.md").write_text("# Research Idea\n\nChanged by user.\n", encoding="utf-8")

            result = sync_artifact_stale(project.path)

            self.assertEqual(result["status"], "synced")
            self.assertIn("references", result["stale_stages"])
            self.assertIn("research_plan", result["stale_stages"])
            state = load_project(project.path)
            self.assertTrue(state.metadata["stages"]["references"]["stale"])
            self.assertTrue(state.metadata["stages"]["research_plan"]["stale"])

            events = read_jsonl(project.path / "integrity_ledger.jsonl")
            self.assertTrue(any(event["kind"] == "artifact_drift" for event in events))

            status = status_project(project.path)
            self.assertEqual(status["pipeline_state"], "ready")
            self.assertEqual(status["next_action"]["stage"], "references")

    def test_cli_detect_and_sync_artifact_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI drift", field="workflow engineering")
            (project.path / "idea" / "idea.md").write_text("# Research Idea\n\nChanged by user.\n", encoding="utf-8")

            detect_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "detect-artifact-drift",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            detect_payload = json.loads(detect_completed.stdout)
            self.assertEqual(detect_payload["status"], "drift_detected")

            sync_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "sync-artifact-stale",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            sync_payload = json.loads(sync_completed.stdout)
            self.assertEqual(sync_payload["status"], "synced")
            self.assertIn("references", sync_payload["stale_stages"])


if __name__ == "__main__":
    unittest.main()
