from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ensure_before(text: str, marker: str, insertion: str) -> str:
    if insertion.strip() in text:
        return text
    if marker not in text:
        raise ValueError(f"required marker not found: {marker}")
    return text.replace(marker, insertion + "\n" + marker, 1)


def execute_project_giovanni(contract: dict[str, Any], root: Path) -> list[str]:
    objective = str(contract.get("product_objective", "")).lower()
    app = root / "app"
    if not app.is_dir() or not (root / "package.json").exists():
        raise ValueError("Project Giovanni App Router structure not found")
    changed: list[str] = []
    if "error recovery" in objective:
        path = app / "error.tsx"
        if not path.exists():
            path.write_text('''"use client";\n\nimport { useEffect } from "react";\n\nexport default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void; }) {\n  useEffect(() => { console.error("Project Giovanni route error", error); }, [error]);\n  return (\n    <main className="shell" aria-labelledby="global-error-title">\n      <section role="alert">\n        <p className="eyebrow">ERRORE TEMPORANEO</p>\n        <h1 id="global-error-title">Questa schermata non si è caricata correttamente.</h1>\n        <p>I tuoi dati non sono stati modificati. Puoi riprovare senza uscire dalla sessione.</p>\n        <button type="button" onClick={reset}>Riprova</button>\n      </section>\n    </main>\n  );\n}\n''', encoding="utf-8")
            changed.append("app/error.tsx")
    if "loading feedback" in objective or "route transitions" in objective:
        path = app / "loading.tsx"
        if not path.exists():
            path.write_text('''export default function GlobalLoading() {\n  return (\n    <main className="shell" aria-busy="true" aria-live="polite">\n      <section role="status" aria-label="Caricamento in corso">\n        <p className="eyebrow">PROJECT GIOVANNI</p>\n        <h1>Sto preparando la schermata…</h1>\n        <p>Attendi qualche istante.</p>\n      </section>\n    </main>\n  );\n}\n''', encoding="utf-8")
            changed.append("app/loading.tsx")
    return sorted(set(changed))


def execute_pfarma_cloud(contract: dict[str, Any], root: Path) -> list[str]:
    objective = str(contract.get("product_objective", "")).lower()
    api = root / "api"
    tests = root / "tests"
    if not api.is_dir() or not tests.is_dir():
        raise ValueError("PFarma api/tests structure not found")
    changed: list[str] = []
    if "stock threshold preview" in objective:
        module = api / "stock_threshold_preview.py"
        test = tests / "test_stock_threshold_preview.py"
        if not module.exists():
            module.write_text('''from __future__ import annotations\n\nfrom dataclasses import dataclass\n\n\n@dataclass(frozen=True)\nclass StockThresholdPreview:\n    state: str\n    available: int\n    minimum: int\n    target: int\n    shortage: int\n    suggested_replenishment: int\n    production_write: bool = False\n    purchase_order_write: bool = False\n\n\ndef _quantity(value: object, label: str) -> int:\n    if isinstance(value, bool):\n        raise ValueError(f"{label} must be a non-negative integer")\n    try:\n        parsed = int(value)\n    except (TypeError, ValueError) as exc:\n        raise ValueError(f"{label} must be a non-negative integer") from exc\n    if parsed < 0 or parsed != value:\n        raise ValueError(f"{label} must be a non-negative integer")\n    return parsed\n\n\ndef preview_stock_threshold(*, available: object, minimum: object, target: object) -> StockThresholdPreview:\n    current = _quantity(available, "available")\n    floor = _quantity(minimum, "minimum")\n    desired = _quantity(target, "target")\n    if desired < floor:\n        raise ValueError("target must be greater than or equal to minimum")\n    state = "urgent" if current == 0 else "low" if current < floor else "healthy"\n    shortage = max(floor - current, 0)\n    suggested = max(desired - current, 0)\n    return StockThresholdPreview(state, current, floor, desired, shortage, suggested)\n''', encoding="utf-8")
            test.write_text('''import unittest\n\nfrom api.stock_threshold_preview import preview_stock_threshold\n\n\nclass StockThresholdPreviewTests(unittest.TestCase):\n    def test_classifies_and_suggests_without_writes(self):\n        preview = preview_stock_threshold(available=2, minimum=5, target=12)\n        self.assertEqual(preview.state, "low")\n        self.assertEqual(preview.shortage, 3)\n        self.assertEqual(preview.suggested_replenishment, 10)\n        self.assertFalse(preview.production_write)\n        self.assertFalse(preview.purchase_order_write)\n\n    def test_zero_is_urgent_and_invalid_target_is_rejected(self):\n        self.assertEqual(preview_stock_threshold(available=0, minimum=1, target=4).state, "urgent")\n        with self.assertRaises(ValueError):\n            preview_stock_threshold(available=1, minimum=5, target=4)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding="utf-8")
            changed += ["api/stock_threshold_preview.py", "tests/test_stock_threshold_preview.py"]
    if "warehouse transfer preview" in objective or "interwarehouse transfer" in objective:
        module = api / "interwarehouse_transfer_preview.py"
        test = tests / "test_interwarehouse_transfer_preview.py"
        if not module.exists():
            module.write_text('''from __future__ import annotations\n\nfrom dataclasses import dataclass\n\n_ALLOWED = {"E", "A"}\n\n\n@dataclass(frozen=True)\nclass InterwarehouseTransferPreview:\n    source: str\n    destination: str\n    quantity: int\n    source_after: int\n    destination_after: int\n    production_write: bool = False\n\n\ndef _quantity(value: object, label: str) -> int:\n    if isinstance(value, bool):\n        raise ValueError(f"{label} must be a non-negative integer")\n    try:\n        parsed = int(value)\n    except (TypeError, ValueError) as exc:\n        raise ValueError(f"{label} must be a non-negative integer") from exc\n    if parsed < 0 or parsed != value:\n        raise ValueError(f"{label} must be a non-negative integer")\n    return parsed\n\n\ndef preview_interwarehouse_transfer(*, source: str, destination: str, quantity: object, source_available: object, destination_available: object) -> InterwarehouseTransferPreview:\n    src = source.strip().upper()\n    dst = destination.strip().upper()\n    if src not in _ALLOWED or dst not in _ALLOWED or src == dst:\n        raise ValueError("source and destination must be different E/A warehouses")\n    moved = _quantity(quantity, "quantity")\n    src_available = _quantity(source_available, "source_available")\n    dst_available = _quantity(destination_available, "destination_available")\n    if moved > src_available:\n        raise ValueError("insufficient source stock")\n    return InterwarehouseTransferPreview(src, dst, moved, src_available - moved, dst_available + moved)\n''', encoding="utf-8")
            test.write_text('''import unittest\n\nfrom api.interwarehouse_transfer_preview import preview_interwarehouse_transfer\n\n\nclass InterwarehouseTransferPreviewTests(unittest.TestCase):\n    def test_previews_balances_without_writing(self):\n        preview = preview_interwarehouse_transfer(source="E", destination="A", quantity=3, source_available=10, destination_available=4)\n        self.assertEqual((preview.source_after, preview.destination_after), (7, 7))\n        self.assertFalse(preview.production_write)\n\n    def test_rejects_same_warehouse_and_insufficient_stock(self):\n        with self.assertRaises(ValueError):\n            preview_interwarehouse_transfer(source="E", destination="E", quantity=1, source_available=2, destination_available=0)\n        with self.assertRaises(ValueError):\n            preview_interwarehouse_transfer(source="A", destination="E", quantity=5, source_available=4, destination_available=1)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding="utf-8")
            changed += ["api/interwarehouse_transfer_preview.py", "tests/test_interwarehouse_transfer_preview.py"]
    return sorted(set(changed))


