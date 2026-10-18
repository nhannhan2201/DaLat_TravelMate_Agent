"""Kiểm tra runner offline: chỉ dùng graph/HTTP/LLM giả."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app import graph
from app.ranking import build_recommendation_response
from app.schemas import (
    AssessmentGroup, CandidateGroup, CriterionAssessment, NeedGroup,
    PlaceAssessment, PlaceCandidate, PlaceEvaluation, PlaceEvidence,
    EvidenceItem, RecommendationRequest,
)
from evaluation import run


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cases = run.load_cases(run.ROOT / "evaluation" / "cases.json")
        self.env = patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "fake-model-secret-for-test",
            "SERPAPI_API_KEY": "fake-search-secret-for-test",
            "DEEPSEEK_MODEL": "fake-model",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        # Bất kỳ truy cập mạng ngoài ý muốn phải fail, kể cả SDK dùng socket.
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden in offline tests"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.config = patch("app.graph._validate_assessment_request")
        self.config.start()
        self.addCleanup(self.config.stop)

    def fixture(self, *, empty=False):
        needs, groups, prepared, assessed = [], [], [], []
        for gi in range(2):
            need = NeedGroup(name="Nhóm cùng tên", wants=["Yên tĩnh"], avoids=[],
                             search_query="quán ăn", broad_search_query="quán ăn")
            places = []
            for pi in range(2):
                candidate = PlaceCandidate(name="Tên trùng", place_id=f"id-{gi}-{pi}",
                                           address=f"Địa chỉ {gi}-{pi}", rating=4 + pi / 10,
                                           photo_url=f"https://example.org/{gi}-{pi}.jpg")
                evidence = PlaceEvidence(candidate=candidate, analyzed_review_count=1, items=[
                    EvidenceItem(id="review:0", source="review", text=f"Nguồn riêng {gi}-{pi}: yên tĩnh buổi trưa.", date="2026-01-01"),
                ])
                assessment = PlaceAssessment(criteria=[CriterionAssessment(
                    kind="want", criterion_index=0, criterion="Yên tĩnh", status="supported",
                    supporting_evidence_ids=["review:0"], contradicting_evidence_ids=[],
                    explanation="Chỉ ghi nhận vào buổi trưa.",
                )])
                places.append(PlaceEvaluation(candidate=candidate, status="assessed", evidence=evidence, assessment=assessment))
            if empty:
                places = []
            needs.append(need)
            groups.append(CandidateGroup(need=need, used_search_query="quán ăn", candidates=[p.candidate for p in places]))
            prepared.append([{"candidate": p.candidate, "status": "ready", "evidence": p.evidence, "message": None} for p in places])
            assessed.append(AssessmentGroup(need=need, used_search_query="quán ăn", places=places))
        return [
            {"extract_needs": {"needs": needs}},
            {"search": {"used_search_queries": ["quán ăn"] * 2, "search_responses": [{"api_key": "RAW_METADATA_MUST_NOT_BE_SAVED"}]}},
            {"normalize": {"groups": groups}},
            {"evidence": {"prepared_groups": prepared}},
            {"assess": {"assessment_groups": assessed}},
            {"recommend": {"response": build_recommendation_response(assessed, "Đà Lạt", 1)}},
        ]

    def execute(self, updates, cases=None):
        fake = Mock()
        fake.stream.side_effect = lambda initial, **kwargs: iter(updates)
        with patch.object(run, "build_recommendation_graph", return_value=fake):
            folder = run.run_evaluation(cases or [self.cases[1]], 3, 1, self.root)
        return folder, fake

    def test_case_file_and_request_do_not_leak_expectations(self):
        self.assertEqual([c["id"] for c in self.cases], [f"E{i:02}" for i in range(1, 11)])
        folder, fake = self.execute(self.fixture())
        fake.stream.assert_called_once()
        initial = fake.stream.call_args.args[0]
        self.assertEqual(set(initial), {"description", "location", "max_candidates_per_group", "top_k"})
        self.assertEqual(initial["description"], self.cases[1]["description"])
        fake.invoke.assert_not_called()
        saved = (folder / "E02.json").read_text()
        self.assertNotIn("RAW_METADATA_MUST_NOT_BE_SAVED", saved)
        self.assertNotIn("search_responses", saved)

    def test_sources_and_output_link_by_group_id_and_rank_not_name(self):
        folder, _ = self.execute(self.fixture())
        saved = json.loads((folder / "E02.json").read_text())
        links = saved["recommendation_links"]
        self.assertEqual([(p["group_index"], p["place_id"]) for p in links], [(0, "id-0-1"), (1, "id-1-1")])
        self.assertEqual(links[0]["output"]["address"], "Địa chỉ 0-1")
        self.assertEqual(links[1]["assessment_place_index"], 1)
        report = (folder / "report.md").read_text()
        self.assertIn("Nguồn riêng 0", report)
        self.assertIn("Chỉ ghi nhận vào buổi trưa", report)
        self.assertIn("Ghi chú output/UI (ngoài benchmark", report)
        self.assertNotIn("| Lý do bám nguồn |", report)
        self.assertNotIn('"quality_score"', saved)

    def test_each_run_gets_a_new_directory(self):
        first, _ = self.execute(self.fixture())
        original = (first / "E02.json").read_bytes()
        second, _ = self.execute(self.fixture())
        self.assertNotEqual(first, second)
        self.assertEqual((first / "E02.json").read_bytes(), original)

    def test_partial_failure_is_saved_and_next_case_runs_once(self):
        updates = self.fixture()
        def broken():
            yield from updates[:4]
            raise RuntimeError("exception-with-secret fake-model-secret-for-test")
        fake = Mock()
        fake.stream.side_effect = [broken(), iter(updates)]
        with patch.object(run, "build_recommendation_graph", return_value=fake):
            folder = run.run_evaluation(self.cases[:2], 3, 1, self.root)
        first = json.loads((folder / "E01.json").read_text())
        self.assertEqual(first["status"], "error")
        self.assertEqual(first["failed_stage"], "assess")
        self.assertIn("prepared_groups", first["data"])
        self.assertIn("assessment_groups", first["missing_fields"])
        self.assertEqual(json.loads((folder / "E02.json").read_text())["status"], "completed")
        self.assertEqual(fake.stream.call_count, 2)
        report = (folder / "report.md").read_text()
        self.assertIn("Chưa có assessment", report)
        self.assertNotIn("exception-with-secret", report)

    def test_empty_groups_are_explicit(self):
        folder, _ = self.execute(self.fixture(empty=True))
        saved = json.loads((folder / "E02.json").read_text())
        self.assertEqual(saved["status"], "completed_with_issues")
        self.assertEqual(saved["recommendation_links"], [])
        self.assertIn("Không có ứng viên", (folder / "report.md").read_text())

    def test_candidate_errors_and_not_evaluated_remain_visible(self):
        updates = self.fixture()
        groups = updates[4]["assess"]["assessment_groups"]
        groups[0].places[0] = PlaceEvaluation(candidate=groups[0].places[0].candidate, status="error", message="Reviews lỗi fake-search-secret-for-test")
        groups[0].places[1] = PlaceEvaluation(candidate=groups[0].places[1].candidate, status="not_evaluated", message="Vượt giới hạn")
        updates[5]["recommend"]["response"] = build_recommendation_response(groups, "Đà Lạt", 1)
        folder, _ = self.execute(updates)
        saved = json.loads((folder / "E02.json").read_text())
        self.assertEqual([p["status"] for p in saved["data"]["assessment_groups"][0]["places"]], ["error", "not_evaluated"])
        self.assertIn("Vượt giới hạn", (folder / "report.md").read_text())
        self.assertNotIn("fake-search-secret-for-test", (folder / "E02.json").read_text())

    def test_source_secrets_and_html_are_not_written_raw(self):
        updates = self.fixture()
        evidence = updates[4]["assess"]["assessment_groups"][0].places[0].evidence
        evidence.items[0].text = '<script>alert(1)</script> fake-model-secret-for-test'
        evidence.items[0].url = "https://example.org/?api_key=url-secret-value"
        folder, _ = self.execute(updates)
        for path in folder.iterdir():
            self.assertNotIn("fake-model-secret-for-test", path.read_text())
            self.assertNotIn("url-secret-value", path.read_text())
        self.assertNotIn("<script>", (folder / "report.md").read_text())

    def test_interruption_preserves_completed_data_and_pending_cases(self):
        def interrupted():
            yield self.fixture()[0]
            raise KeyboardInterrupt()
        fake = Mock()
        fake.stream.return_value = interrupted()
        with patch.object(run, "build_recommendation_graph", return_value=fake):
            folder = run.run_evaluation(self.cases[:2], 3, 1, self.root)
        manifest = json.loads((folder / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "interrupted")
        self.assertEqual(manifest["cases"][1]["status"], "pending")
        self.assertTrue((folder / "E01.json").exists())
        self.assertFalse((folder / "E02.json").exists())

    def test_input_failure_still_creates_a_case_report(self):
        with patch.object(run, "prepare_recommendation_state", side_effect=run.ConfigurationError("raw secret")), patch.object(run, "build_recommendation_graph") as builder:
            folder = run.run_evaluation([self.cases[0]], 3, 1, self.root)
        builder.assert_not_called()
        rec = json.loads((folder / "E01.json").read_text())
        self.assertEqual(rec["failed_stage"], "prepare_input")
        self.assertEqual(rec["error"]["category"], "configuration")

    def test_cli_requires_selection_and_positive_limits(self):
        for args in ([], ["--all", "--case", "E01", "--max-candidates-per-group", "3", "--top-k", "1"],
                     ["--all", "--max-candidates-per-group", "0", "--top-k", "1"]):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                run.main(args)
        with patch.object(run, "build_recommendation_graph") as execute, self.assertRaises(ValueError):
            run.run_evaluation([self.cases[0]], True, 1, self.root)
        execute.assert_not_called()

    def test_all_ten_cases_saved_with_one_stream_each(self):
        folder, fake = self.execute(self.fixture(), cases=self.cases)
        self.assertEqual(fake.stream.call_count, 10)
        self.assertEqual(sorted(p.stem for p in folder.glob('E*.json')), [c['id'] for c in self.cases])
        manifest = json.loads((folder / 'manifest.json').read_text())
        self.assertEqual(len(manifest['cases']), 10)
        self.assertTrue(all(c['status'] == 'completed' for c in manifest['cases']))

    def test_normal_workflow_keeps_response_contract(self):
        response = self.fixture()[5]["recommend"]["response"]
        fake = Mock()
        fake.invoke.return_value = {"response": response}
        with patch.object(graph, "build_recommendation_graph", return_value=fake):
            actual = graph.run_recommendation_workflow(RecommendationRequest(description="Ăn vặt"), 3, 1)
        self.assertIs(actual, response)

    def test_real_compiled_graph_streams_once_with_mocked_services(self):
        # Kiểm tra stream thực tương thích runner, nhưng mọi dịch vụ đã bị thay bằng mock.
        fixture = self.fixture()
        need = fixture[0]["extract_needs"]["needs"][0]
        place = fixture[4]["assess"]["assessment_groups"][0].places[0]
        with patch.object(graph, "extract_needs", return_value=Mock(groups=[need])) as extract, \
             patch.object(graph, "search_places", return_value={"local_results": [{"title": "Tên trùng", "place_id": "id-0-0"}]}) as search, \
             patch.object(graph, "get_place_details", return_value={}) as details, \
             patch.object(graph, "get_place_reviews", return_value={}) as reviews, \
             patch.object(graph, "build_place_evidence", return_value=place.evidence), \
             patch.object(graph, "assess_place", return_value=place.assessment) as assess:
            folder = run.run_evaluation([self.cases[0]], 3, 1, self.root)
        for service in (extract, search, details, reviews, assess):
            service.assert_called_once()
        rec = json.loads((folder / "E01.json").read_text())
        self.assertEqual(rec["completed_nodes"], list(run.NODES))
        self.assertEqual(rec["status"], "completed")


if __name__ == "__main__":
    unittest.main()
