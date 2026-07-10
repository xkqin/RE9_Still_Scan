# Scene 1.1 True-Keyframe Smoke Set

This export contains 10 low-to-high smoke-test trajectories for `scene_1.1`.

- Every exported keyframe is an exact scored source pose.
- Measured keyframe scores are strictly increasing.
- Score gain is at least `2.0` (observed minimum: `2.057227`).
- Every trajectory ends at the global maximum score `7.127104` pose.
- Each trajectory contains 13-16 real keyframes.
- Materialized interpolated keyframes: 0.
- Complete physical geometry signatures: 10 unique out of 10.

The existing Lua trajectory player interpolates camera motion continuously
between timed keyframes. Those runtime frames are not included as scored
evidence in this JSON.

Files:

- `scene_1_1_true_gain2_optimal_10_trajectories.json`: replay trajectories.
- `trajectory_summary.csv`: per-trajectory statistics.
- `validation.json`: hard-constraint validation.
- `generation_diagnostics.json`: graph and search diagnostics.
- `real_keyframe_score_curves.png`: measured score curves.
- `physical_distance_vs_time.png`: cumulative physical distance.
- `trajectory_xz_paths.png`: x-z route projection.
