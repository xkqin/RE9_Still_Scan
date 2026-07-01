# RE9 FreeCam Dataset Capture Toolkit

Tools for collecting reproducible Resident Evil Requiem / Resident Evil 9 FreeCam still-image datasets with OBS, plus optional video recording, pose logging, LAION aesthetic scoring, and pose/score reports.

> Current platform support: Windows only. The project is developed and tested on Windows with Steam, OBS Studio, REFramework, and PowerShell scripts. Linux/Steam Proton support is not currently tested or documented.

The main workflow is:

1. Install Resident Evil Requiem, REFramework, and the RE9 FREECAM CED mod yourself.
2. Patch the FreeCam Lua script with this project's reversible logger/control block.
3. Use OBS WebSocket as the capture backend.
4. Define scan regions as `x/y/z` planes in YAML.
5. Let Python move the FreeCam through the scan grid and save high-quality still images plus CSV metadata.

The repository is intentionally code-only. It does not include game files, mod files, screenshots, videos, generated datasets, model weights, or Nexus mod downloads.

## Who this is for

- Researchers or artists who want reproducible FreeCam image datasets from manually installed mods.
- People who want each captured image paired with `x`, `y`, `z`, `yaw`, `pitch`, and source metadata.
- Users who want to compare viewpoints later with optional LAION aesthetic scoring.
- Anyone who wants a configurable OBS + FreeCam capture pipeline without modifying the game executable or FreeCam DLL.

## What this project does

- Backs up and minimally patches `RE9FreeCam.lua` with a reversible pose logger block.
- Communicates with Lua only through JSON files in `reframework/data`.
- Controls OBS through OBS WebSocket.
- Captures still images from OBS using configurable scan planes and view patterns.
- Writes per-image CSV metadata for position, yaw, pitch, dataset, and file path.
- Extracts video frames at a configured FPS.
- Scores frames using CLIP embeddings plus LAION aesthetic predictor weights.
- Aligns frame timestamps to camera pose timestamps.
- Generates `scores.csv`, `pose_log.csv`, `scores_with_pose.csv`, plots, copied top frames, and `report.html`.

## What this project does not do

- It does not control player movement or gameplay.
- It does not know the map collision mesh, so scan regions must be chosen by the user.
- It does not modify `RE9FreeCamPlugin.dll`.
- It does not read game memory from Python.
- It does not modify the game executable.
- It does not redistribute Nexus mods.
- It does not include game assets, videos, screenshots, or mod files.

## Installation

This section assumes Windows. The provided scripts are PowerShell scripts and the default paths use a Windows Steam install location.

1. Install Resident Evil Requiem.
2. Install REFramework manually.
3. Install the RE9 FreeCam mod manually.
4. Confirm this Lua path exists, or edit `configs/default.yaml`:

```powershell
D:\steam\steamapps\common\RESIDENT EVIL requiem BIOHAZARD requiem\reframework\autorun\RE9FreeCam.lua
```

5. Install OBS Studio.
6. Enable OBS WebSocket:
   OBS -> Tools -> WebSocket Server Settings -> Enable WebSocket Server
   Port: `4455`
   Password: set one.
7. Install Python 3.10+.
8. Install Git.

## Required Nexus Mods

This repository does not include or redistribute Nexus mod files. Download and install these manually from Nexus Mods:

