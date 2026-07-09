# scene_1.1 top-start 4000 gain1p3 trajectories

This folder contains the `scene_1.1` straight-line trajectory export generated from scored still-camera poses.

- Count: 4000 trajectories
- Keyframes per trajectory: 80
- Duration: 15.8 seconds
- Time step: 0.2 seconds
- Start anchor: highest-scored `scene_1.1` pose
- Start score: 7.127104
- Minimum score gain/drop from start to endpoint: 1.3
- Path length range: 10.345-47.225 m
- Physical signatures: 4000 unique
- Endpoints: 4000 unique

Files:

- `scene_1_1_topstart_4000_trajectories.json`: replay trajectory data
- `trajectory_summary.csv`: per-trajectory metrics
- `trajectory_score_curves.png`: score curves
- `physical_distance_vs_time.png`: cumulative physical distance over time
- `trajectory_xz_paths.png`: X-Z path plot
- `trajectory_distance_hist.png`: path length histogram
- `capture_readiness_validation.json`: pre-capture validation report
- `clipping_risk_proxy_summary.json/csv`: nearest sampled-node distance risk proxy

Note: only start and end keyframes are exact scored still-camera nodes. Middle keyframes are straight interpolation. No scene mesh, depth map, or collision volume is included, so this export cannot prove absence of clipping through geometry.
