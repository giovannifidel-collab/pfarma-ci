#!/usr/bin/env bash
set -euo pipefail

WRANGLER=(npx --yes wrangler@latest)
API="https://api.cloudflare.com/client/v4/zones"

# Known accounts from the authenticated Wrangler session.
ACCOUNTS=(
  "796dd8ead6f58d66e5213ea2abc882a9|Giovanni.fidel@gmail.com's Account"
  "6f6de52331e398c395d3de97c83011cd|project giovanni"
)

AUTH_JSON="$("${WRANGLER[@]}" auth token --json)"
TOKEN="$(printf '%s' "$AUTH_JSON" | node -e '
let s=""; process.stdin.on("data", d => s += d); process.stdin.on("end", () => {
  try { const j = JSON.parse(s); process.stdout.write(j.token || ""); }
  catch { process.exit(2); }
});
')"

if [[ -z "$TOKEN" ]]; then
  echo "CLOUDFLARE_AUTH_TOKEN_UNAVAILABLE" >&2
  exit 2
fi

echo "HIVE Cloudflare active-zone discovery"
echo "No authentication token will be printed."
echo

TOTAL=0
for entry in "${ACCOUNTS[@]}"; do
  ACCOUNT_ID="${entry%%|*}"
  ACCOUNT_NAME="${entry#*|}"
  TMP="$(mktemp)"

  HTTP_STATUS="$(curl -sS --get "$API" \
    -H "Authorization: Bearer $TOKEN" \
    --data-urlencode "account.id=$ACCOUNT_ID" \
    --data-urlencode "status=active" \
    --data-urlencode "per_page=50" \
    -o "$TMP" -w '%{http_code}')"

  echo "ACCOUNT: $ACCOUNT_NAME"
  echo "ACCOUNT_ID: $ACCOUNT_ID"

  if [[ "$HTTP_STATUS" != "200" ]]; then
    echo "STATUS: API_ERROR_$HTTP_STATUS"
    node - "$TMP" <<'NODE'
const fs = require('fs');
const p = process.argv[2];
try {
  const j = JSON.parse(fs.readFileSync(p, 'utf8'));
  for (const e of (j.errors || [])) console.log(`ERROR: ${e.code ?? ''} ${e.message ?? ''}`.trim());
} catch {}
NODE
    echo
    rm -f "$TMP"
    continue
  fi

  COUNT="$(node - "$TMP" <<'NODE'
const fs = require('fs');
const j = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const rows = Array.isArray(j.result) ? j.result : [];
process.stdout.write(String(rows.length));
NODE
)"

  echo "ACTIVE_ZONES: $COUNT"
  node - "$TMP" <<'NODE'
const fs = require('fs');
const j = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
for (const z of (j.result || [])) {
  console.log(`ZONE: ${z.name}`);
  console.log(`ZONE_ID: ${z.id}`);
  console.log(`ZONE_TYPE: ${z.type}`);
}
NODE

  TOTAL=$((TOTAL + COUNT))
  echo
  rm -f "$TMP"
done

echo "TOTAL_ACTIVE_ZONES: $TOTAL"
if [[ "$TOTAL" -eq 0 ]]; then
  echo "HIVE_CUSTOM_DOMAIN_STATUS: NO_ACTIVE_CLOUDFLARE_ZONE"
else
  echo "HIVE_CUSTOM_DOMAIN_STATUS: ACTIVE_ZONE_AVAILABLE"
fi