- [REFramework](https://www.nexusmods.com/residentevilrequiem/mods/13): a scripting/API framework for RE Engine games. This project relies on REFramework's Lua runtime, `reframework/autorun` script loading, and `reframework/data` file access so Python can communicate with Lua by JSON files.
- [RE9 FREECAM CED](https://www.nexusmods.com/residentevilrequiem/mods/1147): the Resident Evil Requiem FreeCam mod used to manually or scriptedly position the camera. The Nexus page lists REFramework as a requirement.

Install summary:

1. Install REFramework for Resident Evil Requiem following the Nexus mod instructions.
2. Install RE9 FREECAM CED after REFramework.
3. The FreeCam plugin DLL should be placed under:

```text
<game folder>/reframework/plugins/
```

4. The FreeCam Lua script should be placed under:

```text
<game folder>/reframework/autorun/
```

5. Confirm this file exists before patching:

```text
D:\steam\steamapps\common\RESIDENT EVIL requiem BIOHAZARD requiem\reframework\autorun\RE9FreeCam.lua
```

The Python patcher only backs up and modifies `RE9FreeCam.lua`. It never modifies the game executable, never modifies the FreeCam DLL, and never reads game memory from Python.

## Python setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m re9_pose_recorder.cli setup-laion
```

`requirements.txt` includes `-e .`, so the local `src/re9_pose_recorder` package is installed in editable mode and `python -m re9_pose_recorder.cli` works from the virtual environment.

Or use:

```powershell
.\scripts\setup_windows.ps1
.\scripts\setup_laion_repo.ps1
```

## Patch Lua

The patcher creates a timestamped backup before it modifies `RE9FreeCam.lua`.
Injected Lua is contained only between:

```lua
-- BEGIN RE9_AESTHETIC_POSE_LOGGER
-- END RE9_AESTHETIC_POSE_LOGGER
```

Run:

```powershell
python -m re9_pose_recorder.cli check-lua
python -m re9_pose_recorder.cli backup-lua
python -m re9_pose_recorder.cli patch-lua-logger
python -m re9_pose_recorder.cli verify-lua-patch
```

## Test OBS

```powershell
python -m re9_pose_recorder.cli obs-test --obs-password YOUR_PASSWORD
```

If OBS is not running, WebSocket is disabled, the port is wrong, or the password is wrong, the command prints connection guidance.

## Still image scan datasets

This is the current primary workflow. The scanner moves the FreeCam through configured `x/y/z` scan regions, captures OBS still images, and writes a CSV row for every image.

Before starting:

1. Start the game.
2. Enable FreeCam.
3. Open OBS and make sure the current Program scene captures the game cleanly.
4. Close the REFramework menu before capture begins. If the REFramework overlay is visible in OBS, it will be visible in the saved images.

Run the default street/upper-plane scan:

```powershell
python scripts\scan_stills_gui.py
```

Run the two-scene scan example:

```powershell
python scripts\scan_new_scenes_gui.py
```

The scan definitions live in:

```text
configs/still_scan_layers.yaml
configs/new_scene_scan_layers.yaml
```

Each layer/zone defines a rectangular region using two diagonal points and a sampling density:

```yaml
layers:
  - id: scene01_plane01
    y: 13.91
    point_a: {x: -5.07, y: 12.53, z: -262.11}
    point_b: {x: 24.01, y: 13.91, z: -324.49}
    zones:
      - id: dense
        points_x: 12
        points_z: 12
```

For each position, the scanner captures 22 views:

- `pitch = 0`, yaw every 45 degrees: 8 images.
- `pitch = +45`, yaw every 60 degrees: 6 images.
- `pitch = -45`, yaw every 60 degrees: 6 images.
- `pitch = +90` and `-90`: 2 images.

Outputs are saved under:

```text
data/stills/scans/<session>/datasets/<dataset_id>/images/
data/stills/scans/<session>/datasets/<dataset_id>/samples.csv
data/stills/scans/<session>/samples.csv
```

Generated still images are ignored by Git. Do not commit game screenshots or datasets to this repository.

By default, the scanner captures the current OBS Program scene as PNG at the OBS Base Canvas resolution. For highest quality, set OBS `Settings -> Video -> Base Canvas Resolution` to the resolution you want before scanning. If your OBS Program scene includes overlays, menus, or display-capture artifacts, those will be saved too; use a clean Game Capture scene and close the REFramework UI with `Insert` before starting.

## Record and score

Start the game, enable/use the FreeCam manually, make sure OBS capture is configured, then run:

```powershell
python -m re9_pose_recorder.cli record-and-score --obs-password YOUR_PASSWORD --fps 2 --device cuda --top-k 50
```

Flow:

1. Python verifies the Lua file and patch.
2. Python verifies the LAION repo exists.
3. Python connects to OBS.
4. Python writes `re9_pose_control.json` with a new session id.
5. Lua starts writing pose CSV rows while FreeCam mode is active.
6. You press Enter to start OBS recording.
7. You manually fly the FreeCam.
8. You press Enter to stop.
9. Python stops OBS, tells Lua to stop, extracts frames, scores them, aligns pose, and writes reports.

To let the command clone/update LAION automatically:

```powershell
python -m re9_pose_recorder.cli record-and-score --obs-password YOUR_PASSWORD --fps 2 --device cuda --top-k 50 --auto-setup-laion
```

## One-click recording window

For a small button window that starts/stops OBS recording and Lua pose logging, with a live LAION aesthetic score from the cloned `LAION-AI/aesthetic-predictor` model:

```powershell
python -m re9_pose_recorder.cli one-click-record --obs-password YOUR_PASSWORD --device cuda
```

Or:

```powershell
.\scripts\one_click_record.ps1 -ObsPassword YOUR_PASSWORD -Device cuda
```

Click `Start Recording` once to start OBS and pose logging. The window periodically captures the current OBS Program scene, scores it with the LAION aesthetic predictor, and displays current/average/best scores. Click `Stop Recording` once to stop both. This records only; run `analyze-video` afterwards if you want full scoring/report generation.

The control window is topmost by default so it can float above the game. To keep it out of the recorded video, use OBS `Game Capture` for the game rather than `Display Capture`; Game Capture records the game content and not the Python control window.

During recording, the window can split the OBS recording into 5-second video segments, score every frame in each segment, and write the best frame from each segment:

```text
outputs/segment_best_5s_SESSION.csv
```

Each row contains the highest-scoring frame in that 5-second video segment plus nearest logged `x`, `y`, `z`, `yaw`, `pitch`, and `fov`. This uses OBS `split_record_file`, so OBS will produce multiple segment files while recording.

OpenCLIP/Hugging Face model files are cached under `third_party/huggingface_cache` so later launches reuse the project-local copy. Live score samples are saved under `outputs/live_scores_SESSION.csv`. Disable live scoring with:

```powershell
python -m re9_pose_recorder.cli one-click-record --obs-password YOUR_PASSWORD --no-live-score
```

To pre-download and load the live-score model before recording:

```powershell
python -m re9_pose_recorder.cli warmup-laion --device cuda
```

## Analyze existing video and pose log

```powershell
python -m re9_pose_recorder.cli analyze-video --video data/videos/session.mp4 --pose-log data/pose_logs/pose_log.csv --fps 2 --device cuda --top-k 50
```

## Individual commands

```powershell
python -m re9_pose_recorder.cli extract-frames --video data/videos/session.mp4 --out data/frames/session_001 --fps 2
python -m re9_pose_recorder.cli score-frames --input data/frames/session_001 --output outputs/scores.csv --device cuda --batch-size 32
python -m re9_pose_recorder.cli align-pose --scores outputs/scores.csv --pose-log data/pose_logs/re9_freecam_pose_log.csv --out outputs/scores_with_pose.csv
```

Build a sampled trajectory that climbs toward the best scored pose:

```powershell
python -m re9_pose_recorder.cli build-trajectory --scores-with-pose outputs/scores_with_pose.csv --out outputs/trajectory_to_best.csv --plot outputs/trajectory_to_best.png
```

The CSV is ordered low/starting pose to best sampled pose. Read it in reverse order for a high-to-low score trajectory.

Pose logging only:

```powershell
python -m re9_pose_recorder.cli start-pose-log
python -m re9_pose_recorder.cli stop-pose-log --session-id 20260522_123000
```

## Restore Lua

```powershell
python -m re9_pose_recorder.cli restore-lua --backup backups/lua/RE9FreeCam.lua.TIMESTAMP.bak
```

The restore command copies the selected backup over the configured `RE9FreeCam.lua`.

## Outputs

By default, outputs are written under `outputs/`:

- `scores.csv`: one row per extracted frame with LAION aesthetic score.
- `pose_log.csv`: copy of the Lua pose CSV for the session.
- `scores_with_pose.csv`: score rows aligned with `x`, `y`, `z`, `yaw`, `pitch`, and `fov`.
- `score_curve.png`: aesthetic score over time.
- `camera_path.png`: top-down `x` vs `z` camera path, colored by score when pose alignment exists.
- `top_frames/`: copied best frames named with rank, score, timestamp, and pose.
- `report.html`: summary, plots, top frames, and an aligned sample table.

If existing output files would be overwritten and `video.overwrite` is false, a timestamped/session output directory is created under `outputs/`.

## Error handling notes

- Wrong Lua path: edit `configs/default.yaml` and rerun `check-lua`.
- Missing Lua patch: run `patch-lua-logger`.
- OBS connection failure: open OBS, enable WebSocket, confirm port `4455`, and check the password.
- Missing Git: install Git for Windows and rerun `setup-laion`.
- Missing LAION repo: run `setup-laion`.
- CUDA unavailable: the scorer falls back to CPU when `device` is `auto`, and warns when `cuda` was requested.
- Missing pose log after recording: video scoring can still continue, but pose alignment is marked invalid.
- Corrupted frames: skipped with warnings.

## Lua logger details

The Lua patch writes:

```text
session_id,timestamp_sec,x,y,z,yaw,pitch,fov,freecam_mode,user_has_rotated
```

It polls:

```text
reframework/data/re9_pose_control.json
```

and writes status to:

```text
reframework/data/re9_pose_status.json
```

Start control example:

```json
{
  "command": "start",
  "session_id": "20260522_123000",
  "pose_log_file": "D:/steam/steamapps/common/RESIDENT EVIL requiem BIOHAZARD requiem/reframework/data/re9_freecam_pose_log_20260522_123000.csv",
  "interval_sec": 0.033333
}
```

Stop control example:

```json
{
  "command": "stop",
  "session_id": "20260522_123000"
}
```

The patch uses `json.load_file` / `json.dump_file` when available, falls back to simple file IO where possible, and reports write errors in the REFramework UI/status file without intentionally crashing the game.

## Project layout

```text
re9-freecam-aesthetic-pose-recorder/
  configs/default.yaml
  src/re9_pose_recorder/
  data/videos/
  data/frames/
  data/pose_logs/
  outputs/
  scripts/
  third_party/
```

Run the CLI with:

```powershell
python -m re9_pose_recorder.cli
```
