# Scene 3.1 point archive

This directory preserves the current REFramework New Scene point recording as
`scene_3.1`. It is independent of the live game files and existing scene data.

## Files

- `scene_3.1_points.csv`: byte-identical copy of the live CSV.
- `scene_3.1_points.json`: byte-identical point payload with only the top-level
  scene label changed from `new_scene` to `scene_3.1`.
- `scene_3.1_5layer_dense_scan_layers.yaml`: hull-aware five-layer scan config.
- `scene_3.1_5layer_dense_positions.json`: exact generated positions grouped by
  layer, with plan metadata and totals.
- `scene_3.1_5layer_dense_positions.csv`: flat position table for inspection.

## Snapshot

- Records: 88
- Unique XYZ coordinates: 87
- Index range: 1-88, continuous
- Duplicate: records 87 and 88 share identical XYZ and camera values at
  `(100.526896525, 12.919827100, -347.192803857)`.
- X bounds: `88.657193007` to `136.011375096`
- Y bounds: `2.105327390` to `19.288590753`
- Z bounds: `-350.754226494` to `-309.493450136`

## Five-layer dense plan

- Layer heights: `3.823653726`, `7.260306399`, `10.696959072`,
  `14.133611744`, and `17.570264417`
- Valid positions per layer: `49`, `134`, `138`, `141`, and `58`
- Valid positions: `520`
- Views per position: `22`
- Planned images: `11,440`
- Candidate grid: `14 x 14` per layer, filtered by a 16-vertex 3D convex hull
- The original 88 recorded boundary records remain unchanged.

## Source provenance

- Source JSON: `reframework/data/re9_new_scene_points.json`
- Source JSON modified: `2026-07-22T23:36:21.6064319+08:00`
- Source JSON SHA-256: `65F20F7408E1146EE9C2B955E45671B08AE537353948E3A59134CB7A7288EA90`
- Source CSV: `reframework/data/re9_new_scene_points.csv`
- Source CSV modified: `2026-07-22T23:36:21.6029104+08:00`
- Source CSV SHA-256: `A7C2C8F56874A0FA97F09B05C81F649894D76AF8B3090136D16016512D78CD5E`

## Archive hashes

- `scene_3.1_points.json`: `7F548227687C33B34B4E6CEEF9569F2D579D11C1450765BF3E4906DE50EB51FE`
- `scene_3.1_points.csv`: `A7C2C8F56874A0FA97F09B05C81F649894D76AF8B3090136D16016512D78CD5E`
- `scene_3.1_5layer_dense_scan_layers.yaml`: `2108B5A84D27C87C0E3B5B634114503CFC206EE822A5000CB7050572AC3912EB`
- `scene_3.1_5layer_dense_positions.json`: `2E1995785C81A62BC3DA170A9DD410B29E73BD248B7513EA4D9947571BCFD9BA`
- `scene_3.1_5layer_dense_positions.csv`: `8E7DDDB1D654E2ADBC884D68B8177FFF880895195DB64B58936D8F84BC2511B5`
