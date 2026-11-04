"""HTTP boundary protocol tests. Stubbed responses are NOT live model evidence."""
import io
import json
from types import SimpleNamespace
import urllib.error
from unittest.mock import patch

from helpers import ProjectFixture, action, citation, document
from kb_agent.models import LiveModel, ModelError
from kb_agent.retrieval import KnowledgeBase
from kb_agent.runtime import Agent, TOOLS


def response_for(act):
    args = dict(act["arguments"], reason=act.get("reason", "test"))
    return {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "tool_calls": [{"id": "stub_call", "type": "function", "function": {"name": act["action"], "arguments": json.dumps(args, ensure_ascii=False)}}]}}]}


def response_for_batch(actions):
    response = response_for(actions[0])
    calls = [response_for(act)["choices"][0]["message"]["tool_calls"][0] for act in actions]
    for index, call in enumerate(calls):
        call["id"] = f"stub_call_{index}"
    response["choices"][0]["message"]["tool_calls"] = calls
    return response


class LiveProtocolTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.empty_config = self.work / "protocol-fixture.env"
        self.empty_config.write_text("", encoding="utf-8")

    def live_model(self, **kwargs):
        kwargs.setdefault("config_file", self.empty_config)
        return LiveModel(**kwargs)

    def test_http_requests_include_new_observations_and_tool_schema(self):
        scripted = [action("search", query="报销期限"), action("read", doc_id="T01"), action("finish", status="answered", answer="30天", citations=[citation()], gaps=[])]
        requests = []
        def fake_open(request, timeout):
            requests.append({"url": request.full_url, "body": json.loads(request.data), "authorization": request.get_header("Authorization"), "timeout": timeout})
            return io.BytesIO(json.dumps(response_for(scripted[len(requests) - 1]), ensure_ascii=False).encode())
        with patch("kb_agent.models.urllib.request.build_opener", return_value=SimpleNamespace(open=fake_open)):
            result = Agent(self.live_model(api_key="stub-secret", base_url="http://127.0.0.1:9999/v1", model="protocol-stub", timeout=2), KnowledgeBase(self.data_file())).run("报销期限多久？")
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["model_mode"], "live")
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[0]["url"], "http://127.0.0.1:9999/v1/chat/completions")
        self.assertEqual(requests[0]["authorization"], "Bearer stub-secret")
        self.assertEqual(requests[0]["body"]["tool_choice"], "required")
        self.assertEqual({x["function"]["name"] for x in requests[0]["body"]["tools"]}, {"search", "read", "finish"})
        second = json.dumps(requests[1]["body"]["messages"], ensure_ascii=False)
        third = json.dumps(requests[2]["body"]["messages"], ensure_ascii=False)
        self.assertIn("T01", second)
        self.assertIn("observation", second)
        self.assertIn("报销申请须在费用发生后30天内提交。", third)
        self.assertNotIn("stub-secret", json.dumps(result, ensure_ascii=False))

    def test_http_provider_failure_has_no_mock_fallback_or_secret_leak(self):
        failure = urllib.error.HTTPError("https://example.test?key=stub-secret", 401, "stub-secret provider body", {}, io.BytesIO(b"stub-secret"))
        with patch("kb_agent.models.urllib.request.build_opener", return_value=SimpleNamespace(open=lambda *a, **k: (_ for _ in ()).throw(failure))):
            result = Agent(self.live_model(api_key="stub-secret"), KnowledgeBase(self.data_file())).run("报销期限多久？")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["model_mode"], "live")
        self.assertNotIn("stub-secret", json.dumps(result, ensure_ascii=False))
        self.assertEqual([x["action"] for x in result["trace"]], ["model_error"])

    def test_malformed_and_finish_mixed_model_responses_are_rejected(self):
        model = self.live_model(api_key="stub-secret")
        mixed = response_for_batch([action("search", query="test"), action("finish", status="out_of_scope", answer="", citations=[], gaps=[])])
        for response in [{}, {"choices": []}, {"choices": [{"message": {"content": "not json"}}]}, mixed, {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}]:
            with self.subTest(response=response), patch.object(model, "_request", return_value=response):
                with self.assertRaises(ModelError):
                    model.decide([], TOOLS)

    def test_plain_json_action_is_supported(self):
        expected = action("search", query="报销")
        with patch.object(LiveModel, "_request", return_value={"choices": [{"message": {"content": json.dumps(expected)}}]}):
            self.assertEqual(self.live_model(api_key="stub-secret").decide([], TOOLS), expected)

    def test_insecure_remote_endpoint_is_rejected(self):
        for url in ["http://example.com/v1", "https://user:password@example.com", "https://example.com?key=secret"]:
            with self.subTest(url=url), self.assertRaises(ModelError):
                self.live_model(api_key="stub-secret", base_url=url)

    def test_read_batch_returns_first_model_action_and_reports_replanning(self):
        model = self.live_model(api_key="stub-secret")
        batch = response_for_batch([action("read", doc_id="T01"), action("read", doc_id="T02")])
        with patch.object(model, "_request", return_value=batch):
            parsed = model.decide([], TOOLS)
        self.assertEqual(parsed["action"], "read")
        self.assertEqual(parsed["arguments"], {"doc_id": "T01"})
        self.assertIn("2", parsed["reason"])
        self.assertRegex(parsed["reason"], r"(?:只|仅)执行(?:首个|第1个)")
        self.assertIn("重新决策", parsed["reason"])

    def test_invalid_later_batch_call_cannot_be_ignored(self):
        model = self.live_model(api_key="stub-secret")
        invalid_seconds = [
            action("delete_all", path="D:/"),
            action("finish", status="answered", answer="30天", citations=[], gaps=[]),
            action("read", doc_id=""),
            action("read", doc_id=["T02"]),
            action("read", doc_id="T02", unexpected="field"),
            action("search", query=["报销"]),
            action("search", query="报销", limit=True),
        ]
        for second in invalid_seconds:
            response = response_for_batch([action("read", doc_id="T01"), second])
            with self.subTest(second=second), patch.object(model, "_request", return_value=response):
                with self.assertRaises(ModelError):
                    model.decide([], TOOLS)
        for malformed in ["{broken", "[]", "null"]:
            response = response_for_batch([action("read", doc_id="T01"), action("read", doc_id="T02")])
            response["choices"][0]["message"]["tool_calls"][1]["function"]["arguments"] = malformed
            with self.subTest(arguments=malformed), patch.object(model, "_request", return_value=response):
                with self.assertRaises(ModelError):
                    model.decide([], TOOLS)

    def test_batch_read_observation_causes_fresh_model_decision_not_queued_read(self):
        responses = [
            response_for(action("search", query="报销期限")),
            response_for_batch([action("read", doc_id="T01"), action("read", doc_id="T02")]),
            response_for(action("search", query="报销适用范围")),
            response_for(action("finish", status="needs_clarification", answer="需要确认", citations=[], gaps=["适用范围不足"])),
        ]
        requests = []
        def fake_open(request, timeout):
            requests.append(json.loads(request.data))
            return io.BytesIO(json.dumps(responses[len(requests) - 1], ensure_ascii=False).encode())
        with patch("kb_agent.models.urllib.request.build_opener", return_value=SimpleNamespace(open=fake_open)):
            model = self.live_model(api_key="stub-secret", base_url="https://api.deepseek.com", model="deepseek-flash")
            result = Agent(model, KnowledgeBase(self.data_file([document("T01"), document("T02")]))).run("报销期限多久？")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual([step["action"] for step in result["trace"]], ["search", "read", "search", "finish"])
        self.assertEqual(len(requests), 4)
        reads = [step for step in result["trace"] if step["action"] == "read"]
        self.assertEqual([step["arguments"]["doc_id"] for step in reads], ["T01"])
        observations = []
        for message in requests[2]["messages"]:
            if message["role"] == "user":
                value = json.loads(message["content"])
                if "observation" in value:
                    observations.append(value["observation"])
        read_docs = [value["document"] for value in observations if value.get("ok") and "document" in value]
        self.assertEqual([doc["doc_id"] for doc in read_docs], ["T01"])
        self.assertEqual(read_docs[0]["content"], document()["content"])

    def test_batch_response_cannot_execute_past_step_budget(self):
        responses = [response_for(action("search", query="报销期限")),
                     response_for_batch([action("read", doc_id="T01"), action("read", doc_id="T02")])]
        model = self.live_model(api_key="stub-secret")
        with patch.object(model, "_request", side_effect=responses) as request:
            result = Agent(model, KnowledgeBase(self.data_file([document("T01"), document("T02")])), max_steps=2).run("报销期限多久？")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["steps"], 2)
        self.assertEqual(request.call_count, 2)
        self.assertEqual([step["action"] for step in result["trace"]], ["search", "read"])
        self.assertEqual(result["trace"][1]["arguments"]["doc_id"], "T01")

    def test_deepseek_payload_uses_non_thinking_required_tools(self):
        config = self.work / "empty.env"
        config.write_text("", encoding="utf-8")
        model = LiveModel(api_key="fixture-only-secret", base_url="https://api.deepseek.com", model="deepseek-flash", timeout=60, config_file=config)
        with patch.object(model, "_request", return_value=response_for(action("search", query="报销"))) as request:
            model.decide([{"role": "user", "content": "报销期限多久？"}], TOOLS)
        payload = request.call_args.args[0]
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["tool_choice"], "required")
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertNotIn("parallel_tool_calls", payload)
        self.assertNotIn("fixture-only-secret", json.dumps(payload))
        self.assertNotIn("fixture-only-secret", json.dumps(model.public_config()))

    def test_non_deepseek_payload_keeps_generic_tool_behavior(self):
        config = self.work / "empty.env"
        config.write_text("", encoding="utf-8")
        model = LiveModel(api_key="fixture-only-secret", base_url="https://provider.example/v1", model="generic-model", config_file=config)
        with patch.object(model, "_request", return_value=response_for(action("search", query="报销"))) as request:
            model.decide([], TOOLS)
        payload = request.call_args.args[0]
        self.assertNotIn("thinking", payload)
        self.assertNotIn("max_tokens", payload)
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertEqual(payload["tool_choice"], "required")
