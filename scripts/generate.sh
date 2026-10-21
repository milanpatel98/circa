#!/usr/bin/env bash
# Generate the synthetic patients Rounds is tested on. Same seeds and dates give the same people.
# Needs Java 17+. Output: synthea/fhir/*.json (not committed; `rounds ingest` turns it into data/charts).
set -euo pipefail
export LC_ALL=C.UTF-8 LANG=C.UTF-8
cd "$(dirname "$0")/.."
JAR=tools/synthea-3.3.0.jar
if [ ! -f "$JAR" ]; then
  mkdir -p tools
  curl -sSL -o "$JAR" https://github.com/synthetichealth/synthea/releases/download/v3.3.0/synthea-with-dependencies.jar
fi
rm -rf synthea
common=(-r 20261020 -e 20261020 --exporter.fhir.export=true --exporter.hospital.fhir.export=false
        --exporter.practitioner.fhir.export=false --exporter.years_of_history=12 --exporter.baseDirectory=./synthea)
LC_ALL=C.UTF-8 java -Dsun.jnu.encoding=UTF-8 -Dfile.encoding=UTF-8 -jar "$JAR" -s 1101 -cs 1101 -p 90 -a 40-90 "${common[@]}" Colorado
LC_ALL=C.UTF-8 java -Dsun.jnu.encoding=UTF-8 -Dfile.encoding=UTF-8 -jar "$JAR" -s 2202 -cs 2202 -p 40 "${common[@]}" Colorado
echo "patients: $(ls synthea/fhir | wc -l)"
