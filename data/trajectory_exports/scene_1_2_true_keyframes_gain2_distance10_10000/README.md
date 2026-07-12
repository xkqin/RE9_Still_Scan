# Scene 1.2: 10,000 True-Keyframe Trajectories

- 10,000 trajectories: four target anchors, 2,500 trajectories per anchor.
- Every exported keyframe is an original EZCAM-scored still pose.
- Real keyframe scores are strictly increasing in UI replay order.
- Score gain is at least 2.0 and net physical displacement is at least 10 m.
- Path/net ratio is at most 1.5, target-distance backtracking is at most 0.3 m, and near revisits are forbidden.
- All 10,000 physical XYZ geometry signatures are unique.

Use `scene_1_2_true_gain2_distance10_10000_low_to_high_ui.json` for the capture UI. The larger `*_trajectories.json` file retains planning provenance and measured-score metadata.

The score guarantee applies to exported real keyframes. Runtime interpolation frames have not been recaptured or scored, and continuous collision clearance has not been verified against a scene mesh. Run a smoke capture before full collection.
