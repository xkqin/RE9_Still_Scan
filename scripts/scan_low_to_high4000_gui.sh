#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TRAJECTORY_SET=custom \
TRAJECTORY_JSON="${PROJECT_ROOT}/data/trajectory_exports/scene_1_1_low_to_high_4000_gain1p3/scene_1_1_low_to_high_4000_gain1p3_trajectories.json" \
TRAJECTORY_OUTPUT_DIR="${PROJECT_ROOT}/data/videos/trajectories/scene_1_1_low_to_high_4000_gain1p3" \
TRAJECTORY_LABEL="scene_1.1 low-to-high 4000 gain1p3" \
TRAJECTORY_SESSION_PREFIX="scene_1_1_low_to_high_4000_gain1p3" \
RE9_OBS_RESTART_EVERY_N="${RE9_OBS_RESTART_EVERY_N:-30}" \
RE9_OBS_RESTART_WAIT_SEC="${RE9_OBS_RESTART_WAIT_SEC:-30}" \
RE9_OBS_RESTART_COMMAND="${RE9_OBS_RESTART_COMMAND:-/usr/bin/obs --collection RE9_Still_Scan --profile Untitled --disable-missing-files-check}" \
"${SCRIPT_DIR}/scan_gui.sh" "$@"
