from __future__ import annotations

import unittest
from pathlib import Path

from razzo.kernel.provider import ProviderState, load_provider_registry, select_online_zero_extra_cost_provider


ROOT = Path(__file__).resolve().parent


class ProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.providers = load_provider_registry(ROOT / "providers.json")

    def test_registry_reflects_verified_retirement_and_probe(self) -> None:
        by_id = {provider.provider_id: provider for provider in self.providers}
        self.assertIs(by_id["github-models"].state, ProviderState.RETIRED)
        self.assertIs(by_id["codex-github-mention"].state, ProviderState.PENDING_PROBE)

    def test_no_provider_is_eligible_before_real_probe(self) -> None:
        self.assertFalse(any(provider.eligible for provider in self.providers))
        with self.assertRaisesRegex(RuntimeError, "found 0"):
            select_online_zero_extra_cost_provider(self.providers)

    def test_paid_and_scheduled_paths_are_never_selected(self) -> None:
        by_id = {provider.provider_id: provider for provider in self.providers}
        self.assertTrue(by_id["openai-api-github-actions"].additional_cost_required)
        self.assertFalse(by_id["chatgpt-automation-github-connector"].eligible)


if __name__ == "__main__":
    unittest.main()
