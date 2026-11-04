"""Retrieval behavior and trusted-source boundary tests."""
from pathlib import Path

from helpers import ProjectFixture, ROOT, document
from kb_agent.retrieval import KnowledgeBase


class RetrievalTests(ProjectFixture):
    def test_synonym_query_recalls_expense_policy(self):
        kb = KnowledgeBase(self.data_file())
        result = kb.search("费用最迟什么时候能报？")
        self.assertTrue(result["ok"])
        self.assertIn("T01", [x["doc_id"] for x in result["results"]])

    def test_out_of_domain_query_has_no_hits(self):
        result = KnowledgeBase(self.data_file()).search("火星半径多少？")
        self.assertTrue(result["ok"])
        self.assertFalse(result["results"])

    def test_read_returns_exact_versioned_source(self):
        result = KnowledgeBase(self.data_file()).read("T01")
        self.assertTrue(result["ok"])
        self.assertEqual(result["document"]["content"], document()["content"])
        self.assertEqual(result["document"]["version_date"], "2026-01-01")

    def test_unknown_document_is_structured_failure(self):
        result = KnowledgeBase(self.data_file()).read("MISSING")
        self.assertFalse(result["ok"])
        self.assertIn("error", result)
        self.assertIn("retryable", result)

    def test_transient_search_failure_then_recovery(self):
        kb = KnowledgeBase(self.data_file(), fail_searches=1)
        first, second = kb.search("报销期限"), kb.search("报销期限")
        self.assertFalse(first["ok"])
        self.assertTrue(first["retryable"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["results"])

    def test_transient_read_failure_then_recovery(self):
        kb = KnowledgeBase(self.data_file(), fail_reads=1)
        self.assertFalse(kb.read("T01")["ok"])
        self.assertTrue(kb.read("T01")["ok"])

    def test_content_change_invalidates_old_fact_annotations(self):
        changed = dict(document(), content="报销期限暂未发布，请等待财务确认。")
        doc = KnowledgeBase(self.data_file([changed])).read("T01")["document"]
        self.assertFalse(doc.get("facts", []))

    def test_value_missing_from_quote_invalidates_annotation(self):
        original = document()
        original["facts"][0]["value"] = "90天"
        doc = KnowledgeBase(self.data_file([original])).read("T01")["document"]
        self.assertFalse(doc.get("facts", []))

    def test_external_data_path_is_rejected(self):
        with self.assertRaises((ValueError, PermissionError)):
            KnowledgeBase(ROOT.parent / "outside.json")

    def test_search_limit_is_enforced(self):
        docs = [document(f"T{i:02d}", i) for i in range(1, 8)]
        result = KnowledgeBase(self.data_file(docs)).search("报销期限", limit=2)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["results"]), 2)
    def test_duplicate_document_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            KnowledgeBase(self.data_file([document(), document()]))

    def test_invalid_version_date_is_rejected(self):
        with self.assertRaises(ValueError):
            KnowledgeBase(self.data_file([dict(document(), version_date="2026-99-01")]))

    def test_returned_document_cannot_mutate_corpus(self):
        kb = KnowledgeBase(self.data_file())
        observed = kb.read("T01")["document"]
        observed["content"] = "corrupted"
        observed["facts"].clear()
        fresh = kb.read("T01")["document"]
        self.assertEqual(fresh, document())

    def test_invalid_tool_arguments_return_structured_errors(self):
        kb = KnowledgeBase(self.data_file())
        for args in [("", 5), ("报销", 0), ("报销", True)]:
            with self.subTest(args=args):
                self.assertFalse(kb.search(*args)["ok"])
        self.assertFalse(kb.read(12)["ok"])
