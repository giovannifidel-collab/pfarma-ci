from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ProviderState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PENDING_PROBE = "PENDING_PROBE"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class ExecutionProvider:
    provider_id: str
    state: ProviderState
    online_only: bool
    additional_cost_required: bool
    unattended_trigger: bool
    can_write_code: bool
    evidence: tuple[str, ...]

    @property
    def eligible(self) -> bool:
        return bool(
            self.state is ProviderState.AVAILABLE
            and self.online_only
            and not self.additional_cost_required
            and self.unattended_trigger
            and self.can_write_code
            and self.evidence
        )


def load_provider_registry(path: str | Path) -> tuple[ExecutionProvider, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != "razzo-online-provider-v1":
        raise ValueError("unsupported provider registry schema")
    providers: list[ExecutionProvider] = []
    seen: set[str] = set()
    for item in payload.get("providers", []):
        provider_id = str(item.get("id", "")).strip()
        if not provider_id or provider_id in seen:
            raise ValueError("provider ids must be non-empty and unique")
        seen.add(provider_id)
        evidence = tuple(str(value).strip() for value in item.get("evidence", []) if str(value).strip())
        providers.append(
            ExecutionProvider(
                provider_id=provider_id,
                state=ProviderState(str(item["state"])),
                online_only=bool(item["online_only"]),
                additional_cost_required=bool(item["additional_cost_required"]),
                unattended_trigger=bool(item["unattended_trigger"]),
                can_write_code=bool(item["can_write_code"]),
                evidence=evidence,
            )
        )
    if not providers:
        raise ValueError("provider registry must contain at least one provider")
    return tuple(providers)


def select_online_zero_extra_cost_provider(providers: tuple[ExecutionProvider, ...]) -> ExecutionProvider:
    eligible = [provider for provider in providers if provider.eligible]
    if len(eligible) != 1:
        raise RuntimeError(f"expected exactly one eligible provider, found {len(eligible)}")
    return eligible[0]
