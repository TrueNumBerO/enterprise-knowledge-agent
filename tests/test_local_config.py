"""Local credential loading without network calls or exposure of real secrets."""
import os
from unittest.mock import patch

from helpers import ProjectFixture, ROOT
from kb_agent.config import ConfigError, load_local_env
from kb_agent.models import LiveModel, MockModel, ModelError
from kb_agent.retrieval import KnowledgeBase
from kb_agent.runtime import Agent


class LocalConfigTests(ProjectFixture):
    def config_file(self, content="", name="fixture.env", encoding="utf-8"):
        path = self.work / name
        path.write_text(content, encoding=encoding)
        return path

    def test_default_file_is_project_local_and_accepts_bom_quotes_comments(self):
        content = '# comment\n\n KB_AGENT_API_KEY = "fixture-only-secret" \nKB_AGENT_MODEL=\'deepseek-flash\'\nKB_AGENT_TIMEOUT=60\n'
        self.config_file(content, name=".env", encoding="utf-8-sig")
        with patch("kb_agent.config.PROJECT_ROOT", self.work), patch.dict(os.environ, {"UNCHANGED": "yes"}, clear=True):
            before = dict(os.environ)
            result = load_local_env()
            self.assertEqual(result["KB_AGENT_API_KEY"], "fixture-only-secret")
            self.assertEqual(result["KB_AGENT_MODEL"], "deepseek-flash")
            self.assertEqual(result["KB_AGENT_TIMEOUT"], "60")
            self.assertEqual(dict(os.environ), before)

    def test_missing_default_is_optional_but_explicit_missing_file_is_an_error(self):
        with patch("kb_agent.config.PROJECT_ROOT", self.work):
            self.assertEqual(load_local_env(), {})
            with self.assertRaises(ConfigError):
                load_local_env(self.work / "missing.env")

    def test_configuration_does_not_interpolate_or_execute_value(self):
        literal = '${HOME}$(dangerous_command)`literal`'
        parsed = load_local_env(self.config_file('KB_AGENT_API_KEY="' + literal + '"\n'))
        self.assertEqual(parsed["KB_AGENT_API_KEY"], literal)

    def test_invalid_lines_never_echo_the_credential_content(self):
        secret = "fixture-only-sensitive-value"
        invalid = [secret, "UNKNOWN_KEY=" + secret, 'KB_AGENT_API_KEY="' + secret,
                   "KB_AGENT_API_KEY=" + secret + "\nKB_AGENT_API_KEY=" + secret,
                   "KB_AGENT_API_KEY=" + secret + "\x00"]
        for index, text in enumerate(invalid):
            with self.subTest(index=index):
                with self.assertRaises(ConfigError) as caught:
                    load_local_env(self.config_file(text))
                self.assertNotIn(secret, str(caught.exception))
                self.assertIn("行", str(caught.exception))

    def test_outside_project_configuration_path_is_rejected(self):
        with self.assertRaises(ConfigError):
            load_local_env(ROOT.parent / "outside.env")

    def test_oversized_and_invalid_utf8_files_fail_without_content(self):
        large = self.config_file("KB_AGENT_API_KEY=" + "x" * 17000)
        with self.assertRaises(ConfigError):
            load_local_env(large)
        invalid = self.work / "invalid.env"
        invalid.write_bytes(b"KB_AGENT_API_KEY=\xfffixture-only-secret")
        with self.assertRaises(ConfigError) as caught:
            load_local_env(invalid)
        self.assertNotIn("fixture-only-secret", str(caught.exception))

    def test_live_model_loads_file_fields_without_exporting_environment(self):
        path = self.config_file("KB_AGENT_API_KEY=fixture-key\nKB_AGENT_BASE_URL=https://api.deepseek.com\nKB_AGENT_MODEL=deepseek-flash\nKB_AGENT_TIMEOUT=60\n")
        with patch.dict(os.environ, {}, clear=True):
            model = LiveModel(config_file=path)
            self.assertEqual(model.api_key, "fixture-key")
            self.assertEqual(model.endpoint, "https://api.deepseek.com/chat/completions")
            self.assertEqual(model.model, "deepseek-flash")
            self.assertEqual(model.timeout, 60)
            self.assertEqual(dict(os.environ), {})
            self.assertNotIn("fixture-key", str(model.public_config()))

    def test_process_environment_overrides_file_and_explicit_arguments_override_both(self):
        path = self.config_file("KB_AGENT_API_KEY=file-key\nKB_AGENT_BASE_URL=https://file.example/v1\nKB_AGENT_MODEL=file-model\nKB_AGENT_TIMEOUT=50\n")
        env = {"DEEPSEEK_API_KEY": "environment-key", "KB_AGENT_BASE_URL": "https://environment.example/v1",
               "KB_AGENT_MODEL": "environment-model", "KB_AGENT_TIMEOUT": "40"}
        with patch.dict(os.environ, env, clear=True):
            model = LiveModel(config_file=path)
            self.assertEqual((model.api_key, model.base_url, model.model, model.timeout),
                             ("environment-key", "https://environment.example/v1", "environment-model", 40))
            explicit = LiveModel(api_key="explicit-key", base_url="https://explicit.example/v1", model="explicit-model", timeout=20, config_file=path)
            self.assertEqual((explicit.api_key, explicit.base_url, explicit.model, explicit.timeout),
                             ("explicit-key", "https://explicit.example/v1", "explicit-model", 20))

    def test_key_aliases_have_documented_order_within_each_source(self):
        path = self.config_file("DASHSCOPE_API_KEY=dashscope-fixture\nDEEPSEEK_API_KEY=deepseek-fixture\n")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(LiveModel(config_file=path).api_key, "deepseek-fixture")
        with patch.dict(os.environ, {"KB_AGENT_API_KEY": "generic-fixture", "DEEPSEEK_API_KEY": "deepseek-env"}, clear=True):
            self.assertEqual(LiveModel(config_file=path).api_key, "generic-fixture")

    def test_explicit_empty_environment_key_blocks_file_fallback(self):
        path = self.config_file("KB_AGENT_API_KEY=never-use-this-fixture\n")
        with patch.dict(os.environ, {"KB_AGENT_API_KEY": ""}, clear=True):
            with self.assertRaises(ModelError) as caught:
                LiveModel(config_file=path)
            self.assertNotIn("never-use-this-fixture", str(caught.exception))

    def test_live_model_wraps_file_errors_without_echoing_secret(self):
        path = self.config_file("UNKNOWN=fixture-only-secret\n")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ModelError) as caught:
                LiveModel(config_file=path)
            self.assertNotIn("fixture-only-secret", str(caught.exception))

    def test_mock_does_not_read_local_credentials(self):
        with patch("kb_agent.models.load_local_env", side_effect=AssertionError("Mock must not load credentials")):
            result = Agent(MockModel(), KnowledgeBase(self.data_file())).run("报销期限多久？")
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["model_mode"], "mock")
