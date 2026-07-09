# scene_1.1 low-to-high 4000 gain1p3 trajectories

This folder contains the capture-ready low-to-high export for `scene_1.1`.

The original planning batch selected the highest-scored pose first and generated straight-line paths from that high-score anchor to lower-score endpoints. This export reverses every trajectory for capture:

```text
lower-score start -> highest-score endpoint
```

Summary:

- Count: 4000 trajectories
- Keyframes per trajectory: 80
- Duration: 15.8 seconds
- Time step: 0.2 seconds
- Direction: low score to high score
- Final endpoint: highest-scored `scene_1.1` pose
- Final score: 7.127104
- Minimum score gain: 1.3
- Physical signatures: 4000 unique
- Low-score start nodes: 4000 unique

Files:

- `scene_1_1_low_to_high_4000_gain1p3_trajectories.json`: replay trajectory data
- `trajectory_summary.csv`: per-trajectory metrics in low-to-high direction
- `trajectory_score_curves.png`: low-to-high score curves
- `physical_distance_vs_time.png`: cumulative physical distance over time
- `trajectory_xz_paths.png`: X-Z path plot
- `trajectory_distance_hist.png`: path length histogram
- `capture_readiness_validation.json`: pre-capture validation report

Note: no scene mesh, depth map, or collision volume is included, so this export cannot prove absence of clipping through geometry. Middle keyframes are straight interpolation between scored endpoint poses.
