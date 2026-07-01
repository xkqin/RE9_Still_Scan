from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .paths import DEFAULT_CONFIG_PATH, resolve_project_path


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]
    path: Path

    @property
    def lua_path(self) -> Path:
        return Path(self.raw["game"]["lua_path"]).expanduser()

    @property
    def control_file(self) -> Path:
        return Path(self.raw["lua_logger"]["control_file"]).expanduser()

    @property
    def status_file(self) -> Path:
        return Path(self.raw["lua_logger"]["status_file"]).expanduser()

    @property
    def pose_log_file(self) -> Path:
        return Path(self.raw["lua_logger"]["pose_log_file"]).expanduser()

    @property
    def lua_backup_dir(self) -> Path:
        return resolve_project_path(self.raw["lua_logger"]["backup_dir"])

    @property
    def output_dir(self) -> Path:
        return resolve_project_path(self.raw["report"]["output_dir"])

    @property
    def obs_recording_output_dir(self) -> Path:
        return resolve_project_path(self.raw["obs"].get("recording_output_dir") or "data/videos")

    @property
    def laion_repo_dir(self) -> Path:
        return resolve_project_path(self.raw["laion"]["repo_dir"])

    @property
    def supported_video_extensions(self) -> set[str]:
        return {item.lower() for item in self.raw["video"]["supported_video_extensions"]}


def load_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH
    if not path.is_absolute():
        path = resolve_project_path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return AppConfig(raw=raw, path=path)
