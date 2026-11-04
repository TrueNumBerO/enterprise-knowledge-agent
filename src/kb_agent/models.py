"""Swappable model adapters. MockModel proves workflow only, never LLM quality."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .config import ConfigError, load_local_env
from .runtime import (contextual_question, find_conflicts, missing_requested_fact,
                      needs_context, query_subject, requested_fact,
                      uncertain_multiple_sources, valid_facts)


class ModelError(RuntimeError):
    """Safe provider/configuration error without credentials or response bodies."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelError("拒绝模型 API HTTP 重定向")


class LiveModel:
    mode = "live"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, timeout: float | None = None,
                 config_file: str | None = None):
        try:
            local_config = load_local_env(config_file)
        except ConfigError as exc:
            raise ModelError(str(exc)) from None

        def setting(keys: tuple[str, ...], default: str) -> str:
            # An explicitly empty process variable also overrides the file.
            for source in (os.environ, local_config):
                for key in keys:
                    if key in source:
                        return source[key]
            return default

        self.api_key = api_key if api_key is not None else setting(("KB_AGENT_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"), "")
        self.base_url = base_url if base_url is not None else setting(("KB_AGENT_BASE_URL",), "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model = model if model is not None else setting(("KB_AGENT_MODEL",), "qwen-plus")
        try:
            self.timeout = float(timeout if timeout is not None else setting(("KB_AGENT_TIMEOUT",), "30"))
        except (TypeError, ValueError):
            raise ModelError("KB_AGENT_TIMEOUT 必须是秒数") from None
        if not isinstance(self.api_key, str) or not self.api_key.strip() or "\n" in self.api_key or "\r" in self.api_key:
            raise ModelError("请在项目根目录.env填写KB_AGENT_API_KEY，或配置相应进程环境变量")
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 200:
            raise ModelError("模型名称无效")
        if not 0 < self.timeout <= 120:
            raise ModelError("模型超时须在 0 至 120 秒之间")
        try:
            parsed = urllib.parse.urlsplit(self.base_url)
            _ = parsed.port
            if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError()
            if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
                raise ValueError()
        except (ValueError, TypeError):
            raise ModelError("API URL 须为无用户信息、查询参数或片段的 HTTPS 地址；仅本地测试允许 HTTP") from None
        self.is_deepseek = parsed.hostname == "api.deepseek.com"
        self.endpoint = self.base_url.rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint += "/chat/completions"

    def public_config(self) -> dict:
        """Safe evaluation metadata; never include credentials or local values."""
        return {"model": self.model, "endpoint": self.endpoint, "timeout_seconds": self.timeout,
                "thinking": "disabled" if self.is_deepseek else "provider_default",
                "max_output_tokens": 4096 if self.is_deepseek else None}

    def _request(self, payload: dict) -> dict:
        request = urllib.request.Request(self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"}, method="POST")
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ModelError("模型响应超过大小上限")
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ModelError("模型响应不是 JSON 对象")
            return value
        except ModelError:
            raise
        except urllib.error.HTTPError as exc:
            raise ModelError(f"模型 HTTP 请求失败（状态 {exc.code}）") from None
        except Exception:
            raise ModelError("模型请求失败或响应不是合法 JSON") from None

    def decide(self, messages: list[dict], tools: list[dict]) -> dict:
        payload = {"model": self.model, "messages": messages, "tools": tools,
                   "tool_choice": "required", "parallel_tool_calls": False, "temperature": 0}
        if self.is_deepseek:
            # DeepSeek defaults to thinking, which rejects tool_choice=required.
            # This adapter uses the documented non-thinking tool-call interface.
            payload.update(thinking={"type": "disabled"}, max_tokens=4096)
            payload.pop("parallel_tool_calls")
        response = self._request(payload)
        try:
            choice = response["choices"][0]
            if choice.get("finish_reason") in {"length", "content_filter"}:
                raise ValueError()
            message = choice["message"]
            calls = message.get("tool_calls")
            if calls:
                if not isinstance(calls, list):
                    raise ValueError()
                parsed_calls = []
                for call in calls:
                    function = call["function"]
                    args = json.loads(function["arguments"])
                    if not isinstance(args, dict):
                        raise ValueError()
                    if len(calls) > 1:
                        # Validate even unexecuted proposals. A batch may contain
                        # only read-only tools; finishing together with other
                        # actions could otherwise hide unfinished evidence work.
                        self._validate_readonly_proposal(function["name"], args)
                        if call.get("type", "function") != "function":
                            raise ValueError()
                    parsed_calls.append((function["name"], args))
                name, args = parsed_calls[0]
                reason = args.pop("reason", "模型根据最新工具观察选择动作。")
                if len(parsed_calls) > 1:
                    # Do not queue proposals: the next model request must observe
                    # this action's actual result before deciding what to do next.
                    reason = (f"模型本轮返回{len(parsed_calls)}个工具调用，按返回顺序只执行首个；"
                              "其余不执行、不排队，下一轮根据新观察重新决策。" + reason)
                return {"action": name, "arguments": args, "reason": reason}
            content = message.get("content", "")
            if not isinstance(content, str):
                raise ValueError()
            if content.startswith("```json\n") and content.endswith("\n```"):
                content = content[8:-4]
            action = json.loads(content)
            if not isinstance(action, dict):
                raise ValueError()
            return action
        except (ValueError, KeyError, IndexError, TypeError):
            raise ModelError("模型未返回可安全执行的合法动作") from None

    @staticmethod
    def _validate_readonly_proposal(name: str, args: dict) -> None:
        """Check every proposal before reducing a read-only batch to one action."""
        if not isinstance(name, str) or name not in {"search", "read"}:
            raise ValueError()
        if "reason" in args and not isinstance(args["reason"], str):
            raise ValueError()
        if name == "read":
            if (set(args) - {"doc_id", "reason"}
                    or not isinstance(args.get("doc_id"), str)
                    or not args["doc_id"].strip() or len(args["doc_id"]) > 100):
                raise ValueError()
        else:
            if (set(args) - {"query", "limit", "reason"}
                    or not isinstance(args.get("query"), str)
                    or not args["query"].strip() or len(args["query"]) > 4000):
                raise ValueError()
            limit = args.get("limit", 5)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
                raise ValueError()


def _action(name: str, args: dict, reason: str) -> dict:
    return {"action": name, "arguments": args, "reason": reason}


def _finish(status: str, answer: str, citations: list | None = None, gaps: list | None = None, reason: str = "依据当前观察结束。") -> dict:
    return _action("finish", {"status": status, "answer": answer, "citations": citations or [], "gaps": gaps or []}, reason)


def _citation(doc: dict, quote: str | None = None) -> dict:
    return {"doc_id": doc["doc_id"], "version_date": doc["version_date"], "quote": quote or doc["content"]}


class MockModel:
    """Deterministic observation-driven simulator; explicitly NOT a real LLM.

    State is reconstructed from messages on each call, so a model instance is safe
    to reuse between sequential runs. Never reads hidden KB data or prebuilt traces.
    """
    mode = "mock"

    def decide(self, messages: list[dict], tools: list[dict]) -> dict:
        request = json.loads(messages[1]["content"])
        question = request["question"]
        history = request.get("history", [])
        contextual = contextual_question(question, history)
        context_missing = needs_context(question) and query_subject(contextual) is None
        observations = []
        for message in messages[2:]:
            if message.get("role") == "user":
                try:
                    obj = json.loads(message["content"])
                    if "observation" in obj:
                        observations.append(obj)
                except (ValueError, TypeError):
                    pass
        if not observations:
            if context_missing:
                return _finish("needs_clarification", "请补充您要查询的制度、产品或事项。", gaps=["缺少查询主题或可用对话上下文。"], reason="指代不明确且没有可用历史。")
            return _action("search", {"query": contextual, "limit": 5}, "先检索问题及必要的历史主题。")
        latest = observations[-1]
        if not latest["observation"].get("ok") and latest["action"] != "finish":
            failures = [o for o in observations if o["action"] == latest["action"] and o["arguments"] == latest["arguments"] and not o["observation"].get("ok")]
            if latest["observation"].get("retryable") and len(failures) < 2:
                return _action(latest["action"], latest["arguments"], "工具标记为暂时失败，结合观察只再尝试一次。")
            return _finish("tool_error", "工具失败，无法完成资料查证。", gaps=["需要恢复检索或文档读取工具后重试。"], reason="观察到工具连续失败或不可重试错误。")
        searches = [o for o in observations if o["action"] == "search" and o["observation"].get("ok")]
        docs = {o["observation"]["document"]["doc_id"]: o["observation"]["document"]
                for o in observations if o["action"] == "read" and o["observation"].get("ok")}
        candidates = {}
        for search in searches:
            for doc in search["observation"].get("results", []):
                candidates[doc["doc_id"]] = doc
        if not candidates:
            if len(searches) < 2:
                return _action("search", {"query": self._broaden(contextual), "limit": 5}, "首轮没有候选，使用更短的主题词补充检索。")
            return _finish("out_of_scope", "现有知识库没有相关依据。", gaps=["需要补充与问题相关的制度或产品资料。"], reason="两次检索均未找到资料。")
        fact_requested = requested_fact(contextual)
        conflicts = find_conflicts(list(docs.values()))
        if fact_requested:
            conflicts = {key: rows for key, rows in conflicts.items() if key == fact_requested}
        verified = any("适用范围 优先级" in s["arguments"].get("query", "") for s in searches)
        if conflicts and not verified:
            return _action("search", {"query": next(iter(conflicts)) + " 适用范围 优先级", "limit": 5}, "原文出现不同规则，补搜适用范围或优先级以查证冲突。")
        # Only inspect the highest ranked topic, plus explicit conflict-scope evidence.
        first = next(iter(candidates.values()))
        topic = first.get("topic")
        relevant = [d for d in candidates.values() if fact_requested or not topic or d.get("topic") == topic or (conflicts and d.get("topic") == "expense_scope")]
        for candidate in relevant:
            if candidate["doc_id"] not in docs:
                return _action("read", {"doc_id": candidate["doc_id"]}, "读取候选原文，核对版本与引用依据。")
        selected = [docs[d["doc_id"]] for d in relevant if d["doc_id"] in docs]
        if any(doc.get("discarded_fact_count", 0) for doc in selected):
            return _finish("needs_clarification", "原文与结构化事实标注不一致，请确认更新后的制度。", [_citation(d) for d in selected],
                           ["资料标注过期；离线模型无法可靠判断新的语义关系。"], "已读取更新后的原文，拒绝继续引用过期事实标注。")
        if missing_requested_fact(contextual, selected):
            return _finish("needs_clarification", "相关资料没有说明问题所需的事实维度。", [_citation(d) for d in selected],
                           ["请补充能直接回答所问事项的制度。"], "已读取相关候选，但申请提前期/报销期限不能回答年度天数/金额上限。")
        if uncertain_multiple_sources(selected):
            return _finish("needs_clarification", "缺少可靠标注，无法证实同主题多份资料是否一致。", [_citation(d) for d in selected],
                           ["请核对同主题原文并补充可靠事实标注。"], "没有检测到已标注冲突不代表证明原文一致，保守请求核实。")
        if conflicts:
            citations = []
            for rows in conflicts.values():
                for doc, fact in rows:
                    citation = _citation(doc, fact["quote"])
                    if citation not in citations:
                        citations.append(citation)
            return _finish("conflict", "发现冲突，需要确认适用制度。", citations,
                           ["缺少可消解冲突的适用范围和优先级。"], "补充查证后仍无明确优先级，披露双方原文并追问。")
        if not selected:
            return _finish("incomplete", "未读取到可用原文。", gaps=["需要读取检索候选。"])
        citations = []
        for doc in selected:
            facts = valid_facts(doc)
            if fact_requested:
                facts = [fact for fact in facts if fact["key"] == fact_requested]
                if not facts:
                    continue
            citations.append(_citation(doc, facts[0]["quote"] if facts else doc["content"]))
        return _finish("answered", "根据已核验资料回答。", citations, reason="相关候选已读取且未发现已标注规则冲突，返回原文依据。")

    @staticmethod
    def _needs_context(text: str) -> bool:
        return needs_context(text)

    @staticmethod
    def _has_subject(text: str) -> bool:
        return query_subject(text) is not None

    @staticmethod
    def _broaden(text: str) -> str:
        for terms, query in ((("报销", "报账", "垫付", "费用"), "报销"), (("年假", "休假", "请假"), "年假"), (("IT", "电脑", "服务台"), "IT 服务台")):
            if any(term in text for term in terms):
                return query
        return text.replace("请问", "").replace("请告诉我", "").replace("？", "").replace("?", "").strip()
