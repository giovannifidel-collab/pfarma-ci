from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from razzo.kernel.portfolio import load_portfolio


class PortfolioTests(unittest.TestCase):
    def write(self, payload: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name, "projects.json")
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_enabled_projects_are_discovered_only_from_registry(self) -> None:
        path = self.write({"projects": [
            {"id": "alpha", "repository": "org/alpha", "enabled": True},
            {"id": "beta", "repository": "org/beta", "enabled": False},
            {"id": "gamma", "repository": "org/gamma", "enabled": True},
        ]})
        snapshot = load_portfolio(path)
        self.assertEqual(
            [project.project_id for project in snapshot.require_enabled()],
            ["alpha", "gamma"],
        )
        self.assertEqual(len(snapshot.source_digest), 64)

    def test_registry_changes_are_visible_on_next_load(self) -> None:
        path = self.write({"projects": [{"id": "alpha", "repository": "org/alpha", "enabled": True}]})
        first = load_portfolio(path)
        path.write_text(json.dumps({"projects": [
            {"id": "alpha", "repository": "org/alpha", "enabled": False},
            {"id": "delta", "repository": "org/delta", "enabled": True},
        ]}), encoding="utf-8")
        second = load_portfolio(path)
        self.assertNotEqual(first.source_digest, second.source_digest)
        self.assertEqual([project.project_id for project in second.require_enabled()], ["delta"])

    def test_empty_enabled_portfolio_fails_closed(self) -> None:
        path = self.write({"projects": [{"id": "off", "repository": "org/off", "enabled": False}]})
        with self.assertRaisesRegex(ValueError, "no enabled projects"):
            load_portfolio(path).require_enabled()

    def test_duplicate_ids_and_repositories_are_rejected(self) -> None:
        duplicate_id = self.write({"projects": [
            {"id": "same", "repository": "org/one"},
            {"id": "same", "repository": "org/two"},
        ]})
        with self.assertRaisesRegex(ValueError, "duplicate project id"):
            load_portfolio(duplicate_id)

        duplicate_repo = self.write({"projects": [
            {"id": "one", "repository": "org/same"},
            {"id": "two", "repository": "org/same"},
        ]})
        with self.assertRaisesRegex(ValueError, "duplicate project repository"):
            load_portfolio(duplicate_repo)


if __name__ == "__main__":
    unittest.main()
