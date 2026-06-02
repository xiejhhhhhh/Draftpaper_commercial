from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from draftpaper_cli.project_scaffold import create_project


SAMPLE_ITEMS = [
    {
        "title": "Transformer models for active galactic nuclei outburst prediction",
        "authors": ["Jane Smith", "Alan Chen"],
        "year": "2024",
        "doi": "10.1000/agn.2024.1",
        "url": "https://example.org/agn-transformer",
        "abstract": "Existing models lack external validation for long-term outburst prediction in active galactic nuclei.",
        "publication": "Journal of Astroinformatics",
        "citation_count": 42,
        "source": "semantic_scholar",
    },
    {
        "title": "Multimodal survey data for time-domain astronomy",
        "authors": ["Maria Lee"],
        "year": "2023",
        "doi": "",
        "url": "https://arxiv.org/abs/2301.00001",
        "abstract": "Multimodal photometric and spectroscopic survey data improve time-domain event characterization.",
        "publication": "arXiv",
        "citation_count": 7,
        "source": "arxiv",
    },
]


class ReferencesTests(unittest.TestCase):
    def test_write_reference_outputs_creates_fixed_artifacts(self) -> None:
        from draftpaper_cli.references import write_reference_outputs

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN outburst prediction", field="machine learning astronomy")
            result = write_reference_outputs(project.path, SAMPLE_ITEMS, query="AGN outburst prediction")

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["item_count"], 2)
            for relative in [
                "references/library.bib",
                "references/literature_items.json",
                "references/citation_evidence.csv",
                "references/literature_review_notes.md",
            ]:
                self.assertTrue((project.path / relative).exists(), relative)

            bibtex = (project.path / "references" / "library.bib").read_text(encoding="utf-8")
            self.assertIn("@article{Smith2024Transformer1", bibtex)
            self.assertIn("Journal of Astroinformatics", bibtex)

            literature_items = json.loads((project.path / "references" / "literature_items.json").read_text(encoding="utf-8"))
            self.assertEqual(literature_items[0]["bibtex_key"], "Smith2024Transformer1")
            self.assertEqual(literature_items[0]["source"], "semantic_scholar")

            with (project.path / "references" / "citation_evidence.csv").open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                list(rows[0].keys()),
                ["citation_key", "section", "claim", "evidence_summary", "source", "doi", "url"],
            )
            self.assertEqual(rows[0]["citation_key"], "Smith2024Transformer1")
            self.assertEqual(rows[0]["section"], "introduction")
            self.assertIn("external validation", rows[0]["evidence_summary"])

            manifest = json.loads((project.path / "references" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertIn("references/library.bib", manifest["output_files"])

    def test_cli_search_literature_from_json_writes_references_and_marks_downstream_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN outburst prediction", field="machine learning astronomy")
            sample_file = Path(tmp) / "sample_items.json"
            sample_file.write_text(json.dumps(SAMPLE_ITEMS), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "search-literature",
                    "--project",
                    str(project.path),
                    "--from-json",
                    str(sample_file),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertEqual(payload["item_count"], 2)

            project_json = json.loads((project.path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["references"]["status"], "draft")
            self.assertEqual(project_json["stages"]["research_plan"]["status"], "stale")

    def test_search_literature_from_json_accepts_utf8_bom_files(self) -> None:
        from draftpaper_cli.literature_search import search_literature_for_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="BOM JSON import", field="workflow engineering")
            sample_file = Path(tmp) / "sample_items_bom.json"
            sample_file.write_text(json.dumps(SAMPLE_ITEMS), encoding="utf-8-sig")

            result = search_literature_for_project(project.path, from_json=sample_file)

            self.assertEqual(result["status"], "written")
            self.assertTrue((project.path / "references" / "library.bib").exists())

    def test_search_literature_default_limit_is_thirty(self) -> None:
        from draftpaper_cli.cli import build_parser

        args = build_parser().parse_args(["search-literature", "--project", "C:\\project"])

        self.assertEqual(args.limit, 30)

    def test_references_are_ranked_and_html_summaries_are_written(self) -> None:
        from draftpaper_cli.references import write_reference_outputs

        items = []
        for index in range(35):
            items.append({
                "title": f"X-ray transient classification benchmark {index}",
                "authors": [f"Author {index}"],
                "year": "2024",
                "doi": f"10.1000/test.{index}",
                "url": f"https://example.org/paper-{index}",
                "abstract": (
                    "Einstein Probe WXT FXT X-ray transient classification uses light curves, "
                    "spectral features, hardness ratios, and external validation."
                    if index == 29
                    else "A generic astronomy paper with limited relevance."
                ),
                "publication": "Nature Astronomy" if index == 29 else "Workshop Notes",
                "citation_count": 500 if index == 29 else index,
                "source": "semantic_scholar",
            })

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Einstein Probe WXT FXT X-ray transient classification with light curves and spectra",
                field="machine learning astronomy",
                target_journal="Nature Astronomy",
            )
            result = write_reference_outputs(project.path, items, query="Einstein Probe transient classification")

            self.assertEqual(result["item_count"], 30)
            self.assertIn("references/literature_summaries/index.html", result["outputs"])
            literature_items = json.loads((project.path / "references" / "literature_items.json").read_text(encoding="utf-8"))
            self.assertEqual(len(literature_items), 30)
            self.assertEqual(literature_items[0]["publication"], "Nature Astronomy")
            self.assertGreater(literature_items[0]["citation_weight"], literature_items[-1]["citation_weight"])
            for key in ["relevance_score", "authority_score", "citation_authority_score", "journal_score", "citation_weight"]:
                self.assertIn(key, literature_items[0])

            summaries = sorted((project.path / "references" / "literature_summaries").glob("*.html"))
            self.assertGreaterEqual(len(summaries), 31)
            index_html = (project.path / "references" / "literature_summaries" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Literature Summary Index", index_html)
            self.assertIn("Citation weight", index_html)
            summary_text = "\n".join(path.read_text(encoding="utf-8") for path in summaries if path.name != "index.html")
            self.assertIn("<html", summary_text)
            self.assertIn("Relevance to Study", summary_text)
            self.assertIn("Journal authority", summary_text)

            notes = (project.path / "references" / "literature_review_notes.md").read_text(encoding="utf-8")
            self.assertIn("Cross-Paper Synthesis", notes)
            self.assertIn("Data Patterns", notes)

    def test_reference_selection_keeps_data_and_method_contexts_and_filters_weak_metadata(self) -> None:
        from draftpaper_cli.references import write_reference_outputs

        items = []
        for index in range(24):
            items.append({
                "title": f"Recent idea paper {index}",
                "authors": [f"Idea Author {index}"],
                "year": "2024",
                "doi": f"10.1000/idea.{index}",
                "abstract": "Einstein Probe X-ray transient classification and source identification.",
                "publication": "Astrophysical Journal",
                "citation_count": index,
                "source": "semantic_scholar",
                "search_context": "idea",
                "search_query": "Einstein Probe X-ray transient classification",
            })
        for index in range(6):
            items.append({
                "title": f"Data construction paper {index}",
                "authors": [f"Data Author {index}"],
                "year": "2023",
                "doi": f"10.1000/data.{index}",
                "abstract": "X-ray light curve spectral hardness dataset construction for transient source samples.",
                "publication": "The Astronomical Journal",
                "citation_count": 100 + index,
                "source": "crossref",
                "search_context": "data",
                "search_query": "light curve spectral hardness dataset construction",
            })
        for index in range(6):
            items.append({
                "title": f"Method learning paper {index}",
                "authors": [f"Method Author {index}"],
                "year": "2022",
                "doi": f"10.1000/method.{index}",
                "abstract": "Transformer machine learning classification method for irregular X-ray time series.",
                "publication": "Monthly Notices of the Royal Astronomical Society",
                "citation_count": 120 + index,
                "source": "semantic_scholar",
                "search_context": "methods",
                "search_query": "transformer machine learning irregular X-ray time series",
            })
        for index in range(4):
            items.append({
                "title": f"Old paper {index}",
                "authors": [f"Old Author {index}"],
                "year": "2005",
                "doi": f"10.1000/old.{index}",
                "abstract": "Old but related X-ray source classification paper.",
                "publication": "Journal of Astronomy",
                "citation_count": 999,
                "source": "crossref",
                "search_context": "idea",
                "search_query": "old X-ray source classification",
            })
        items.append({
            "title": "Weak metadata candidate",
            "authors": [],
            "year": "",
            "abstract": "",
            "publication": "",
            "citation_count": 5000,
            "source": "crossref",
            "search_context": "data",
            "search_query": "weak metadata",
        })

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Einstein Probe X-ray transient source classification using light curves and spectra",
                field="machine learning astronomy",
                target_journal="Astrophysical Journal",
            )
            result = write_reference_outputs(
                project.path,
                items,
                query="Einstein Probe X-ray transient classification",
                search_queries={
                    "idea": "Einstein Probe X-ray transient classification",
                    "data": "light curve spectral hardness dataset construction",
                    "methods": "transformer machine learning irregular X-ray time series",
                },
            )

            self.assertEqual(result["item_count"], 30)
            literature_items = json.loads((project.path / "references" / "literature_items.json").read_text(encoding="utf-8"))
            contexts = [item["search_context"] for item in literature_items]
            self.assertGreaterEqual(contexts.count("data"), 5)
            self.assertGreaterEqual(contexts.count("methods"), 5)
            self.assertNotIn("Weak metadata candidate", [item["title"] for item in literature_items])
            self.assertGreaterEqual(sum(1 for item in literature_items if int(item["year"]) >= 2021), 18)
            self.assertFalse(any(int(item["year"]) < 2011 for item in literature_items))

            with (project.path / "references" / "citation_evidence.csv").open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertIn("data", {row["section"] for row in rows})
            self.assertIn("methods", {row["section"] for row in rows})

            summary_text = "\n".join(path.read_text(encoding="utf-8") for path in (project.path / "references" / "literature_summaries").glob("*.html"))
            self.assertIn("Search context", summary_text)
            self.assertIn("light curve spectral hardness dataset construction", summary_text)
            self.assertIn("Recommended section", summary_text)

            search_queries = json.loads((project.path / "references" / "search_queries.json").read_text(encoding="utf-8"))
            self.assertEqual(search_queries["data"], "light curve spectral hardness dataset construction")

    def test_metadata_filter_excludes_abstractless_items_without_pdf(self) -> None:
        from draftpaper_cli.references import write_reference_outputs

        items = [
            {
                "title": "Metadata-only unrelated optimization paper",
                "authors": ["A. Author"],
                "year": "2026",
                "doi": "10.1000/noabstract",
                "url": "https://example.org/noabstract",
                "abstract": "",
                "publication": "Engineering Journal",
                "citation_count": 999,
                "source": "crossref",
                "search_context": "methods",
                "search_query": "1D CNN X-ray light curve classification astronomy APJS",
            },
            {
                "title": "CNN classification of X-ray transient light curves",
                "authors": ["B. Author"],
                "year": "2025",
                "doi": "10.1000/abstract",
                "url": "https://example.org/abstract",
                "abstract": "A 1D CNN is evaluated for X-ray transient light curve classification in time-domain astronomy.",
                "publication": "Astrophysical Journal",
                "citation_count": 10,
                "source": "semantic_scholar",
                "search_context": "methods",
                "search_query": "1D CNN X-ray light curve classification astronomy APJS",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray transient classification", field="machine learning astronomy")
            result = write_reference_outputs(project.path, items, query="X-ray transient classification")

            literature_items = json.loads((project.path / "references" / "literature_items.json").read_text(encoding="utf-8"))
            self.assertEqual(result["item_count"], 1)
            self.assertEqual(literature_items[0]["title"], "CNN classification of X-ray transient light curves")

    def test_context_queries_are_crossed_with_domain_journal_and_method_phrases(self) -> None:
        from draftpaper_cli.literature_search import build_context_search_queries

        method_note = (
            "1D CNN / ResNet: handle light curves.\n"
            "Transformer: handle irregular time sampling sequences.\n"
            "Temporal Convolutional Network: handle long-timescale light curves.\n"
            "multimodal network: fuse light curves, spectra, and multi-band features.\n"
            "contrastive learning / self-supervised pretraining: handle scarce labels."
        )
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Einstein Probe X-ray flaring source classification",
                field="machine learning astronomy",
                target_journal="APJS",
            )
            (project.path / "methods" / "method_plan.md").write_text(method_note, encoding="utf-8")
            (project.path / "data" / "data_inventory.json").write_text(
                json.dumps({"files": [{"columns": ["light_curve", "spectrum", "multi_band_feature"]}]}),
                encoding="utf-8",
            )

            queries = build_context_search_queries(project.path, "X-ray transient classification")

            self.assertIsInstance(queries["data"], list)
            self.assertIsInstance(queries["methods"], list)
            self.assertGreaterEqual(len(queries["data"]), 3)
            self.assertLessEqual(len(queries["data"]), 5)
            self.assertGreaterEqual(len(queries["methods"]), 3)
            self.assertLessEqual(len(queries["methods"]), 5)
            for context in ["data", "methods"]:
                for query in queries[context]:
                    self.assertIn("astronomy", query.lower())
                    self.assertNotIn("APJS", query)
            self.assertTrue(any("1D CNN" in query or "ResNet" in query for query in queries["methods"]))
            self.assertTrue(any("Transformer" in query for query in queries["methods"]))
            self.assertTrue(any("Temporal Convolutional Network" in query for query in queries["methods"]))

    def test_live_search_uses_small_per_query_limits_for_data_and_methods(self) -> None:
        from draftpaper_cli.literature_search import search_literature_for_project

        calls = []

        def fake_search(query: str, limit: int = 30) -> list[dict[str, object]]:
            calls.append((query, limit))
            return [
                {
                    "title": f"Result for {query[:24]}",
                    "authors": ["A. Author"],
                    "year": "2025",
                    "abstract": f"Relevant astronomy paper for {query}.",
                    "publication": "Astrophysical Journal",
                    "citation_count": 1,
                    "source": "semantic_scholar",
                }
            ]

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Einstein Probe X-ray flaring source classification",
                field="machine learning astronomy",
                target_journal="APJS",
            )
            (project.path / "methods" / "method_plan.md").write_text("1D CNN / ResNet\nTransformer\nTemporal Convolutional Network", encoding="utf-8")

            with patch("draftpaper_cli.literature_search.search_free_literature", side_effect=fake_search):
                search_literature_for_project(project.path, query="X-ray transient classification", limit=30)

            self.assertGreaterEqual(len(calls), 7)
            data_method_limits = [limit for query, limit in calls if "dataset" in query.lower() or "1D CNN" in query or "Transformer" in query or "Temporal Convolutional Network" in query]
            self.assertTrue(data_method_limits)
            self.assertTrue(all(limit <= 2 for limit in data_method_limits))

    def test_duplicate_paper_can_support_multiple_reference_contexts(self) -> None:
        from draftpaper_cli.references import write_reference_outputs

        shared = {
            "title": "Shared X-ray source classification paper",
            "authors": ["A. Author"],
            "year": "2024",
            "doi": "10.1000/shared",
            "abstract": "This paper describes an X-ray source dataset and machine learning classification method.",
            "publication": "Astrophysical Journal",
            "citation_count": 20,
            "source": "semantic_scholar",
        }
        items = [
            {**shared, "search_context": "data", "search_query": "machine learning astronomy dataset"},
            {**shared, "search_context": "methods", "search_query": "machine learning astronomy transformer"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray source classification", field="machine learning astronomy")
            write_reference_outputs(project.path, items, query="X-ray source classification")

            literature_items = json.loads((project.path / "references" / "literature_items.json").read_text(encoding="utf-8"))
            self.assertEqual(len(literature_items), 1)
            self.assertEqual(set(literature_items[0]["search_contexts"]), {"data", "methods"})

            with (project.path / "references" / "citation_evidence.csv").open("r", encoding="utf-8", newline="") as handle:
                sections = {row["section"] for row in csv.DictReader(handle)}
            self.assertIn("data", sections)
            self.assertIn("methods", sections)


if __name__ == "__main__":
    unittest.main()
