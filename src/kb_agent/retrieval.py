"""Small, inspectable lexical retrieval tools for the synthetic policy corpus.

Search is discovery only. A caller must read a document before citing it.
This module intentionally makes no embeddings, external services or model calls.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import json
import math
from pathlib import Path
import re
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_CORPUS_BYTES = 2_000_000
MAX_QUERY_LENGTH = 2_000

# Curated domain vocabulary: transparent, bounded, and testable on this corpus.
SYNONYMS = {
    "expense": ("报销", "报账", "报帐", "报费用", "费用申请", "垫付", "reimbursement", "expense"),
    "deadline": ("期限", "截止", "时限", "有效期", "几天内", "多长时间", "多久", "最迟", "deadline"),
    "process": ("流程", "步骤", "怎么报", "如何报", "怎么操作", "凭证", "发票", "票据", "process"),
    "annual_leave": ("年假", "带薪休假", "休年假", "年休", "annual_leave", "annual leave"),
    "advance": ("提前", "事先", "预先", "提前期", "advance"),
    "scope": ("范围", "适用", "部门", "适合", "scope"),
    "priority": ("优先级", "优先", "哪份", "哪个制度", "以谁为准", "以哪个为准", "priority"),
    "support": ("技术支持", "it服务台", "it 服务台", "it支持", "电脑坏", "电脑故障", "系统故障", "helpdesk", "support"),
    "contact": ("联系", "邮箱", "邮件", "找谁", "contact"),
}
STOP_TERMS = {
    "请问", "需要", "要提", "提前", "多久", "多少", "什么", "怎么", "如何", "是否", "可以", "哪些",
    "公司", "员工", "制度", "问题", "一下", "有关", "相关", "关于", "我的", "我们", "这个", "那个", "规定",
    "the", "a", "an", "is", "of", "to", "and", "for", "how", "what", "in", "please",
}


def project_path(path: str | Path) -> Path:
    """Resolve only paths inside this project, including symlink targets."""
    candidate = Path(path)
    resolved = (PROJECT_ROOT / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError("路径必须位于项目目录内")
    return resolved


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _concepts(text: str) -> set[str]:
    text = _normalise(text)
    return {canonical for canonical, variants in SYNONYMS.items() if any(term in text for term in variants)}


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for word in re.findall(r"[a-z][a-z0-9_]+|[\u3400-\u9fff]+", _normalise(text)):
        if word.isascii():
            tokens.add(word)
        elif len(word) >= 2:
            tokens.update(word[index:index + 2] for index in range(len(word) - 1))
    return tokens - STOP_TERMS


def _error(code: str, message: str, retryable: bool = False) -> dict:
    return {"ok": False, "code": code, "error": message, "retryable": retryable}


class KnowledgeBase:
    """Read-only corpus with bounded, deterministic failure injection for tests.

    Fault counters are per instance: N initial calls fail, then tools recover.
    Source files are never mutated. Read results are copies, so observations
    cannot mutate the corpus or contaminate subsequent questions.
    """

    def __init__(self, path: str | Path, fail_searches: int = 0, fail_reads: int = 0, *, use_synonyms: bool = True):
        for label, value in (("fail_searches", fail_searches), ("fail_reads", fail_reads)):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100_000:
                raise ValueError(f"{label} 必须是 0 至 100000 的整数")
        if not isinstance(use_synonyms, bool):
            raise ValueError("use_synonyms 必须是布尔值")
        self.use_synonyms = use_synonyms
        self.path = project_path(path)
        if not self.path.is_file():
            raise ValueError("知识库文件不存在或不是普通文件")
        if self.path.stat().st_size > MAX_CORPUS_BYTES:
            raise ValueError("知识库文件超过 2 MB 上限")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("无法读取知识库 JSON") from exc
        documents = payload.get("documents") if isinstance(payload, dict) else None
        if not isinstance(documents, list):
            raise ValueError("知识库必须包含 documents 数组")
        self._documents: dict[str, dict] = {}
        self._terms: dict[str, set[str]] = {}
        self._concept_index: dict[str, set[str]] = {}
        self._discarded: dict[str, int] = {}
        for raw in documents:
            document = self._validate_document(raw)
            doc_id = document["doc_id"]
            if doc_id in self._documents:
                raise ValueError(f"重复的文档 ID: {doc_id}")
            original_facts = document.get("facts", [])
            valid_facts = [fact for fact in original_facts if self._valid_fact(fact, document["content"])]
            self._discarded[doc_id] = len(original_facts) - len(valid_facts)
            document["facts"] = valid_facts
            self._documents[doc_id] = document
            searchable = " ".join(document[key] for key in ("title", "content", "topic"))
            self._terms[doc_id] = _tokens(searchable)
            self._concept_index[doc_id] = _concepts(searchable)
        self._document_frequency = Counter(term for terms in self._terms.values() for term in terms)
        self._remaining_search_failures = fail_searches
        self._remaining_read_failures = fail_reads

    @staticmethod
    def _validate_document(raw: object) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("documents 中每项必须是对象")
        for key in ("doc_id", "version_date", "title", "content", "topic"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise ValueError(f"文档字段 {key} 必须是非空字符串")
        if len(raw["doc_id"]) > 100:
            raise ValueError("doc_id 长度不得超过 100")
        try:
            date.fromisoformat(raw["version_date"])
        except ValueError as exc:
            raise ValueError("version_date 必须是 ISO 日期 YYYY-MM-DD") from exc
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw["version_date"]):
            raise ValueError("version_date 必须是 ISO 日期 YYYY-MM-DD")
        if not isinstance(raw.get("facts", []), list):
            raise ValueError("facts 必须是数组")
        return deepcopy(raw)

    @staticmethod
    def _valid_fact(fact: object, content: str) -> bool:
        # A changed source paragraph immediately invalidates the old annotation.
        # This is structural validation, NOT a general semantic entailment check.
        return (
            isinstance(fact, dict)
            and all(isinstance(fact.get(key), str) and fact[key].strip() for key in ("key", "value", "quote"))
            and fact["quote"] in content
            and fact["value"] in fact["quote"]
        )

    def search(self, query: str, limit: int = 5) -> dict:
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LENGTH:
            return _error("INVALID_QUERY", "检索词须为 1 至 2000 字符的非空字符串")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            return _error("INVALID_LIMIT", "limit 须为 1 至 20 的整数")
        if self._remaining_search_failures:
            self._remaining_search_failures -= 1
            return _error("SEARCH_UNAVAILABLE", "合成故障：检索服务暂时不可用", True)
        query_terms = _tokens(query)
        concepts = _concepts(query) if self.use_synonyms else set()
        domains = concepts & {"expense", "annual_leave", "support"}
        count = len(self._documents)
        ranked = []
        for doc_id, document in self._documents.items():
            if domains and not domains & self._concept_index[doc_id]:
                continue
            shared_terms = query_terms & self._terms[doc_id]
            shared_concepts = concepts & self._concept_index[doc_id]
            if not shared_terms and not shared_concepts:
                continue
            score = 8.0 * len(shared_concepts)
            score += sum(math.log(1 + (count + 1) / (self._document_frequency[term] + 1)) for term in shared_terms)
            if document["topic"] in query:
                score += 10.0
            ranked.append((score, doc_id, document))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        results = []
        for score, doc_id, document in ranked[:limit]:
            results.append({
                "doc_id": doc_id,
                "version_date": document["version_date"],
                "title": document["title"],
                "topic": document["topic"],
                "snippet": document["content"][:160],
                "score": round(score, 4),
            })
        return {"ok": True, "query": query, "results": results, "total": len(ranked), "returned": len(results)}

    def read(self, doc_id: str) -> dict:
        if not isinstance(doc_id, str) or not doc_id.strip() or len(doc_id) > 100:
            return _error("INVALID_DOCUMENT_ID", "doc_id 须为 1 至 100 字符的非空字符串")
        if self._remaining_read_failures:
            self._remaining_read_failures -= 1
            return _error("READ_UNAVAILABLE", "合成故障：原文读取暂时不可用", True)
        if doc_id not in self._documents:
            return _error("DOCUMENT_NOT_FOUND", "未找到该文档 ID")
        return {
            "ok": True,
            "document": deepcopy(self._documents[doc_id]),
            "discarded_fact_count": self._discarded[doc_id],
        }
