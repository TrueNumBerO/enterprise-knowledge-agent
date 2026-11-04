"""A deliberately small, reproducible lexical/synonym retrieval comparison."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from kb_agent.retrieval import KnowledgeBase


class RetrievalComparisonTests(unittest.TestCase):
    def test_two_query_recall_comparison(self):
        cases = json.loads((ROOT / "data/retrieval-evaluation.json").read_text(encoding="utf-8"))["cases"]
        totals = {}
        for label, enabled in (("lexical", False), ("synonyms", True)):
            knowledge = KnowledgeBase(ROOT / "data/knowledge.json", use_synonyms=enabled)
            recalls = []
            for case in cases:
                found = {item["doc_id"] for item in knowledge.search(case["query"], limit=2)["results"]}
                expected = set(case["expected_doc_ids"])
                recalls.append(len(found & expected) / len(expected))
            totals[label] = sum(recalls) / len(recalls)
        self.assertEqual(totals["lexical"], 0.5)
        self.assertEqual(totals["synonyms"], 1.0)

    def test_explicit_leave_topic_does_not_retrieve_expense_conflict(self):
        result = KnowledgeBase(ROOT / "data/knowledge.json").search("年假需要提前多久申请？")
        self.assertEqual([item["doc_id"] for item in result["results"]], ["D04"])


if __name__ == "__main__":
    unittest.main()
