"""Test helpers; all fixtures and subprocess files remain in the project."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class ScriptedModel:
    mode = "scripted_test"
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = []

    def decide(self, messages, tools):
        self.calls.append(copy.deepcopy(messages))
        if not self.actions:
            raise AssertionError("Unexpected model call")
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def action(name, **arguments):
    return {"action": name, "arguments": arguments, "reason": "黑盒测试的受控动作"}


def document(doc_id="T01", days=30):
    quote = f"报销申请须在费用发生后{days}天内提交。"
    return {
        "doc_id": doc_id, "version_date": "2026-01-01", "title": "报销期限制度",
        "topic": "expense_deadline", "content": quote,
        "facts": [{"key": "expense_deadline", "value": f"{days}天", "quote": quote}],
    }


def citation(doc=None):
    doc = doc or document()
    return {"doc_id": doc["doc_id"], "version_date": doc["version_date"], "quote": doc["content"]}


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fixture-", dir=ROOT / "tests")
        self.work = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def data_file(self, documents=None, name="knowledge.json"):
        path = self.work / name
        path.write_text(json.dumps({"documents": documents if documents is not None else [document()]}, ensure_ascii=False), encoding="utf-8")
        return path
