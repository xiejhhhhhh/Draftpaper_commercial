from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def write_failed_gate_reports(project_path: Path) -> None:
    (project_path / "data" / "data_feasibility_report.json").write_text(
        json.dumps({
            "decision": "blocked",
            "blocking_issues": ["Total tabular row count 5 is below the minimum threshold 30."],
            "recommended_actions": ["Add more observations or reduce the scope."],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "methods" / "run_manifest.yaml").write_text(
        json.dumps({
            "status": "failed",
            "command": "python code/scripts/run_analysis.py",
            "returncode": 1,
            "missing_outputs": ["results/tables/metrics.csv"],
            "output_files": ["results/tables/metrics.csv"],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "results" / "result_validity_report.json").write_text(
        json.dumps({
            "decision": "revise_required",
            "primary_metric": "f1",
            "observed_value": 0.42,
            "minimum_value": 0.75,
            "failure_causes": ["method"],
            "recommended_actions": ["Inspect model design and validation split."],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "integrity").mkdir(exist_ok=True)
    (project_path / "integrity" / "integrity_report.json").write_text(
        json.dumps({
            "status": "failed",
            "issues": [
                {
                    "severity": "error",
                    "code": "missing_citation_evidence",
                    "message": "Citation key is absent from citation_evidence.csv: Unknown2026",
                    "file": "references/citation_evidence.csv",
                    "section": "introduction",
                },
                {
                    "severity": "error",
                    "code": "result_artifact_missing",
                    "message": "Result artifact does not exist: results/figures/missing.svg",
                    "file": "results/figures/missing.svg",
                    "section": "results",
                },
            ],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "quality_checks" / "quality_report.json").write_text(
        json.dumps({
            "status": "failed",
            "issues": [
                {
                    "severity": "error",
                    "code": "stale_stage_in_final_latex",
                    "message": "Final LaTeX depends on stale stage: results.",
                    "file": "results/stage_manifest.json",
                }
            ],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "latex" / "main.tex").write_text("\\section{Draft}\n", encoding="utf-8")
    (project_path / "results" / "results.tex").write_text("\\section{Results}\nWeak result text.\n", encoding="utf-8")


class ReviewRevisionTests(unittest.TestCase):
    def test_diagnose_gate_failures_writes_unified_revision_issues(self) -> None:
        from draftpaper_cli.review_revision import diagnose_gate_failures

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Revision router", field="workflow engineering")
            write_failed_gate_reports(project.path)

            report = diagnose_gate_failures(project.path)

            self.assertEqual(report["status"], "issues_found")
            self.assertTrue((project.path / "review" / "gate_failure_diagnosis.json").exists())
            self.assertTrue((project.path / "review" / "gate_failure_diagnosis.md").exists())
            sources = {issue["source"] for issue in report["issues"]}
            self.assertIn("data_feasibility", sources)
            self.assertIn("methods", sources)
            self.assertIn("result_validity", sources)
            self.assertIn("integrity", sources)
            self.assertTrue(all("recommended_commands" in issue for issue in report["issues"]))
            self.assertTrue(any(issue["target_stage"] == "references" for issue in report["issues"]))
            self.assertTrue(any(issue["target_stage"] == "results" for issue in report["issues"]))

    def test_review_and_revision_plan_create_commitment_ledger(self) -> None:
        from draftpaper_cli.review_revision import generate_revision_plan, review_draft

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Reviewer loop", field="workflow engineering")
            write_failed_gate_reports(project.path)

            review = review_draft(project.path)
            plan = generate_revision_plan(project.path)

            self.assertEqual(review["status"], "reviewed")
            self.assertTrue((project.path / "review" / "review_report.md").exists())
            self.assertTrue((project.path / "review" / "reviewer_issues.json").exists())
            self.assertEqual(plan["status"], "revision_required")
            self.assertTrue((project.path / "review" / "revision_plan.json").exists())
            self.assertTrue((project.path / "review" / "revision_plan.md").exists())
            ledger_path = project.path / "review" / "commitment_ledger.csv"
            self.assertTrue(ledger_path.exists())
            with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertGreaterEqual(len(rows), 1)
            self.assertIn("issue_id", rows[0])
            self.assertIn("target_stage", rows[0])

    def test_apply_revision_marks_target_and_downstream_stages_stale(self) -> None:
        from draftpaper_cli.project_state import update_stage_status
        from draftpaper_cli.review_revision import apply_revision, generate_revision_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Apply revision", field="workflow engineering")
            write_failed_gate_reports(project.path)
            for stage in ["methods", "result_validity", "results", "discussion", "latex", "quality_checks"]:
                update_stage_status(project.path, stage, "completed")
            generate_revision_plan(project.path)

            result = apply_revision(project.path)

            self.assertEqual(result["status"], "applied")
            project_json = json.loads((project.path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["methods"]["status"], "stale")
            self.assertEqual(project_json["stages"]["results"]["status"], "stale")
            self.assertTrue((project.path / "review" / "apply_revision_report.json").exists())

    def test_cli_review_revision_loop_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI review loop", field="workflow engineering")
            write_failed_gate_reports(project.path)
            for command in [
                "diagnose-gate-failures",
                "review-draft",
                "generate-revision-plan",
                "apply-revision",
                "re-review",
            ]:
                completed = subprocess.run(
                    [sys.executable, "-m", "draftpaper_cli.cli", command, "--project", str(project.path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn("status", json.loads(completed.stdout))
            self.assertTrue((project.path / "review" / "re_review_report.md").exists())


if __name__ == "__main__":
    unittest.main()
