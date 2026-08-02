from __future__ import annotations

import argparse
import json
from pathlib import Path

MODULE = '''from __future__ import annotations

from dataclasses import dataclass

_ALLOWED = {"E", "A"}


@dataclass(frozen=True)
class InterwarehouseTransferPreview:
    source: str
    destination: str
    quantity: int
    source_after: int
    destination_after: int
    production_write: bool = False


def _quantity(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a non-negative integer") from exc
    if parsed < 0 or parsed != value:
        raise ValueError(f"{label} must be a non-negative integer")
    return parsed


def preview_interwarehouse_transfer(*, source: str, destination: str, quantity: object, source_available: object, destination_available: object) -> InterwarehouseTransferPreview:
    src = source.strip().upper()
    dst = destination.strip().upper()
    if src not in _ALLOWED or dst not in _ALLOWED or src == dst:
        raise ValueError("source and destination must be different E/A warehouses")
    moved = _quantity(quantity, "quantity")
    src_available = _quantity(source_available, "source_available")
    dst_available = _quantity(destination_available, "destination_available")
    if moved > src_available:
        raise ValueError("insufficient source stock")
    return InterwarehouseTransferPreview(src, dst, moved, src_available - moved, dst_available + moved)
'''

TEST = '''import unittest

from api.interwarehouse_transfer_preview import preview_interwarehouse_transfer


class InterwarehouseTransferPreviewTests(unittest.TestCase):
    def test_previews_balances_without_writing(self):
        preview = preview_interwarehouse_transfer(source="E", destination="A", quantity=3, source_available=10, destination_available=4)
        self.assertEqual((preview.source_after, preview.destination_after), (7, 7))
        self.assertFalse(preview.production_write)

    def test_rejects_invalid_warehouse_and_insufficient_stock(self):
        for kwargs in (
            dict(source="E", destination="E", quantity=1, source_available=2, destination_available=0),
            dict(source="X", destination="E", quantity=1, source_available=2, destination_available=0),
            dict(source="A", destination="E", quantity=5, source_available=4, destination_available=1),
            dict(source="A", destination="E", quantity=-1, source_available=4, destination_available=1),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                preview_interwarehouse_transfer(**kwargs)


if __name__ == "__main__":
    unittest.main()
'''


def load_artifacts(root: Path) -> dict[str, dict]:
    artifacts: dict[str, dict] = {}
    keys: set[str] = set()
    for path in sorted(root.rglob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        key = item["idempotency_key"]
        if key in keys:
            raise ValueError(f"duplicate shred artifact {key}")
        keys.add(key)
        artifacts[item["artifact"]] = item
    required = {"contract", "logic", "safety", "happy_tests", "error_tests", "integrate"}
    missing = required - set(artifacts)
    if missing:
        raise ValueError(f"missing shred artifacts: {sorted(missing)}")
    return artifacts


def assemble(artifacts_root: Path, product_root: Path) -> list[str]:
    load_artifacts(artifacts_root)
    module = product_root / "api" / "interwarehouse_transfer_preview.py"
    test = product_root / "tests" / "test_interwarehouse_transfer_preview.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    test.parent.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    if not module.exists() or module.read_text(encoding="utf-8") != MODULE:
        module.write_text(MODULE, encoding="utf-8")
        changed.append("api/interwarehouse_transfer_preview.py")
    if not test.exists() or test.read_text(encoding="utf-8") != TEST:
        test.write_text(TEST, encoding="utf-8")
        changed.append("tests/test_interwarehouse_transfer_preview.py")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--product-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    changed = assemble(Path(args.artifacts_root), Path(args.product_root))
    result = {"schema": "razzo-shred-assembly-v1", "changed_files": changed, "single_publish": True}
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
