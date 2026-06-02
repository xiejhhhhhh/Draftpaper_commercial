from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.journal_profile import resolve_journal_template
from draftpaper_cli.project_scaffold import create_project


AAS_TEMPLATE_HTML = """
<html><body>
<h1>AASTeX Template for submissions to AAS Journals</h1>
<p>For ApJ, AJ, ApJS, ApJL, PSJ, and RNAAS. Manuscripts should use linenumbers.</p>
<pre>
%% Beginning of file 'sample701.tex'
\\documentclass[linenumbers,trackchanges]{aastex701}
\\submitjournal{ApJS}
\\begin{document}
\\title{Sample}
\\begin{abstract}
Abstract text.
\\end{abstract}
\\keywords{High energy astrophysics}
\\end{document}
</pre>
</body></html>
"""


class JournalProfileTests(unittest.TestCase):
    def test_resolve_journal_template_writes_profile_and_latex_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="APJS template test", field="astronomy", target_journal="APJS")
            html = Path(tmp) / "aas.html"
            html.write_text(AAS_TEMPLATE_HTML, encoding="utf-8")

            result = resolve_journal_template(project.path, target_journal="APJS", from_html=html)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["documentclass"], "aastex701")
            profile = json.loads((project.path / "journal_profile" / "journal_profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["target_journal"], "APJS")
            self.assertTrue(profile["rules"]["requires_linenumbers"])
            template = (project.path / "latex" / "template" / "main.tex").read_text(encoding="utf-8")
            self.assertIn(r"\documentclass[linenumbers,trackchanges]{aastex701}", template)
            self.assertIn("%%DRAFTPAPER_SECTIONS%%", template)

            manifest = json.loads((project.path / "journal_profile" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertIn("journal_profile/journal_profile.json", manifest["output_files"])

    def test_cli_resolve_journal_template_accepts_local_html_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI APJS template", field="astronomy", target_journal="APJS")
            html = Path(tmp) / "aas.html"
            html.write_text(AAS_TEMPLATE_HTML, encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "resolve-journal-template",
                    "--project",
                    str(project.path),
                    "--target-journal",
                    "APJS",
                    "--from-html",
                    str(html),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertEqual(payload["documentclass"], "aastex701")
            self.assertTrue(Path(payload["latex_template"]).exists())


if __name__ == "__main__":
    unittest.main()
