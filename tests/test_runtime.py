"""Black-box execution, grounding, boundedness and observation tests."""
import json

from helpers import ProjectFixture, ScriptedModel, ROOT, action, citation, document
from kb_agent.models import MockModel
from kb_agent.retrieval import KnowledgeBase
from kb_agent.runtime import Agent


class RuntimeSafetyTests(ProjectFixture):
    def run_actions(self, actions, docs=None, max_steps=8):
        if actions and isinstance(actions[0], dict) and actions[0].get("action") == "read":
            actions = [action("search", query="报销期限")] + actions
        model = ScriptedModel(actions)
        result = Agent(model, KnowledgeBase(self.data_file(docs)), max_steps=max_steps).run("报销期限多久？")
        return result, model

    def test_tool_observation_reaches_next_model_turn(self):
        result, model = self.run_actions([
            action("search", query="报销期限"), action("read", doc_id="T01"),
            action("finish", status="answered", answer="30天", citations=[citation()], gaps=[]),
        ])
        self.assertEqual(result["status"], "answered")
        self.assertEqual(len(model.calls), 3)
        self.assertIn("T01", json.dumps(model.calls[1], ensure_ascii=False))
        self.assertIn(document()["content"], json.dumps(model.calls[2], ensure_ascii=False))
        self.assertEqual([t["action"] for t in result["trace"]], ["search", "read", "finish"])
        for step in result["trace"]:
            self.assertTrue({"step", "action", "arguments", "observation", "reason"} <= step.keys())

    def test_answer_without_citation_cannot_succeed(self):
        result, _ = self.run_actions([action("finish", status="answered", answer="30天", citations=[], gaps=[])])
        self.assertNotEqual(result["status"], "answered")

    def test_unread_real_document_cannot_be_cited(self):
        result, _ = self.run_actions([action("finish", status="answered", answer="30天", citations=[citation()], gaps=[])])
        self.assertNotEqual(result["status"], "answered")

    def test_search_snippet_is_not_read_evidence(self):
        result, _ = self.run_actions([
            action("search", query="报销期限"),
            action("finish", status="answered", answer="30天", citations=[citation()], gaps=[]),
        ])
        self.assertNotEqual(result["status"], "answered")

    def test_fabricated_quote_is_rejected(self):
        forged = {**citation(), "quote": "报销期限为60天"}
        result, _ = self.run_actions([
            action("read", doc_id="T01"),
            action("finish", status="answered", answer="60天", citations=[forged], gaps=[]),
        ])
        self.assertNotEqual(result["status"], "answered")

    def test_wrong_document_version_is_rejected(self):
        forged = {**citation(), "version_date": "2030-01-01"}
        result, _ = self.run_actions([
            action("read", doc_id="T01"),
            action("finish", status="answered", answer="30天", citations=[forged], gaps=[]),
        ])
        self.assertNotEqual(result["status"], "answered")

    def test_real_citation_does_not_justify_fabricated_conclusion(self):
        result, _ = self.run_actions([
            action("read", doc_id="T01"),
            action("finish", status="answered", answer="报销有效期90天，且无需发票。", citations=[citation()], gaps=[]),
        ])
        self.assertNotIn("90天", result["answer"])
        self.assertNotIn("无需发票", result["answer"])
        if result["status"] == "answered":
            self.assertIn("30天", result["answer"])

    def test_known_conflict_cannot_be_silently_selected(self):
        docs = [document("T01", 30), document("T02", 15)]
        result, _ = self.run_actions([
            action("read", doc_id="T01"), action("read", doc_id="T02"),
            action("finish", status="answered", answer="按最新的15天为准", citations=[citation(docs[1])], gaps=[]),
        ], docs)
        self.assertNotEqual(result["status"], "answered")
        self.assertNotIn("按最新的15天为准", result["answer"])

    def test_step_budget_is_explicitly_incomplete(self):
        result, model = self.run_actions([action("search", query="报销期限")] * 2, max_steps=2)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(len(result["trace"]), 2)
        self.assertTrue(result["gaps"])

    def test_unknown_tool_cannot_execute(self):
        result, _ = self.run_actions([action("delete_all", path="D:/")])
        self.assertEqual(result["status"], "incomplete")

    def test_model_error_never_silently_falls_back_to_mock(self):
        result, model = self.run_actions([RuntimeError("simulated provider failure")])
        self.assertIn(result["status"], ["incomplete", "tool_error"])
        self.assertNotEqual(result.get("model_mode"), "mock")
        self.assertEqual(len(model.calls), 1)

    def test_runtime_rejects_invalid_budget(self):
        for value in [0, -1, True]:
            with self.subTest(value=value):
                with self.assertRaises((ValueError, TypeError)):
                    Agent(MockModel(), KnowledgeBase(self.data_file()), max_steps=value)

    def test_content_replacement_does_not_trust_stale_facts(self):
        original = document()
        first = Agent(MockModel(), KnowledgeBase(self.data_file([original], "before.json"))).run("报销期限多久？")
        changed = dict(original, content="报销申请须在费用发生后7天内提交。")
        second = Agent(MockModel(), KnowledgeBase(self.data_file([changed], "after.json"))).run("报销期限多久？")
        self.assertEqual(first["status"], "answered")
        self.assertIn("30天", first["answer"])
        self.assertNotIn("30天", second["answer"])
        self.assertNotEqual(first["answer"], second["answer"])
        for item in second["citations"]:
            self.assertIn(item["quote"], changed["content"])

    def test_same_model_can_be_reused_without_history_leak(self):
        agent = Agent(MockModel(), KnowledgeBase(self.data_file()))
        first = agent.run("报销期限多久？")
        second = agent.run("火星半径多少？")
        self.assertEqual(first["status"], "answered")
        self.assertEqual(second["status"], "out_of_scope")
        self.assertFalse(second["citations"])
    def test_unread_conflict_candidate_blocks_answer(self):
        docs = [document("T01", 30), document("T02", 15)]
        result, _ = self.run_actions([
            action("search", query="报销期限"), action("read", doc_id="T01"),
            action("finish", status="answered", answer="30天", citations=[citation(docs[0])], gaps=[]),
        ], docs)
        self.assertNotEqual(result["status"], "answered")

    def test_failed_read_of_conflict_candidate_blocks_answer(self):
        class FailsSecondDocument(KnowledgeBase):
            def read(self, doc_id):
                if doc_id == "T02":
                    return {"ok": False, "code": "READ_UNAVAILABLE", "error": "test failure", "retryable": True}
                return super().read(doc_id)
        docs = [document("T01", 30), document("T02", 15)]
        model = ScriptedModel([
            action("search", query="报销期限"), action("read", doc_id="T01"), action("read", doc_id="T02"),
            action("finish", status="answered", answer="30天", citations=[citation(docs[0])], gaps=[]),
        ])
        result = Agent(model, FailsSecondDocument(self.data_file(docs))).run("报销期限多久？")
        self.assertNotEqual(result["status"], "answered")

    def test_changed_conflict_text_cannot_disappear_with_stale_annotation(self):
        original = document("T01", 30)
        original["content"] = "报销申请须在费用发生后7天内提交。"
        result = Agent(MockModel(), KnowledgeBase(self.data_file([original, document("T02", 15)]))).run("报销期限多久？")
        self.assertNotEqual(result["status"], "answered")
        self.assertNotIn("30天", result["answer"])
        self.assertTrue(result["gaps"])
    def test_topic_match_does_not_answer_unavailable_annual_leave_allowance(self):
        result = Agent(MockModel(), KnowledgeBase(ROOT / "data/knowledge.json")).run("年假一年有多少天？")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertLess(result["steps"], 8)
        self.assertTrue(result["gaps"])

    def test_topic_match_does_not_answer_unavailable_expense_cap(self):
        result = Agent(MockModel(), KnowledgeBase(ROOT / "data/knowledge.json")).run("报销额度上限多少？")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertLess(result["steps"], 8)
        self.assertTrue(result["gaps"])

    def test_allowance_question_with_apply_word_is_not_advance_notice(self):
        result = Agent(MockModel(), KnowledgeBase(ROOT / "data/knowledge.json")).run("我每年能申请多少天年假？")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertNotIn("3个工作日", result["answer"])

    def test_followup_changes_requested_fact_without_inheriting_old_notice_period(self):
        history = [{"role": "user", "content": "年假需要提前多久申请？"},
                   {"role": "assistant", "content": "请查询年假制度。"}]
        result = Agent(MockModel(), KnowledgeBase(ROOT / "data/knowledge.json")).run("那一年可以休几天？", history)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertNotIn("3个工作日", result["answer"])

    def test_explicit_topic_switch_does_not_inherit_old_missing_fact(self):
        history = [{"role": "user", "content": "年假一年有多少天？"}]
        for question, doc_id, phrase in [("IT服务台邮箱是什么？", "D05", "helpdesk@example.invalid"),
                                        ("年假需要提前多久申请？", "D04", "3个工作日")]:
            with self.subTest(question=question):
                result = Agent(MockModel(), KnowledgeBase(ROOT / "data/knowledge.json")).run(question, history)
                self.assertEqual(result["status"], "answered")
                self.assertIn(phrase, result["answer"])
                self.assertIn(doc_id, {c["doc_id"] for c in result["citations"]})

    def test_unannotated_conflicting_sources_require_clarification_in_mock(self):
        docs = [dict(document("T01", 30), facts=[]), dict(document("T02", 15), facts=[])]
        result = Agent(MockModel(), KnowledgeBase(self.data_file(docs))).run("报销期限多久？")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertLess(result["steps"], 8)
        self.assertEqual({s["arguments"]["doc_id"] for s in result["trace"] if s["action"] == "read"}, {"T01", "T02"})

    def test_runtime_blocks_silently_selecting_unannotated_conflict(self):
        docs = [dict(document("T01", 30), facts=[]), dict(document("T02", 15), facts=[])]
        result, model = self.run_actions([
            action("read", doc_id="T01"), action("read", doc_id="T02"),
            action("finish", status="answered", answer="15天", citations=[citation(docs[1])], gaps=[]),
        ], docs)
        self.assertNotEqual(result["status"], "answered")
        finish = next(s for s in result["trace"] if s["action"] == "finish")
        self.assertFalse(finish["observation"]["ok"])
        self.assertEqual(finish["observation"]["code"], "validation_error")

    def test_conflict_citations_must_show_the_conflicting_policy_values(self):
        docs = [document("T01", 30), document("T02", 15)]
        common = "员工应提交报销申请。"
        for doc in docs:
            doc["content"] += common
        citations = [{**citation(doc), "quote": common} for doc in docs]
        result, _ = self.run_actions([
            action("read", doc_id="T01"), action("read", doc_id="T02"),
            action("search", query="报销期限 适用范围 优先级"),
            action("finish", status="conflict", answer="存在冲突", citations=citations, gaps=[]),
        ], docs)
        reads = [s for s in result["trace"] if s["action"] == "read"]
        self.assertEqual(len(reads), 2)
        self.assertTrue(all(s["observation"]["ok"] for s in reads))
        if result["status"] == "conflict":
            by_id = {c["doc_id"]: c["quote"] for c in result["citations"]}
            self.assertIn(docs[0]["facts"][0]["quote"], by_id["T01"])
            self.assertIn(docs[1]["facts"][0]["quote"], by_id["T02"])
        else:
            self.assertEqual(result["status"], "incomplete")
            self.assertFalse(next(s for s in result["trace"] if s["action"] == "finish")["observation"]["ok"])

    def test_non_string_model_action_is_controlled_incomplete(self):
        result, _ = self.run_actions([{"action": ["search"], "arguments": {}, "reason": "malformed"}])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["trace"][0]["action"], "invalid_action")

    def test_known_conflict_requires_followup_search_before_finishing(self):
        docs = [document("T01", 30), document("T02", 15)]
        result, _ = self.run_actions([
            action("read", doc_id="T01"), action("read", doc_id="T02"),
            action("finish", status="conflict", answer="30天与15天冲突", citations=[citation(d) for d in docs], gaps=[]),
        ], docs)
        finish = next(s for s in result["trace"] if s["action"] == "finish")
        self.assertEqual(finish["observation"]["code"], "validation_error")
        self.assertIn("检索", finish["observation"]["error"])
        self.assertNotEqual(result["status"], "conflict")

    def test_non_string_history_role_is_controlled_input_error(self):
        agent = Agent(MockModel(), KnowledgeBase(self.data_file()))
        with self.assertRaises(ValueError):
            agent.run("报销期限多久？", [{"role": ["user"], "content": "hello"}])
