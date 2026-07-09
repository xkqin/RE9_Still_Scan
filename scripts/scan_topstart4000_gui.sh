#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TRAJECTORY_SET=custom \
TRAJECTORY_JSON="${PROJECT_ROOT}/data/trajectory_exports/scene_1_1_topstart_4000_gain1p3/scene_1_1_topstart_4000_trajectories.json" \
TRAJECTORY_OUTPUT_DIR="${PROJECT_ROOT}/data/videos/trajectories/scene_1_1_topstart_4000_gain1p3" \
TRAJECTORY_LABEL="scene_1.1 topstart 4000 gain1p3" \
TRAJECTORY_SESSION_PREFIX="scene_1_1_topstart_4000_gain1p3" \
"${SCRIPT_DIR}/scan_gui.sh" "$@"
