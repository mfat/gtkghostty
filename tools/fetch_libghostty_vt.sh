#!/bin/sh
# Downloads and verifies signed official libghostty-vt 1.0.0 release files.
# Does NOT build the library. Requires curl, minisign, python3.
set -eu
BASE='https://release.files.ghostty.org/libghostty-vt/1.0.0'
OUT="${1:-libghostty-downloads}"
mkdir -p "$OUT"
cd "$OUT"
for f in SHA256SUMS SHA256SUMS.minisig libghostty-vt-1.0.0.tar.gz libghostty-vt-1.0.0-deps.tar.gz; do
  curl --fail --location --retry 3 --output "$f" "$BASE/$f"
done
# Official key copied from https://lib.ghostty.org/vt/installing.html
minisign -V -P 'RWQlAjJC23149WL2sEpT/l0QKy7hMIFhYdQOFy0Z7z7PbneUgvlsnYcV' -m SHA256SUMS
python3 - <<'PY'
from pathlib import Path
import hashlib
expected = {}
for line in Path('SHA256SUMS').read_text().splitlines():
    parts=line.split()
    if len(parts)>=2 and len(parts[0])==64:
        expected[parts[-1].lstrip('*')] = parts[0].lower()
for name in ('libghostty-vt-1.0.0.tar.gz','libghostty-vt-1.0.0-deps.tar.gz'):
    assert name in expected, f'No checksum in manifest: {name}'
    h = hashlib.sha256()
    with Path(name).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    digest=h.hexdigest()
    assert digest==expected[name], f'Checksum mismatch: {name}'
    print(f'Verified SHA256: {name}')
PY
printf 'Release verified. See docs/BOOTSTRAP.md for Zig 0.17 build commands.\n'
