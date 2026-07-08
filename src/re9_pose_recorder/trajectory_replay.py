from __future__ import annotations

import csv
import json
import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig
from .lua_control import LuaControl, make_session_id
from .obs_control import OBSController, find_latest_video_file
from .paths import ensure_dir


@dataclass(frozen=True)
class ReplayKeyframe:
    step: int
    time_sec: float
    x: float
    y: float
    z: float
    yaw: float
    pitch: float
    fov: float | None
    score: float | None
    image_path: str


@dataclass(frozen=True)
class ReplayTrajectory:
    trajectory_id: str
    source_json: Path
    scene_id: str
    angle_unit: str
    keyframes: list[ReplayKeyframe]

    @property
    def duration_sec(self) -> float:
        if not self.keyframes:
            return 0.0
        return max(frame.time_sec for frame in self.keyframes)


def load_replay_trajectory(
    json_path: str | Path,
    trajectory_id: str | None = None,
    trajectory_index: int = 1,
    angle_unit: str = "auto",
    keyframe_interval_sec: float = 0.2,
    unwrap_yaw: bool = True,
    reverse: bool = False,
) -> ReplayTrajectory:
    """Load one trajectory from a trajectory JSON file."""
    source = Path(json_path)
    with source.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    trajectories = payload.get("trajectories")
    if isinstance(trajectories, list):
        if trajectory_id:
            selected = next((item for item in trajectories if str(item.get("trajectory_id")) == trajectory_id), None)
            if selected is None:
                raise ValueError(f"Trajectory id not found: {trajectory_id}")
        else:
            if trajectory_index <= 0 or trajectory_index > len(trajectories):
                raise ValueError(f"trajectory_index must be between 1 and {len(trajectories)}.")
            selected = trajectories[trajectory_index - 1]
    elif isinstance(payload.get("keyframes"), list):
        selected = payload
    else:
        raise ValueError("Trajectory JSON must contain either trajectories[] or keyframes[].")

    detected_unit = _detect_angle_unit(payload, selected, angle_unit)
    keyframes = _parse_keyframes(selected.get("keyframes") or [], keyframe_interval_sec)
    if reverse:
        keyframes = _reversed_keyframes(keyframes)
    if unwrap_yaw:
        keyframes = _with_unwrapped_yaw(keyframes, detected_unit)
    if detected_unit == "degrees":
        keyframes = _with_radian_angles(keyframes)

    return ReplayTrajectory(
        trajectory_id=str(selected.get("trajectory_id") or trajectory_id or f"trajectory_{trajectory_index:03d}"),
        source_json=source,
        scene_id=str(payload.get("scene_id") or selected.get("scene_id") or ""),
        angle_unit="radians",
        keyframes=keyframes,
    )


