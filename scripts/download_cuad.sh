#!/usr/bin/env bash
# Download CUAD v1 (CC BY 4.0, The Atticus Project) into data/cuad/.
#
# Same source pattern as MAUD: one `data.zip` from the project's GitHub repo, so provenance is
# one command and one sha256. `category_descriptions.csv` comes alongside it — the 41 clause
# categories are read from that file rather than hardcoded, for the same reason the 92 deal
# points are read from MAUD.
set -euo pipefail

BASE="https://raw.githubusercontent.com/The-Atticus-Project/cuad/main"
DEST="$(cd "$(dirname "$0")/.." && pwd)/data/cuad"
ZIP="${DEST}/data.zip"

mkdir -p "${DEST}"

[ -s "${ZIP}" ] || curl -sfL -o "${ZIP}" "${BASE}/data.zip"
[ -s "${DEST}/category_descriptions.csv" ] ||
  curl -sfL -o "${DEST}/category_descriptions.csv" "${BASE}/category_descriptions.csv"

unzip -qn "${ZIP}" -d "${DEST}"

echo "sha256: $(shasum -a 256 "${ZIP}" | cut -d' ' -f1)"
echo "archive bytes: $(wc -c <"${ZIP}" | tr -d ' ')"
echo "files extracted: $(find "${DEST}" -type f ! -name data.zip | wc -l | tr -d ' ')"
