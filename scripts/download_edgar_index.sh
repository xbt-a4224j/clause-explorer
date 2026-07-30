#!/usr/bin/env bash
# Download EDGAR's company-name -> CIK index into data/edgar/ (#9).
#
# One 38 MB file instead of 152 name-search requests, and it includes delisted registrants —
# which is what these targets are, having just been acquired. Company identification is then
# an offline dictionary lookup, so the tests never touch the network.
#
# SEC requires a descriptive User-Agent on automated requests.
set -euo pipefail

UA="Clause Explorer research (open source; contact alex4334johnson@gmail.com)"
DEST="$(cd "$(dirname "$0")/.." && pwd)/data/edgar"
OUT="${DEST}/cik-lookup-data.txt"

mkdir -p "${DEST}"
if [ ! -s "${OUT}" ]; then
  curl -sfL -A "${UA}" -o "${OUT}" https://www.sec.gov/Archives/edgar/cik-lookup-data.txt
fi

echo "file: ${OUT}"
echo "bytes: $(wc -c <"${OUT}" | tr -d ' ')"
echo "lines: $(wc -l <"${OUT}" | tr -d ' ')"
echo "sha256: $(shasum -a 256 "${OUT}" | cut -d' ' -f1)"
echo "fetched: $(date -u +%Y-%m-%d)"
