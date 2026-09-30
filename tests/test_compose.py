"""Static safety checks for the production Compose topology."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


class DockerignoreTests(unittest.TestCase):
    def test_nested_caches_and_runtime_data_are_excluded(self) -> None:
        # In .dockerignore a bare "*.pyc" or "data/" matches only at the
        # context root; "**/" is what keeps chathelper/__pycache__ and
        # a stray chathelper/data/ out of the image.
        lines = {
            line.strip()
            for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        for required in ("**/__pycache__", "**/*.pyc", "**/data/", "**/*.db", ".env", "secrets/"):
            self.assertIn(required, lines)
        self.assertIn("!README.md", lines)  # the Dockerfile copies it


class ComposeSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

    def test_only_reverse_proxy_publishes_ports(self) -> None:
        services = self.document["services"]
        self.assertEqual(
            set(services), {"caddy", "app", "postgres", "db-init", "qdrant", "llm", "embed"}
        )
        for name, service in services.items():
            self.assertEqual("ports" in service, name == "caddy", name)

    def test_data_services_have_separate_persistent_volumes(self) -> None:
        services = self.document["services"]
        self.assertIn("postgres_data:/var/lib/postgresql/data", services["postgres"]["volumes"])
        self.assertIn("qdrant_data:/qdrant/storage", services["qdrant"]["volumes"])
        self.assertTrue(self.document["networks"]["backend"]["internal"])

    def test_secrets_are_mounted_as_files(self) -> None:
        services = self.document["services"]
        self.assertIn("postgres_password", services["postgres"]["secrets"])
        self.assertIn("postgres_password", services["db-init"]["secrets"])
        self.assertIn("app_db_password", services["db-init"]["secrets"])
        self.assertIn("app_db_password", services["app"]["secrets"])
        self.assertNotIn("postgres_password", services["app"]["secrets"])
        self.assertIn("qa_token", services["app"]["secrets"])
        self.assertIn("llm_api_key", services["app"]["secrets"])
        self.assertEqual(
            services["app"]["environment"]["LLM_API_KEY_FILE"], "/run/secrets/llm_api_key"
        )
        self.assertEqual(
            set(self.document["secrets"]),
            {"postgres_password", "app_db_password", "qa_token", "llm_api_key"},
        )
        self.assertEqual(services["app"]["environment"]["POSTGRES_USER"], "chathelper_app")
        self.assertEqual(services["postgres"]["environment"]["POSTGRES_USER"], "postgres")
        self.assertEqual(
            services["app"]["depends_on"]["db-init"]["condition"],
            "service_completed_successfully",
        )

    def test_local_model_servers_are_optional_profiles(self) -> None:
        # Production chat uses a hosted API; the llama.cpp containers must not
        # be required, and only the GPU chat profile may reserve a GPU.
        services = self.document["services"]
        self.assertEqual(services["llm"]["profiles"], ["local-llm"])
        self.assertEqual(services["embed"]["profiles"], ["local-embed"])
        self.assertNotIn("llm", services["app"]["depends_on"])
        self.assertNotIn("embed", services["app"]["depends_on"])
        for name, service in services.items():
            has_gpu = "devices" in service.get("deploy", {}).get("resources", {}).get("reservations", {})
            self.assertEqual(has_gpu, name == "llm", name)


if __name__ == "__main__":
    unittest.main()
