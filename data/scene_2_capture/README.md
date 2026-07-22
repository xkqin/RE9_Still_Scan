# Scene 2 REFramework capture bundle

This folder is a snapshot of the tested scene 2 capture state.

- `reframework/autorun/RE9FreeCam.lua` contains the FreeCam capture UI and Lua control bridge.
- `reframework/data/re9_new_scene_points.csv` and `.json` contain the recorded scene points present on the source machine.

Copy the contents of `reframework/` into the target game's existing
`reframework/` directory, preserving the `autorun/` and `data/` folders. Back
up an existing `RE9FreeCam.lua` first if it has local changes.

Then run `python scripts/scan_new_scenes_gui.py`. The still scan starts at
`scene_2_y01`, and the trajectory selector starts at index 1.
