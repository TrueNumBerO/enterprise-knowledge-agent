"""Replay acceptance cases and save actual inputs, outputs and traces.

Run: python -B scripts/evaluate.py
Offline results demonstrate engineering behavior, not live model quality.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kb_agent.models import MockModel, LiveModel, ModelError
from kb_agent.retrieval import KnowledgeBase, project_path
from kb_agent.runtime import Agent


def write_json(path, value):
    path = project_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_case(case, output):
    errors = []
    expected = case.get("expected_status")
    if expected and output["status"] != expected:
        errors.append(f"status expected={expected}, actual={output['status']}")
    required_ids = case.get("required_citations", case.get("expected_doc_ids", []))
    cited_ids = {item["doc_id"] for item in output["citations"]}
    for doc_id in required_ids:
        if doc_id not in cited_ids:
            errors.append(f"missing citation {doc_id}")
    for phrase in case.get("answer_contains", case.get("expected_contains", [])):
        if phrase not in output["answer"]:
            errors.append(f"answer missing {phrase}")
    for phrase in case.get("answer_not_contains", []):
        if phrase in output["answer"]:
            errors.append(f"answer unexpectedly contains {phrase}")
    documents = {}
    for step in output["trace"]:
        observation = step.get("observation", {})
        if step["action"] == "read" and observation.get("ok"):
            doc = observation["document"]
            documents[doc["doc_id"]] = doc
    for cited in output["citations"]:
        doc = documents.get(cited["doc_id"])
        if not doc or cited["version_date"] != doc["version_date"] or not cited["quote"] or cited["quote"] not in doc["content"]:
            errors.append("citation does not match a source read during this run")
    if output["status"] == "answered" and not output["citations"]:
        errors.append("answered without citations")
    if len(output["trace"]) > case.get("max_steps", 8):
        errors.append("step budget exceeded")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--cases", default="examples/cases.json")
    parser.add_argument("--check-config", action="store_true", help="仅检查live配置，不发送请求或写评测结果")
    args = parser.parse_args()
    if args.check_config:
        if args.mode != "live":
            raise ValueError("--check-config 需要 --mode live")
        model = LiveModel()
        print(json.dumps({"configured": True, "network_called": False, "model_config": model.public_config()}, ensure_ascii=False, indent=2))
        return 0
    cases = json.loads(project_path(args.cases).read_text(encoding="utf-8-sig"))
    if isinstance(cases, dict):
        cases = cases["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases 必须为非空列表")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"]):
            raise ValueError("case id 必须是仅包含字母、数字、下划线和短横线的安全文件名")
        if case["id"] in seen:
            raise ValueError("case id 不能重复")
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError("case question 必须是非空字符串")
        seen.add(case["id"])
    # Fail once before writing any output if the live configuration is absent.
    live_model = LiveModel() if args.mode == "live" else None
    output_dir = ROOT / "examples" / ("outputs" if args.mode == "mock" else "live-outputs")
    rows = []
    for case in cases:
        start = time.perf_counter()
        kb = KnowledgeBase(project_path(case.get("data", "data/knowledge.json")), fail_searches=case.get("fail_searches", 0), fail_reads=case.get("fail_reads", 0))
        model = MockModel() if args.mode == "mock" else live_model
        result = Agent(model, kb, max_steps=case.get("max_steps", 8)).run(case["question"], history=case.get("history"))
        errors = verify_case(case, result)
        record = {"input": case, "output": result, "checks": {"passed": not errors, "errors": errors}}
        filename = f"{case['id']}.json"
        write_json(output_dir / filename, record)
        rows.append({"id": case["id"], "expected_status": case.get("expected_status"), "actual_status": result["status"], "passed": not errors, "errors": errors, "steps": len(result["trace"]), "actions": [step["action"] for step in result["trace"]], "record": str((output_dir / filename).relative_to(ROOT)).replace("\\", "/"), "duration_seconds": round(time.perf_counter() - start, 4)})
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "source_sha256": {
            str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(ROOT.glob("src/**/*.py")) | set(ROOT.glob("tests/*.py")) | set(ROOT.glob("scripts/*.py")) | set(ROOT.glob("data/*.json")) | {project_path(args.cases)})
        },
        "model_mode": args.mode,
        "model_config": live_model.public_config() if live_model else {"model": "offline-mock"},
        "evidence_scope": "离线 Mock：只证明流程、检索、引用约束及故障处理；不证明真实模型决策效果。" if args.mode == "mock" else "真实配置模型运行；需结合逐项实际输出检查语义正确性。",
        "total": len(rows), "passed": sum(row["passed"] for row in rows), "failed": sum(not row["passed"] for row in rows), "cases": rows,
    }
    filename = "evaluation.json" if args.mode == "mock" else "live-evaluation.json"
    write_json(ROOT / "examples" / filename, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError, ModelError) as exc:
        message = str(exc) if isinstance(exc, (ModelError, ValueError)) else "评估输入或文件不可用"
        print(json.dumps({"error": {"code": "evaluation_configuration_error", "message": message}}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)

