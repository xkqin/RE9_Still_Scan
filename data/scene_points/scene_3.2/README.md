# Scene 3.2 point archive

This directory preserves the current REFramework New Scene recording and its
interactive 3D map as `scene_3.2`. It is independent of the live game files and
existing scene archives.

## Files

- `scene_3.2_points.csv`: byte-identical copy of the live CSV.
- `scene_3.2_points.json`: byte-identical point payload with only the top-level
  scene label changed from `new_scene` to `scene_3.2`.
- `scene_3.2_3d_map.html`: standalone interactive map with the convex hull,
  capture order, point labels, and selectable coordinates.
- `scene_3.2_5layer_dense_scan_layers.yaml`: hull-aware five-layer scan config.
- `scene_3.2_5layer_dense_positions.json`: exact generated positions grouped by
  layer, with plan metadata and totals.
- `scene_3.2_5layer_dense_positions.csv`: flat position table for inspection.

## Snapshot

- Records: 62
- Unique XYZ coordinates: 62
- Index range: 1-62, continuous
- X bounds: `-17.142046976` to `39.940287288`
- Y bounds: `13.124972569` to `28.166784629`
- Z bounds: `-358.155693537` to `-265.262052014`

## Five-layer dense plan

- Layer heights: `14.629153775`, `17.637516187`, `20.645878599`,
  `23.654241011`, and `26.662603423`
- Valid positions per layer: `86`, `111`, `113`, `108`, and `33`
- Valid positions: `451`
- Views per position: `22`
- Planned images: `9,922`
- Candidate grid: `11 x 18` aspect-matched X/Z grid, filtered by a 23-vertex
  3D convex hull
- The original 62 recorded boundary records remain unchanged.

## Source provenance

- Source JSON: `reframework/data/re9_new_scene_points.json`
- Source JSON modified: `2026-07-22T23:50:26.2184256+08:00`
- Source JSON SHA-256: `2BA2697B72E229FD7D4FA3DCDF2E00554981B329699FF8CCFE58627C42027E8D`
- Source CSV: `reframework/data/re9_new_scene_points.csv`
- Source CSV modified: `2026-07-22T23:50:26.2149189+08:00`
- Source CSV SHA-256: `644B51919616F05A1555DF26CA0EC346066F52590C8D9091997094C4458024C8`

## Archive hashes

- `scene_3.2_points.json`: `3C4866C730CBACE32F0ACA710D95DB6954DAAA23DFADC73FB1A65D12041769D3`
- `scene_3.2_points.csv`: `644B51919616F05A1555DF26CA0EC346066F52590C8D9091997094C4458024C8`
- `scene_3.2_3d_map.html`: `29EB048DAAE325530CC5EE0A64509F244308A7D929F06785E96BE21F4E7932A7`
- `scene_3.2_5layer_dense_scan_layers.yaml`: `B7D498967C93DDD5A24C061CC218171B4EA279A73EBFA4EF5E94C13BB4847B8A`
- `scene_3.2_5layer_dense_positions.json`: `4C8CBED2CB2850DE5A88E365A081FBF577188E93A93F99AF89520D71F875C8E5`
- `scene_3.2_5layer_dense_positions.csv`: `B78FCB7711F3BEB4ED4F11FA6A213DAB85A8665CF45419D495A98B9F9B1BEC27`