def replay_trajectory_to_obs(
    config: AppConfig,
    trajectory: ReplayTrajectory,
    obs_password: str = "",
    output_dir: str | Path | None = None,
    session_id: str | None = None,
    countdown_sec: float = 3.0,
    settle_sec: float = 1.0,
    post_roll_sec: float = 1.0,
    speed: float = 1.0,
    duration_sec: float | None = None,
    record: bool = True,
    write_pose_log: bool = True,
) -> dict[str, Path | str]:
    """Replay a loaded trajectory through Lua set_pose controls and optionally record OBS."""
    if len(trajectory.keyframes) < 2:
        raise ValueError("A replay trajectory needs at least two keyframes.")
    if speed <= 0:
        raise ValueError("speed must be positive.")
    if countdown_sec < 0 or settle_sec < 0 or post_roll_sec < 0:
        raise ValueError("countdown/settle/post-roll values must be non-negative.")

    session = session_id or f"replay_{make_session_id()}_{_safe_name(trajectory.trajectory_id)}"
    base_output = ensure_dir(output_dir or (Path("data/videos/trajectories") / session))
    pose_log = config.pose_log_file.with_name(f"{config.pose_log_file.stem}_{session}.csv")
    metadata_csv = base_output / "replay_keyframes.csv"
    metadata_json = base_output / "replay_result.json"

    control = LuaControl(config)
    controller: OBSController | None = None
    record_dir = base_output / "raw"
    video_path: Path | None = None
    started_at = time.time()

    scaled = _scaled_keyframes(trajectory.keyframes, speed=speed, duration_sec=duration_sec)
    _write_keyframe_csv(metadata_csv, trajectory, scaled)

    try:
        if write_pose_log:
            control.write_start_control(session, pose_log, float(config.raw["lua_logger"]["default_interval_sec"]))
            control.wait_until_lua_logging_started(session, timeout_sec=3.0)

        first = scaled[0]
        _send_static_pose(control, session, first, segment_id=f"{trajectory.trajectory_id}_prepare")
        time.sleep(settle_sec)
        _raise_if_lua_rejected_pose(control)

        if countdown_sec > 0:
            for remaining in range(int(math.ceil(countdown_sec)), 0, -1):
                print(f"Starting replay in {remaining}...")
                time.sleep(1.0)

        if record:
            obs_cfg = config.raw["obs"]
            controller = OBSController(obs_cfg["host"], int(obs_cfg["port"]), obs_password or obs_cfg.get("password", ""))
            try:
                controller.set_record_directory(record_dir)
            except Exception:
                record_dir = config.obs_recording_output_dir
            started_at = time.time()
            controller.start_recording()
            time.sleep(0.25)

        _run_lua_trajectory(control, session, trajectory.trajectory_id, scaled)

        if post_roll_sec > 0:
            time.sleep(post_roll_sec)

        if controller is not None:
            output = controller.stop_recording()
            if output:
                video_path = Path(output)
            if video_path is None or not video_path.exists():
                video_path = find_latest_video_file(record_dir, before_time=started_at, supported_extensions=config.supported_video_extensions)
    finally:
        try:
            control.write_clear_pose_control(session)
        finally:
            if write_pose_log:
                time.sleep(0.25)
                control.write_stop_control(session)
                time.sleep(0.25)
                control.write_clear_pose_control(session)

    pose_copy: Path | None = None
    if pose_log.exists():
        pose_copy = base_output / "pose_log.csv"
        shutil.copy2(pose_log, pose_copy)

    result: dict[str, Path | str] = {
        "session_id": session,
        "output_dir": base_output,
        "metadata_csv": metadata_csv,
        "metadata_json": metadata_json,
        "source_json": trajectory.source_json,
    }
    if video_path is not None:
        result["video_path"] = video_path
    if pose_copy is not None:
        result["pose_log"] = pose_copy

    metadata_json.write_text(
        json.dumps(
            {
                "session_id": session,
                "trajectory_id": trajectory.trajectory_id,
                "scene_id": trajectory.scene_id,
                "source_json": str(trajectory.source_json),
                "video_path": str(video_path) if video_path else "",
                "pose_log": str(pose_copy) if pose_copy else "",
                "metadata_csv": str(metadata_csv),
                "duration_sec": scaled[-1].time_sec if scaled else 0.0,
                "replay_mode": "lua_play_trajectory",
                "recorded": bool(record),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return result


def _parse_keyframes(raw_keyframes: list[dict[str, Any]], keyframe_interval_sec: float) -> list[ReplayKeyframe]:
    if not raw_keyframes:
        raise ValueError("Trajectory has no keyframes.")
    frames: list[ReplayKeyframe] = []
    for index, item in enumerate(raw_keyframes):
        time_sec = _optional_float(item.get("time_sec"))
        if time_sec is None:
            time_sec = index * keyframe_interval_sec
        frames.append(
            ReplayKeyframe(
                step=int(item.get("step", index)),
                time_sec=float(time_sec),
                x=_required_float(item, "x"),
                y=_required_float(item, "y"),
                z=_required_float(item, "z"),
                yaw=_required_float(item, "yaw"),
                pitch=_required_float(item, "pitch"),
                fov=_optional_float(item.get("fov")),
                score=_optional_float(item.get("score")),
                image_path=str(item.get("image_path") or ""),
            )
        )
    frames.sort(key=lambda frame: (frame.time_sec, frame.step))
    return _ensure_strictly_increasing_time(frames, keyframe_interval_sec)


def _run_keyframe_segments(control: LuaControl, session: str, trajectory_id: str, frames: list[ReplayKeyframe]) -> None:
    for index in range(len(frames) - 1):
        start = frames[index]
        end = frames[index + 1]
        duration = max(0.001, end.time_sec - start.time_sec)
        segment_id = f"{trajectory_id}_k{index:04d}_{index + 1:04d}"
        control.write_set_pose_control(
            session,
            start.x,
            start.y,
            start.z,
            start.yaw,
            start.pitch,
            fov=start.fov,
            segment_id=segment_id,
            x_end=end.x,
            y_end=end.y,
            z_end=end.z,
            yaw_end=end.yaw,
            pitch_end=end.pitch,
            fov_end=end.fov,
            duration_sec=duration,
        )
        time.sleep(duration)
    _send_static_pose(control, session, frames[-1], segment_id=f"{trajectory_id}_final")


def _run_lua_trajectory(control: LuaControl, session: str, trajectory_id: str, frames: list[ReplayKeyframe]) -> None:
    control.write_play_trajectory_control(session, _lua_keyframes(frames), trajectory_id=trajectory_id)
    _wait_for_lua_trajectory(control, trajectory_id)
    _raise_if_lua_rejected_pose(control)
    time.sleep((frames[-1].time_sec if frames else 0.0) + 0.1)


def _send_static_pose(control: LuaControl, session: str, frame: ReplayKeyframe, segment_id: str) -> None:
    control.write_set_pose_control(
        session,
        frame.x,
        frame.y,
        frame.z,
        frame.yaw,
        frame.pitch,
        fov=frame.fov,
        segment_id=segment_id,
        x_end=frame.x,
        y_end=frame.y,
        z_end=frame.z,
        yaw_end=frame.yaw,
        pitch_end=frame.pitch,
        fov_end=frame.fov,
        duration_sec=0.0,
    )


def _lua_keyframes(frames: list[ReplayKeyframe]) -> list[dict[str, float | int | None]]:
    return [
        {
            "step": frame.step,
            "time_sec": frame.time_sec,
            "x": frame.x,
            "y": frame.y,
            "z": frame.z,
            "yaw": frame.yaw,
            "pitch": frame.pitch,
            "fov": frame.fov,
        }
        for frame in frames
    ]


def _wait_for_lua_trajectory(control: LuaControl, trajectory_id: str, timeout_sec: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status = control.read_status() or {}
        last_status = status
        if str(status.get("trajectory_id") or "") == trajectory_id and int(status.get("trajectory_frame_count") or 0) > 1:
            return
        error = str(status.get("last_error") or "")
        if "Enable FreeCam" in error or "play_trajectory requires" in error:
            return
        time.sleep(0.1)
    raise RuntimeError(
        "Lua did not acknowledge play_trajectory. Reload scripts in REFramework or restart the game so the smooth trajectory patch is active. "
        f"Last status: {last_status}"
    )


def _raise_if_lua_rejected_pose(control: LuaControl) -> None:
    status = control.read_status() or {}
    error = str(status.get("last_error") or "")
    if "Enable FreeCam" in error:
        raise RuntimeError("Lua rejected set_pose. Enable FreeCam in-game first, then run replay again.")
    if "play_trajectory requires" in error:
        raise RuntimeError("Lua rejected play_trajectory. Re-run patch-lua-logger so RE9FreeCam.lua has the smooth trajectory patch.")


def _detect_angle_unit(payload: dict[str, Any], selected: dict[str, Any], requested: str) -> str:
    if requested not in {"auto", "degrees", "radians"}:
        raise ValueError("angle_unit must be auto, degrees, or radians.")
    if requested != "auto":
        return requested
    coordinate_system = payload.get("coordinate_system") if isinstance(payload.get("coordinate_system"), dict) else {}
    yaw_unit = str(coordinate_system.get("yaw_unit") or coordinate_system.get("angle_unit") or "").lower()
    pitch_unit = str(coordinate_system.get("pitch_unit") or "").lower()
    if "degree" in yaw_unit or "degree" in pitch_unit:
        return "degrees"
    if "radian" in yaw_unit or "radian" in pitch_unit:
        return "radians"
    keyframes = selected.get("keyframes") or []
    values = [abs(_optional_float(item.get("yaw")) or 0.0) for item in keyframes]
    values += [abs(_optional_float(item.get("pitch")) or 0.0) for item in keyframes]
    return "degrees" if values and max(values) > (2.0 * math.pi + 0.5) else "radians"


def _with_unwrapped_yaw(frames: list[ReplayKeyframe], angle_unit: str) -> list[ReplayKeyframe]:
    if len(frames) < 2:
        return frames
    period = 360.0 if angle_unit == "degrees" else 2.0 * math.pi
    half = period / 2.0
    unwrapped = [frames[0].yaw]
    for frame in frames[1:]:
        previous = unwrapped[-1]
        delta = ((frame.yaw - previous + half) % period) - half
        unwrapped.append(previous + delta)
    return [
        ReplayKeyframe(frame.step, frame.time_sec, frame.x, frame.y, frame.z, yaw, frame.pitch, frame.fov, frame.score, frame.image_path)
        for frame, yaw in zip(frames, unwrapped)
    ]


def _with_radian_angles(frames: list[ReplayKeyframe]) -> list[ReplayKeyframe]:
    return [
        ReplayKeyframe(
            frame.step,
            frame.time_sec,
            frame.x,
            frame.y,
            frame.z,
            math.radians(frame.yaw),
            math.radians(frame.pitch),
            frame.fov,
            frame.score,
            frame.image_path,
        )
        for frame in frames
    ]


def _scaled_keyframes(frames: list[ReplayKeyframe], speed: float, duration_sec: float | None) -> list[ReplayKeyframe]:
    original_duration = max(0.001, frames[-1].time_sec - frames[0].time_sec)
    if duration_sec is not None:
        scale = duration_sec / original_duration
    else:
        scale = 1.0 / speed
    start_time = frames[0].time_sec
    return [
        ReplayKeyframe(
            frame.step,
            (frame.time_sec - start_time) * scale,
            frame.x,
            frame.y,
            frame.z,
            frame.yaw,
            frame.pitch,
            frame.fov,
            frame.score,
            frame.image_path,
        )
        for frame in frames
    ]


def _ensure_strictly_increasing_time(frames: list[ReplayKeyframe], interval: float) -> list[ReplayKeyframe]:
    fixed: list[ReplayKeyframe] = []
    previous = -float("inf")
    for index, frame in enumerate(frames):
        time_sec = frame.time_sec
        if time_sec <= previous:
            time_sec = previous + max(0.001, interval)
        fixed.append(
            ReplayKeyframe(frame.step, time_sec, frame.x, frame.y, frame.z, frame.yaw, frame.pitch, frame.fov, frame.score, frame.image_path)
        )
        previous = time_sec
    return fixed


def _reversed_keyframes(frames: list[ReplayKeyframe]) -> list[ReplayKeyframe]:
    if len(frames) < 2:
        return frames
    ordered = list(reversed(frames))
    original_times = [frame.time_sec for frame in frames]
    original_duration = max(original_times) - min(original_times)
    reversed_frames: list[ReplayKeyframe] = []
    for index, frame in enumerate(ordered):
        # Preserve original segment durations while resetting the reversed path to t=0.
        time_sec = original_duration - (frame.time_sec - min(original_times))
        reversed_frames.append(
            ReplayKeyframe(
                step=index,
                time_sec=time_sec,
                x=frame.x,
                y=frame.y,
                z=frame.z,
                yaw=frame.yaw,
                pitch=frame.pitch,
                fov=frame.fov,
                score=frame.score,
                image_path=frame.image_path,
            )
        )
    reversed_frames.sort(key=lambda frame: frame.time_sec)
    return [
        ReplayKeyframe(index, frame.time_sec, frame.x, frame.y, frame.z, frame.yaw, frame.pitch, frame.fov, frame.score, frame.image_path)
        for index, frame in enumerate(reversed_frames)
    ]


def _write_keyframe_csv(path: Path, trajectory: ReplayTrajectory, frames: list[ReplayKeyframe]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "trajectory_id",
                "scene_id",
                "step",
                "time_sec",
                "x",
                "y",
                "z",
                "yaw_rad",
                "pitch_rad",
                "fov",
                "score",
                "image_path",
            ],
        )
        writer.writeheader()
        for frame in frames:
            writer.writerow(
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "scene_id": trajectory.scene_id,
                    "step": frame.step,
                    "time_sec": frame.time_sec,
                    "x": frame.x,
                    "y": frame.y,
                    "z": frame.z,
                    "yaw_rad": frame.yaw,
                    "pitch_rad": frame.pitch,
                    "fov": "" if frame.fov is None else frame.fov,
                    "score": "" if frame.score is None else frame.score,
                    "image_path": frame.image_path,
                }
            )


def _required_float(item: dict[str, Any], key: str) -> float:
    value = _optional_float(item.get(key))
    if value is None:
        raise ValueError(f"Keyframe is missing numeric field: {key}")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_name(value: str) -> str:
    cleaned = []
    for char in value:
        cleaned.append(char if char.isalnum() or char in "._-" else "_")
    return "".join(cleaned).strip("._") or "trajectory"
