"""The evaluation utility must preserve the same project write boundary."""
import importlib.util
import json
import os
import subprocess
import sys

from helpers import ProjectFixture, ROOT


class EvaluationUtilityTests(ProjectFixture):
    def evaluate(self, *args, **overrides):
        env = os.environ.copy()
        env.update({"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
        env.update(overrides)
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/evaluate.py"), *args], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_case_identifier_cannot_escape_output_directory(self):
        path = self.work / "cases.json"
        path.write_text(json.dumps([{"id": "../../../forbidden-test-output", "question": "报销期限"}]), encoding="utf-8")
        completed = self.evaluate("--cases", str(path))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("error", json.loads(completed.stderr))
        self.assertNotIn("Traceback", completed.stderr)
        self.assertFalse((ROOT.parent / "forbidden-test-output.json").exists())

    def test_live_evaluation_without_credentials_returns_controlled_error(self):
        completed = self.evaluate("--mode", "live", KB_AGENT_API_KEY="", DASHSCOPE_API_KEY="")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("error", json.loads(completed.stderr))
        self.assertNotIn("Traceback", completed.stderr)

    def test_writer_rejects_external_destination(self):
        spec = importlib.util.spec_from_file_location("evaluation_under_test", ROOT / "scripts/evaluate.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(ValueError):
            module.write_json(ROOT.parent / "forbidden-test-output.json", {})

    def test_check_config_exposes_safe_metadata_without_network_or_results(self):
        import contextlib
        import io
        from unittest.mock import patch
        from kb_agent.models import LiveModel

        spec = importlib.util.spec_from_file_location("evaluation_config_check", ROOT / "scripts/evaluate.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        settings = {"KB_AGENT_API_KEY": "fixture-only-secret", "KB_AGENT_BASE_URL": "https://api.deepseek.com",
                    "KB_AGENT_MODEL": "deepseek-flash", "KB_AGENT_TIMEOUT": "60"}
        with patch.dict(os.environ, settings, clear=True), \
             patch.object(sys, "argv", ["evaluate.py", "--mode", "live", "--check-config", "--cases", "does-not-exist.json"]), \
             patch.object(LiveModel, "_request", side_effect=AssertionError("Must not call network")) as request, \
             patch.object(module, "write_json", side_effect=AssertionError("Must not write evaluation files")) as writer, \
             contextlib.redirect_stdout(output):
            self.assertEqual(module.main(), 0)
        metadata = json.loads(output.getvalue())
        self.assertTrue(metadata["configured"])
        self.assertFalse(metadata["network_called"])
        self.assertEqual(metadata["model_config"]["model"], "deepseek-flash")
        self.assertEqual(metadata["model_config"]["thinking"], "disabled")
        self.assertNotIn("fixture-only-secret", output.getvalue())
        request.assert_not_called()
        writer.assert_not_called()

    def test_check_config_requires_live_mode(self):
        result = self.evaluate("--check-config")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
