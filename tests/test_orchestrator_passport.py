from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class OrchestratorPassportTests(unittest.TestCase):
    def test_create_project_initializes_passport_and_ledgers(self) -> None:
        from draftpaper_cli.passport import PASSPORT_FILES, load_project_passport

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Passport test", field="workflow engineering")

            for relative in PASSPORT_FILES.values():
                self.assertTrue((project.path / relative).exists(), relative)

            passport = load_project_passport(project.path)
            self.assertEqual(passport["project_id"], project.project_id)
            self.assertEqual(passport["schema_version"], 1)
            self.assertGreaterEqual(passport["artifact_count"], 3)
            self.assertIn("project.json", {item["path"] for item in passport["artifacts"]})

            artifact_events = read_jsonl(project.path / "artifact_ledger.jsonl")
            self.assertTrue(any(event["path"] == "project.json" for event in artifact_events))

    def test_checkpoint_and_resume_are_append_only_and_drive_status(self) -> None:
        from draftpaper_cli.orchestrator import checkpoint_project, resume_project, status_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Checkpoint test", field="workflow engineering")

            checkpoint = checkpoint_project(project.path, stage="idea", note="User approved the idea.")
            self.assertEqual(checkpoint["status"], "checkpoint_created")
            self.assertRegex(checkpoint["checkpoint_hash"], r"^[a-f0-9]{12}$")

            waiting = status_project(project.path)
            self.assertEqual(waiting["pipeline_state"], "awaiting_confirmation")
            self.assertEqual(waiting["awaiting_checkpoint"]["hash"], checkpoint["checkpoint_hash"])
            self.assertEqual(waiting["next_action"]["command"], "resume")

            resumed = resume_project(project.path, checkpoint_hash=checkpoint["checkpoint_hash"], note="Continue.")
            self.assertEqual(resumed["status"], "resumed")
            self.assertEqual(resumed["consumed_checkpoint_hash"], checkpoint["checkpoint_hash"])

            status = status_project(project.path)
            self.assertEqual(status["pipeline_state"], "ready")
            self.assertEqual(status["next_action"]["stage"], "references")
            self.assertEqual(status["next_action"]["command"], "search-literature")

            checkpoint_events = read_jsonl(project.path / "checkpoint_ledger.jsonl")
            self.assertEqual([event["kind"] for event in checkpoint_events], ["checkpoint", "resume"])

    def test_cli_status_checkpoint_resume_and_run_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI orchestrator", field="workflow engineering")

            status_completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "status", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            status_payload = json.loads(status_completed.stdout)
            self.assertEqual(status_payload["status"], "reported")
            self.assertEqual(status_payload["next_action"]["command"], "search-literature")

            checkpoint_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "checkpoint",
                    "--project",
                    str(project.path),
                    "--stage",
                    "idea",
                    "--note",
                    "Approved.",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            checkpoint_hash = json.loads(checkpoint_completed.stdout)["checkpoint_hash"]

            resume_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "resume",
                    "--project",
                    str(project.path),
                    "--checkpoint-hash",
                    checkpoint_hash,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(resume_completed.stdout)["status"], "resumed")

            run_completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "run-pipeline", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            run_payload = json.loads(run_completed.stdout)
            self.assertEqual(run_payload["status"], "planned")
            self.assertIn("search-literature", run_payload["next_action"]["cli"])

    def test_status_recommends_integrity_gate_before_final_quality_check(self) -> None:
        from draftpaper_cli.orchestrator import status_project
        from draftpaper_cli.passport import refresh_project_passport
        from draftpaper_cli.project_scaffold import _write_json
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Integrity before quality", field="workflow engineering")
            for stage in [
                "references",
                "journal_profile",
                "research_plan",
                "introduction",
                "data",
                "method_plan",
                "code",
                "methods",
                "result_validity",
                "results",
                "discussion",
                "latex",
            ]:
                update_stage_status(project.path, stage, "completed")
            refresh_project_passport(project.path, event="test_status_ready")

            status = status_project(project.path)

            self.assertEqual(status["next_action"]["stage"], "quality_checks")
            self.assertEqual(status["next_action"]["command"], "run-integrity-gate")

            _write_json(project.path / "integrity" / "integrity_report.json", {"status": "passed"})
            status_after_integrity = status_project(project.path)

            self.assertEqual(status_after_integrity["next_action"]["stage"], "quality_checks")
            self.assertEqual(status_after_integrity["next_action"]["command"], "quality-check")

    def test_status_recommends_gate_failure_diagnosis_after_integrity_failure(self) -> None:
        from draftpaper_cli.orchestrator import status_project
        from draftpaper_cli.passport import refresh_project_passport
        from draftpaper_cli.project_scaffold import _write_json
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Diagnose integrity failure", field="workflow engineering")
            for stage in [
                "references",
                "journal_profile",
                "research_plan",
                "introduction",
                "data",
                "method_plan",
                "code",
                "methods",
                "result_validity",
                "results",
                "discussion",
                "latex",
            ]:
                update_stage_status(project.path, stage, "completed")
            _write_json(project.path / "integrity" / "integrity_report.json", {
                "status": "failed",
                "issues": [{"severity": "error", "code": "missing_citation_evidence", "message": "Missing evidence."}],
            })
            refresh_project_passport(project.path, event="test_integrity_failed")

            status = status_project(project.path)

            self.assertEqual(status["next_action"]["stage"], "review")
            self.assertEqual(status["next_action"]["command"], "diagnose-gate-failures")
            self.assertIn("diagnose-gate-failures", status["next_action"]["cli"])

    def test_run_pipeline_recommends_gate_failure_diagnosis_after_quality_failure(self) -> None:
        from draftpaper_cli.orchestrator import run_pipeline
        from draftpaper_cli.passport import refresh_project_passport
        from draftpaper_cli.project_scaffold import _write_json
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Diagnose quality failure", field="workflow engineering")
            for stage in [
                "references",
                "journal_profile",
                "research_plan",
                "introduction",
                "data",
                "method_plan",
                "code",
                "methods",
                "result_validity",
                "results",
                "discussion",
                "latex",
            ]:
                update_stage_status(project.path, stage, "completed")
            update_stage_status(project.path, "quality_checks", "failed")
            _write_json(project.path / "integrity" / "integrity_report.json", {"status": "passed"})
            _write_json(project.path / "quality_checks" / "quality_report.json", {
                "status": "failed",
                "issues": [{"severity": "error", "code": "required_artifact_missing", "message": "Missing artifact."}],
            })
            refresh_project_passport(project.path, event="test_quality_failed")

            plan = run_pipeline(project.path)

            self.assertEqual(plan["next_action"]["stage"], "review")
            self.assertEqual(plan["next_action"]["command"], "diagnose-gate-failures")


if __name__ == "__main__":
    unittest.main()
