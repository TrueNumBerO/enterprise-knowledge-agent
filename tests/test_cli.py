"""CLI checks execute the public entry point in a clean subprocess."""
import json
import os
import subprocess
import sys

from helpers import ProjectFixture, ROOT


class CliTests(ProjectFixture):
    def cli(self, *args, env_override=None):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        if env_override:
            env.update(env_override)
        return subprocess.run([sys.executable, "-B", "-m", "kb_agent", *args], cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True, timeout=30)

    def test_cli_mock_output_is_usable_json(self):
        path = self.work / "result.json"
        completed = self.cli("--question", "报销期限多久？", "--data", str(self.data_file()), "--mode", "mock", "--output", str(path))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual(data["status"], "answered")
        self.assertEqual(data["model_mode"], "mock")
        self.assertTrue(data["trace"])

    def test_cli_rejects_output_outside_project(self):
        completed = self.cli("--question", "测试", "--output", str(ROOT.parent / "forbidden-test-output.json"))
        self.assertEqual(completed.returncode, 2)
        self.assertFalse((ROOT.parent / "forbidden-test-output.json").exists())

    def test_cli_rejects_external_history(self):
        completed = self.cli("--question", "然后呢？", "--history", str(ROOT.parent / "outside.json"))
        self.assertEqual(completed.returncode, 2)

    def test_cli_live_requires_credentials_without_leaking_secrets(self):
        completed = self.cli("--question", "报销期限多久？", "--mode", "live", env_override={"KB_AGENT_API_KEY": "", "DASHSCOPE_API_KEY": "", "OPENAI_API_KEY": ""})
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("Traceback", completed.stderr)

    def test_cli_step_limit_returns_nonzero_incomplete(self):
        path = self.work / "limited.json"
        completed = self.cli("--question", "报销期限多久？", "--data", str(self.data_file()), "--max-steps", "1", "--output", str(path))
        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8-sig"))["status"], "incomplete")

    def test_cli_invalid_history_has_controlled_error(self):
        path = self.work / "history.json"
        path.write_text("{broken", encoding="utf-8")
        completed = self.cli("--question", "然后呢？", "--history", str(path))
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("Traceback", completed.stderr)

    def test_cli_non_string_history_role_has_controlled_error(self):
        path = self.work / "history-with-invalid-role.json"
        path.write_text(json.dumps([{"role": ["user"], "content": "test"}]), encoding="utf-8")
        completed = self.cli("--question", "然后呢？", "--history", str(path))
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual(json.loads(completed.stderr)["status"], "input_error")

