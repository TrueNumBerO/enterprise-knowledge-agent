"""CLI entry point; every input/output file stays inside this project."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .models import LiveModel, MockModel, ModelError
from .runtime import Agent

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(value: str | Path) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError("输入和输出路径必须位于项目目录内")
    return resolved


def main(argv: list[str] | None = None) -> int:
    # Keep redirected Windows output and saved evaluation logs valid UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="企业知识问答 Agent（默认离线 Mock，不代表真实模型效果）")
    parser.add_argument("--question", required=True)
    parser.add_argument("--history", help="项目内 JSON 对话列表文件")
    parser.add_argument("--data", default="data/knowledge.json")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--fail-searches", type=int, default=0)
    parser.add_argument("--fail-reads", type=int, default=0)
    parser.add_argument("--output", help="项目内 JSON 结果路径")
    args = parser.parse_args(argv)
    try:
        # Resolve all paths before any model calls or writes.
        data_path = project_path(args.data)
        output_path = project_path(args.output) if args.output else None
        history_path = project_path(args.history) if args.history else None
        if output_path == data_path or (history_path and output_path == history_path):
            raise ValueError("输出路径不能覆盖输入资料或历史")
        if output_path and output_path.exists():
            raise ValueError("输出文件已存在，请选择新路径以保护已有文件")
        if args.fail_searches < 0 or args.fail_reads < 0:
            raise ValueError("故障注入次数不能为负数")
        history = json.loads(history_path.read_text(encoding="utf-8-sig")) if history_path else None
        from .retrieval import KnowledgeBase
        kb = KnowledgeBase(data_path, fail_searches=args.fail_searches, fail_reads=args.fail_reads)
        model = MockModel() if args.mode == "mock" else LiveModel()
        result = Agent(model, kb, max_steps=args.max_steps).run(args.question, history)
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("x", encoding="utf-8") as output:
                output.write(rendered + "\n")
        print(rendered)
        return 3 if result["status"] in {"incomplete", "tool_error"} else 0
    except (ValueError, OSError, ModelError) as exc:
        # Data errors may contain paths but model errors are already sanitized.
        print(json.dumps({"status": "input_error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
