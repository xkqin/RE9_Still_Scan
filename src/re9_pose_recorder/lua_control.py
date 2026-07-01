from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from .config import AppConfig
from .paths import ensure_dir
from .utils import timestamp_id


def make_session_id() -> str:
    return timestamp_id()


class LuaControl:
    """File-based control channel for the REFramework Lua logger."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.control_file = config.control_file
        self.status_file = config.status_file

    def write_start_control(self, session_id: str, pose_log_file: str | Path, interval_sec: float) -> Path:
        payload = {
            "command": "start",
            "command_id": f"start:{session_id}:{time.time():.6f}",
            "session_id": session_id,
            "pose_log_file": str(Path(pose_log_file).as_posix()),
            "interval_sec": float(interval_sec),
        }
        return self._write_control(payload)

    def write_stop_control(self, session_id: str) -> Path:
        return self._write_control({"command": "stop", "command_id": f"stop:{session_id}:{time.time():.6f}", "session_id": session_id})

    def write_set_pose_control(
        self,
        session_id: str,
        x: float,
        y: float,
        z: float,
        yaw: float,
        pitch: float,
        fov: float | None = None,
        segment_id: str = "",
        yaw_end: float | None = None,
        duration_sec: float | None = None,
    ) -> Path:
        payload: dict[str, Any] = {
            "command": "set_pose",
            "command_id": f"set_pose:{session_id}:{segment_id}:{time.time():.6f}",
            "session_id": session_id,
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "yaw": float(yaw),
            "pitch": float(pitch),
            "segment_id": segment_id,
        }
        if yaw_end is not None:
            payload["yaw_end"] = float(yaw_end)
        if duration_sec is not None:
            payload["duration_sec"] = float(duration_sec)
        if fov is not None:
            payload["fov"] = float(fov)
        return self._write_control(payload)

    def write_clear_pose_control(self, session_id: str) -> Path:
        return self._write_control(
            {"command": "clear_pose", "command_id": f"clear_pose:{session_id}:{time.time():.6f}", "session_id": session_id}
        )

    def read_status(self) -> dict[str, Any] | None:
        if not self.status_file.exists():
            return None
        try:
            with self.status_file.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None

    def wait_until_lua_logging_started(self, session_id: str, timeout_sec: float = 5) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            status = self.read_status()
            if status and status.get("session_id") == session_id and status.get("logging") is True:
                return True
            time.sleep(0.25)
        return False

    def wait_until_lua_logging_stopped(self, session_id: str, timeout_sec: float = 5) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            status = self.read_status()
            if status and status.get("session_id") == session_id and status.get("logging") is False:
                return True
            time.sleep(0.25)
        return False

    def copy_pose_log_to_outputs(self, pose_log_file: str | Path, output_dir: str | Path) -> Path | None:
        source = Path(pose_log_file)
        if not source.exists():
            return None
        out_dir = ensure_dir(output_dir)
        destination = out_dir / "pose_log.csv"
        shutil.copy2(source, destination)
        return destination

    def _write_control(self, payload: dict[str, Any]) -> Path:
        self.control_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.control_file.with_suffix(self.control_file.suffix + ".tmp")
        last_error: OSError | None = None
        for attempt in range(20):
            try:
                with tmp_path.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)
                os.replace(tmp_path, self.control_file)
                return self.control_file
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05 + attempt * 0.02)
            except OSError as exc:
                last_error = exc
                time.sleep(0.05 + attempt * 0.02)
        if last_error is not None:
            raise last_error
        return self.control_file


def write_start_control(
    config: AppConfig, session_id: str, pose_log_file: str | Path, interval_sec: float
) -> Path:
    return LuaControl(config).write_start_control(session_id, pose_log_file, interval_sec)


def write_stop_control(config: AppConfig, session_id: str) -> Path:
    return LuaControl(config).write_stop_control(session_id)


def read_status(config: AppConfig) -> dict[str, Any] | None:
    return LuaControl(config).read_status()


def wait_until_lua_logging_started(config: AppConfig, session_id: str, timeout_sec: float = 5) -> bool:
    return LuaControl(config).wait_until_lua_logging_started(session_id, timeout_sec)


def wait_until_lua_logging_stopped(config: AppConfig, session_id: str, timeout_sec: float = 5) -> bool:
    return LuaControl(config).wait_until_lua_logging_stopped(session_id, timeout_sec)


def copy_pose_log_to_outputs(pose_log_file: str | Path, output_dir: str | Path) -> Path | None:
    source = Path(pose_log_file)
    if not source.exists():
        return None
    out_dir = ensure_dir(output_dir)
    destination = out_dir / "pose_log.csv"
    shutil.copy2(source, destination)
    return destination
