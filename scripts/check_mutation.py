"""Generate actual before/after document-replacement evidence within the project.

Run: python -B scripts/check_mutation.py
All three runs use MockModel and demonstrate engineering behavior, not LLM quality.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kb_agent.models import MockModel
from kb_agent.retrieval import KnowledgeBase
from kb_agent.runtime import Agent
from evaluate import write_json


def main():
    original = {
        "doc_id": "M01", "version_date": "2026-01-01", "title": "合成报销期限制度",
        "topic": "expense_deadline", "content": "报销申请须在费用发生后30天内提交。",
        "facts": [{"key": "expense_deadline", "value": "30天", "quote": "报销申请须在费用发生后30天内提交。"}],
    }
    stale = deepcopy(original)
    stale["content"] = "报销申请须在费用发生后7天内提交。"
    updated = deepcopy(stale)
    updated["facts"] = [{"key": "expense_deadline", "value": "7天", "quote": updated["content"]}]
    variants = [
        ("original", original, "answered", "30天"),
        ("content_changed_stale_annotation", stale, "needs_clarification", None),
        ("content_and_annotation_updated", updated, "answered", "7天"),
    ]
    rows = []
    with tempfile.TemporaryDirectory(prefix="mutation-", dir=ROOT / "tests") as work:
        for name, document, expected_status, expected_phrase in variants:
            path = Path(work) / (name + ".json")
            payload = {"documents": [document]}
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = Agent(MockModel(), KnowledgeBase(path)).run("报销期限多久？")
            errors = []
            if result["status"] != expected_status:
                errors.append(f"expected {expected_status}, got {result['status']}")
            if expected_phrase and expected_phrase not in result["answer"]:
                errors.append("answer does not reflect the current document")
            if name != "original" and "30天" in result["answer"]:
                errors.append("answer retained the old source value")
            for cited in result["citations"]:
                if cited["quote"] not in document["content"]:
                    errors.append("citation is not from the current document")
            rows.append({"id": name, "input": {"question": result["question"], "knowledge_base": payload},
                         "expected_status": expected_status, "output": result,
                         "checks": {"passed": not errors, "errors": errors}})
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "model_mode": "mock",
        "evidence_scope": "三次实际离线运行验证内容替换与旧标注失效；不证明真实模型语义判断能力。",
        "method": "保持问题与文档ID不变，依次替换正文、再同步事实标注；每次新建知识库重新读取。",
        "source_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(list((ROOT / "src").rglob("*.py")) + [Path(__file__).resolve()])},
        "total": len(rows), "passed": sum(row["checks"]["passed"] for row in rows),
        "failed": sum(not row["checks"]["passed"] for row in rows), "cases": rows,
    }
    write_json(ROOT / "examples/content-replacement.json", report)
    print(json.dumps({key: report[key] for key in ("total", "passed", "failed", "model_mode")}, ensure_ascii=False))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
