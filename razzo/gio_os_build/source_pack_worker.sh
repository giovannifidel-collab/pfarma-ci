#!/usr/bin/env bash
set -euo pipefail

: "${PACK_ID:?PACK_ID required}"
: "${PACK_COUNT:=16}"
: "${SOURCEPACK_GENERATION:=v1-20260902}"
[[ "$PACK_ID" =~ ^([0-9]|1[0-5])$ ]] || { echo "invalid PACK_ID" >&2; exit 2; }
[[ "$PACK_COUNT" = 16 ]] || { echo "unexpected PACK_COUNT" >&2; exit 2; }

TAG="gio-a14-lavender-srcpack-${SOURCEPACK_GENERATION}-pack$(printf '%02d' "$PACK_ID")"
ROOT="$RUNNER_TEMP/gio-a14-pack-$PACK_ID"
OUT="$RUNNER_TEMP/sourcepack-output"
mkdir -p "$ROOT" "$OUT" "$HOME/bin"

sudo rm -rf /usr/local/lib/android /usr/share/dotnet /opt/ghc /usr/local/.ghcup /opt/hostedtoolcache/CodeQL || true
sudo docker image prune -af >/dev/null 2>&1 || true
sudo rm -rf /var/lib/apt/lists/* || true
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git git-lfs squashfs-tools python3 curl
curl -fsSL https://storage.googleapis.com/git-repo-downloads/repo -o "$HOME/bin/repo"
chmod 0755 "$HOME/bin/repo"
export PATH="$HOME/bin:$PATH"
git lfs install --skip-repo

cd "$ROOT"
repo init -u https://github.com/crdroidandroid/android.git -b 14.0 \
  --git-lfs --no-clone-bundle --depth=1 --partial-clone --clone-filter=blob:limit=10M
mkdir -p .repo/local_manifests
cat > .repo/local_manifests/gio-lavender-public.xml <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <remote name="crdroid-gio" fetch="https://github.com/crdroidandroid" />
  <project path="device/xiaomi/lavender" name="android_device_xiaomi_lavender" remote="crdroid-gio" revision="fd2a90e734a101fad046736970fa4dfb492d7d78" />
  <project path="kernel/xiaomi/lavender" name="android_kernel_xiaomi_lavender" remote="crdroid-gio" revision="b7b27af5994f7afc11f69cfef194a8dc738842b4" />
  <project path="vendor/xiaomi/lavender" name="proprietary_vendor_xiaomi_lavender" remote="crdroid-gio" revision="483e3e7ca5828c54d8b4408b87ee14069a8d027b" />
</manifest>
XML
repo manifest -o "$OUT/merged-manifest.xml"

PACK_ID="$PACK_ID" PACK_COUNT="$PACK_COUNT" OUT="$OUT" python3 - <<'PY'
import hashlib, os, pathlib, xml.etree.ElementTree as ET
root=ET.parse(pathlib.Path(os.environ['OUT'])/'merged-manifest.xml').getroot()
n=int(os.environ['PACK_COUNT']); bucket=int(os.environ['PACK_ID'])
paths=[]
for p in root.findall('project'):
    path=p.get('path') or p.get('name')
    if int.from_bytes(hashlib.sha256(path.encode()).digest()[:8],'big') % n == bucket:
        paths.append(path)
paths=sorted(set(paths))
if not paths: raise SystemExit('empty deterministic pack')
(pathlib.Path(os.environ['OUT'])/'paths.txt').write_text('\n'.join(paths)+'\n')
print('PACK_PROJECT_COUNT='+str(len(paths)))
PY

mapfile -t projects < "$OUT/paths.txt"
repo sync -c --force-sync --optimized-fetch --prune --no-clone-bundle --no-tags -j4 "${projects[@]}"

echo 'SYNC_ASSIGNED_PROJECTS=PASS'
PACK_ID="$PACK_ID" PACK_COUNT="$PACK_COUNT" ROOT="$ROOT" OUT="$OUT" python3 - <<'PY'
import json, os, pathlib, subprocess
root=pathlib.Path(os.environ['ROOT']); out=pathlib.Path(os.environ['OUT'])
rows=[]
for path in (out/'paths.txt').read_text().splitlines():
    p=root/path
    if not p.exists(): raise SystemExit('missing '+path)
    sha=subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()
    rows.append({'path':path,'sha':sha})
obj={'schema':'gio.os.public-source-pack.v1','pack_id':int(os.environ['PACK_ID']),'pack_count':int(os.environ['PACK_COUNT']),'projects':rows,'public_inputs_only':True,'private_gio_source_present':False,'signing_keys_present':False}
(out/f"pack-{int(os.environ['PACK_ID'])}-projects.json").write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
PY

# Remove repo worktree pointers; .repo itself is excluded from the compressed public source image.
find "$ROOT" -type f -name .git -delete
PACK="$OUT/gio-a14-source-pack-$PACK_ID.sqfs"
mksquashfs "$ROOT" "$PACK" -noappend -comp zstd -Xcompression-level 15 -processors 2 -e .repo
sha256sum "$PACK" > "$PACK.sha256"
split -b 1800M -d -a 2 "$PACK" "$OUT/gio-a14-source-pack-$PACK_ID.sqfs.part-"
sha256sum "$OUT"/gio-a14-source-pack-$PACK_ID.sqfs.part-* > "$OUT/gio-a14-source-pack-$PACK_ID.chunks.sha256"

# Public source only: publish in this public shard repository. No private GIO material is present.
if ! gh release view "$TAG" >/dev/null 2>&1; then
  gh release create "$TAG" --target "$GITHUB_SHA" --title "GIO Android 14 public source pack $PACK_ID/15" \
    --notes "Public upstream Android/crDroid source only. No private GIO OS source and no signing keys."
fi
assets=("$OUT/pack-$PACK_ID-projects.json" "$PACK.sha256" "$OUT/gio-a14-source-pack-$PACK_ID.chunks.sha256")
for f in "$OUT"/gio-a14-source-pack-$PACK_ID.sqfs.part-*; do assets+=("$f"); done
gh release upload "$TAG" "${assets[@]}" --clobber

echo "RAZZO_SOURCE_PACK=READY"
echo "PACK_ID=$PACK_ID"
echo "TAG=$TAG"
echo "PACK_SHA256=$(awk '{print $1}' "$PACK.sha256")"
df -h /
