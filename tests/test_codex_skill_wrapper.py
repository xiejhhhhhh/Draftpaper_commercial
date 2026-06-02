from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = PROJECT_ROOT / "codex_skills" / "draftpaper-workflow"
SKILL_MD = SKILL_DIR / "SKILL.md"
OPENAI_YAML = SKILL_DIR / "agents" / "openai.yaml"
COMMANDS_MD = SKILL_DIR / "references" / "commands.md"


class CodexSkillWrapperTests(unittest.TestCase):
    def test_skill_wrapper_files_exist(self) -> None:
        self.assertTrue(SKILL_MD.exists())
        self.assertTrue(OPENAI_YAML.exists())
        self.assertTrue(COMMANDS_MD.exists())

    def test_skill_frontmatter_is_discoverable_and_thin(self) -> None:
        content = SKILL_MD.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"))
        self.assertIn("name: draftpaper-workflow", content)
        self.assertRegex(content, r"description: Use when .*DraftPaper")
        self.assertLess(len(content.split()), 900)

    def test_skill_only_calls_cli_and_does_not_reimplement_core_logic(self) -> None:
        content = SKILL_MD.read_text(encoding="utf-8")
        commands = COMMANDS_MD.read_text(encoding="utf-8")
        combined = content + "\n" + commands
        self.assertIn("python -m draftpaper_cli.cli", combined)
        self.assertIn("quality-check", combined)
        self.assertIn("Do not directly edit project.json", content)
        self.assertIn("Do not directly edit stage_manifest", content)
        forbidden_patterns = [
            r"def\s+",
            r"class\s+",
            r"json\.dump",
            r"open\(",
            r"write_text\(",
        ]
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, content), pattern)

    def test_skill_documents_stage_order_and_rerun_rules(self) -> None:
        content = SKILL_MD.read_text(encoding="utf-8")
        for command in [
            "create-project",
            "search-literature",
            "resolve-journal-template",
            "generate-plan",
            "write-introduction",
            "collect-method-plan",
            "verify-methods",
            "write-methods",
            "assess-result-validity",
            "inventory-results",
            "write-results",
            "write-discussion",
            "assemble-latex",
            "quality-check",
        ]:
            self.assertIn(command, content)
        self.assertIn("references change", content)
        self.assertIn("results change", content)


if __name__ == "__main__":
    unittest.main()
