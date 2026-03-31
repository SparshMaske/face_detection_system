#!/usr/bin/env bash
set -euo pipefail

# Copies InsightFace models from local cache into project-local model folder
# so backend can run fully offline with FACE_OFFLINE_ONLY=1.
#
# Usage:
#   bash raspberry_pi/sync_local_face_models.sh [MODEL_NAME]
#
# Example:
#   bash raspberry_pi/sync_local_face_models.sh buffalo_s

MODEL_NAME="${1:-buffalo_s}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_ROOT="${HOME}/.insightface/models/${MODEL_NAME}"
DST_ROOT="${PROJECT_ROOT}/backend/models/insightface/models/${MODEL_NAME}"

if [[ ! -d "${SRC_ROOT}" ]]; then
  echo "Source model folder not found: ${SRC_ROOT}"
  echo "Run the backend once on a machine with internet to cache model first."
  exit 1
fi

mkdir -p "${DST_ROOT}"
rsync -a "${SRC_ROOT}/" "${DST_ROOT}/"

echo "Model synced to: ${DST_ROOT}"
echo "You can now run with FACE_OFFLINE_ONLY=1 and FACE_MODEL_ROOT=${PROJECT_ROOT}/backend/models/insightface"
