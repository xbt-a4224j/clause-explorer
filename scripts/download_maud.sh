#!/usr/bin/env bash
# Download MAUD v1 (CC BY 4.0, The Atticus Project) into data/maud/.
#
# Source of record is `data.zip` from the project's GitHub repo, not the Hugging Face mirror.
# The mirror ships the three label CSVs but only **100** of the 152 contract texts; the zip
# ships all 152. Drill-through to clause text is a hard requirement (CLAUDE.md), and a matter
# whose text is missing cannot drill through, so the incomplete source is unusable here.
#
# One file means one command and one sha256 in docs/provenance.md. Idempotent: re-running
# with the archive already downloaded and extracted does nothing.
set -euo pipefail

URL="https://raw.githubusercontent.com/The-Atticus-Project/maud/main/data.zip"
DEST="$(cd "$(dirname "$0")/.." && pwd)/data/maud"
ZIP="${DEST}/data.zip"

mkdir -p "${DEST}"

if [ ! -s "${ZIP}" ]; then
  curl -sfL -o "${ZIP}" "${URL}"
fi

# -n: never overwrite, so a re-run cannot clobber a file mid-read. -j is deliberately NOT
# used: the archive's `data/contracts/` layout is what the parser (#8) expects.
unzip -qn "${ZIP}" -d "${DEST}"

echo "sha256: $(shasum -a 256 "${ZIP}" | cut -d' ' -f1)"
echo "archive bytes: $(wc -c <"${ZIP}" | tr -d ' ')"
echo "contract files: $(find "${DEST}/data/contracts" -name 'contract_*.txt' | wc -l | tr -d ' ')"
echo "extracted bytes: $(du -sk "${DEST}/data" | cut -f1) KiB"
