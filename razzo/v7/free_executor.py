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

    if "error recovery" in objective or "error recovery screen" in objective:
        path = app / "error.tsx"
        if not path.exists():
            path.write_text(
                """\"use client\";\n\nimport { useEffect } from \"react\";\n\nexport default function GlobalError({\n  error,\n  reset\n}: {\n  error: Error & { digest?: string };\n  reset: () => void;\n}) {\n  useEffect(() => {\n    console.error(\"Project Giovanni route error\", error);\n  }, [error]);\n\n  return (\n    <main className=\"shell\" aria-labelledby=\"global-error-title\">\n      <section role=\"alert\">\n        <p className=\"eyebrow\">ERRORE TEMPORANEO</p>\n        <h1 id=\"global-error-title\">Questa schermata non si è caricata correttamente.</h1>\n        <p>I tuoi dati non sono stati modificati. Puoi riprovare senza uscire dalla sessione.</p>\n        <button type=\"button\" onClick={reset}>Riprova</button>\n      </section>\n    </main>\n  );\n}\n""",
                encoding="utf-8",
            )
            changed.append("app/error.tsx")

    if "loading feedback" in objective or "route transitions" in objective:
        path = app / "loading.tsx"
        if not path.exists():
            path.write_text(
                """export default function GlobalLoading() {\n  return (\n    <main className=\"shell\" aria-busy=\"true\" aria-live=\"polite\">\n      <section role=\"status\" aria-label=\"Caricamento in corso\">\n        <p className=\"eyebrow\">PROJECT GIOVANNI</p>\n        <h1>Sto preparando la schermata…</h1>\n        <p>Attendi qualche istante.</p>\n      </section>\n    </main>\n  );\n}\n""",
                encoding="utf-8",
            )
            changed.append("app/loading.tsx")
    return sorted(set(changed))


def execute_family_cloud(contract: dict[str, Any], root: Path) -> list[str]:
    objective = str(contract.get("product_objective", "")).lower()
    changed: list[str] = []
    web = root / "web"
    web.mkdir(parents=True, exist_ok=True)
    index = web / "index.html"
    text = index.read_text(encoding="utf-8")

    if "installable" in objective or "offline" in objective or "application-shell" in objective:
        manifest = web / "manifest.webmanifest"
        manifest.write_text(json.dumps({
            "name": "Family Cloud Local Alpha",
            "short_name": "Family Cloud",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#ffffff",
            "icons": []
        }, indent=2) + "\n", encoding="utf-8")
        sw = web / "sw.js"
        sw.write_text("""const CACHE = 'family-cloud-shell-v1';
const SHELL = ['/', '/index.html', '/app.js', '/styles.css', '/manifest.webmanifest'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL))));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request).then(hit => hit || (event.request.mode === 'navigate' ? caches.match('/index.html') : Response.error()))));
});
""", encoding="utf-8")
        text = ensure_before(text, "</head>", '  <link rel="manifest" href="/manifest.webmanifest">')
        text = ensure_before(text, "</body>", """  <script>
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));
    }
  </script>""")
        changed += ["web/manifest.webmanifest", "web/sw.js"]

    if "vault identity" in objective or "demo vault" in objective:
        vault = web / "vault-identity.js"
        vault.write_text("""(() => {
  const KEY = 'family-cloud.demo-vault-id';
  const VALID = /^fcv_[a-z0-9]{16,64}$/;
  let value = localStorage.getItem(KEY) || '';
  if (!VALID.test(value)) {
    const bytes = new Uint8Array(12);
    crypto.getRandomValues(bytes);
    value = 'fcv_' + Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    localStorage.setItem(KEY, value);
  }
  document.documentElement.dataset.vaultId = value;
  window.familyCloudVaultId = value;
})();
""", encoding="utf-8")
        text = ensure_before(text, "</body>", '  <script src="/vault-identity.js"></script>')
        changed.append("web/vault-identity.js")

    if text != index.read_text(encoding="utf-8"):
        index.write_text(text, encoding="utf-8")
        changed.append("web/index.html")
    return sorted(set(changed))


def execute(contract: dict[str, Any], root: Path) -> dict[str, Any]:
    if contract.get("actionability_state") != "READY":
        return {"state": "UNSUPPORTED", "reason": "contract_not_ready", "changed_files": []}
    project_id = str(contract.get("project_id", ""))
    if project_id == "project-giovanni":
        changed = execute_project_giovanni(contract, root)
    elif project_id == "family-cloud":
        changed = execute_family_cloud(contract, root)
    else:
        return {"state": "UNSUPPORTED", "reason": "no_deterministic_recipe", "changed_files": []}
    if not changed:
        return {"state": "NO_CHANGE", "reason": "recipe_already_satisfied", "changed_files": []}
    return {"state": "CHANGED", "reason": "deterministic_recipe_applied", "changed_files": changed}


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
