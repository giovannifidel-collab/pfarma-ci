from __future__ import annotations

import unittest
from pathlib import Path

from razzo.kernel.provider import ProviderState, load_provider_registry, select_online_zero_extra_cost_provider


ROOT = Path(__file__).resolve().parent


class ProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.providers = load_provider_registry(ROOT / "providers.json")

    def test_registry_reflects_selected_execution_architecture(self) -> None:
        by_id = {provider.provider_id: provider for provider in self.providers}
        self.assertIs(by_id["github-models"].state, ProviderState.RETIRED)
        self.assertIs(by_id["codex-github-mention"].state, ProviderState.UNAVAILABLE)
        self.assertIs(
            by_id["chatgpt-automation-github-connector"].state,
            ProviderState.AVAILABLE,
        )

    def test_exactly_one_provider_is_eligible(self) -> None:
        eligible = [provider for provider in self.providers if provider.eligible]
        self.assertEqual([provider.provider_id for provider in eligible], [
            "chatgpt-automation-github-connector"
        ])
        selected = select_online_zero_extra_cost_provider(self.providers)
        self.assertEqual(selected.provider_id, "chatgpt-automation-github-connector")
        self.assertTrue(selected.unattended_trigger)
        self.assertTrue(selected.can_write_code)

    def test_paid_and_external_paths_are_never_selected(self) -> None:
        by_id = {provider.provider_id: provider for provider in self.providers}
        self.assertTrue(by_id["openai-api-github-actions"].additional_cost_required)
        self.assertFalse(by_id["openai-api-github-actions"].eligible)
        self.assertFalse(by_id["codex-github-mention"].eligible)
        self.assertFalse(by_id["github-models"].eligible)


if __name__ == "__main__":
    unittest.main()