def execute_family_cloud(contract: dict[str, Any], root: Path) -> list[str]:
    objective = str(contract.get("product_objective", "")).lower()
    changed: list[str] = []
    web = root / "web"
    web.mkdir(parents=True, exist_ok=True)
    index = web / "index.html"
    text = index.read_text(encoding="utf-8")
    original = text
    if "installable" in objective or "offline" in objective or "application-shell" in objective:
        (web / "manifest.webmanifest").write_text(json.dumps({"name":"Family Cloud Local Alpha","short_name":"Family Cloud","start_url":"/","display":"standalone","background_color":"#ffffff","theme_color":"#ffffff","icons":[]}, indent=2) + "\n", encoding="utf-8")
        (web / "sw.js").write_text("const CACHE='family-cloud-shell-v1';\nconst SHELL=['/','/index.html','/app.js','/styles.css','/manifest.webmanifest'];\nself.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL))));\nself.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))));\nself.addEventListener('fetch',e=>{if(e.request.method!=='GET'||new URL(e.request.url).origin!==self.location.origin)return;e.respondWith(fetch(e.request).catch(()=>caches.match(e.request).then(hit=>hit||(e.request.mode==='navigate'?caches.match('/index.html'):Response.error()))));});\n", encoding="utf-8")
        text = ensure_before(text, "</head>", '  <link rel="manifest" href="/manifest.webmanifest">')
        text = ensure_before(text, "</body>", "  <script>if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));</script>")
        changed += ["web/manifest.webmanifest", "web/sw.js"]
    if "vault identity" in objective or "demo vault" in objective:
        (web / "vault-identity.js").write_text("(()=>{const KEY='family-cloud.demo-vault-id';const VALID=/^fcv_[a-z0-9]{16,64}$/;let value=localStorage.getItem(KEY)||'';if(!VALID.test(value)){const bytes=new Uint8Array(12);crypto.getRandomValues(bytes);value='fcv_'+Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');localStorage.setItem(KEY,value);}document.documentElement.dataset.vaultId=value;window.familyCloudVaultId=value;})();\n", encoding="utf-8")
        text = ensure_before(text, "</body>", '  <script src="/vault-identity.js"></script>')
        changed.append("web/vault-identity.js")
    if text != original:
        index.write_text(text, encoding="utf-8")
        changed.append("web/index.html")
    return sorted(set(changed))


def execute(contract: dict[str, Any], root: Path) -> dict[str, Any]:
    if contract.get("actionability_state") != "READY":
        return {"state":"UNSUPPORTED","reason":"contract_not_ready","changed_files":[]}
    project_id = str(contract.get("project_id", ""))
    if project_id == "project-giovanni":
        changed = execute_project_giovanni(contract, root)
    elif project_id == "pfarma-cloud":
        changed = execute_pfarma_cloud(contract, root)
    elif project_id == "family-cloud":
        changed = execute_family_cloud(contract, root)
    else:
        return {"state":"UNSUPPORTED","reason":"no_deterministic_recipe","changed_files":[]}
    if not changed:
        return {"state":"NO_CHANGE","reason":"recipe_already_satisfied","changed_files":[]}
    return {"state":"CHANGED","reason":"deterministic_recipe_applied","changed_files":changed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--product-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = execute(json.loads(args.contract_json), Path(args.product_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["state"] in {"CHANGED", "NO_CHANGE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
