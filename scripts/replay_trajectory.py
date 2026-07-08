from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    python = project_root / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    args = [
        str(python),
        "-m",
        "re9_pose_recorder.cli",
        "replay-trajectory",
        "--obs-password",
        "123456",
    ]
    args.extend(sys.argv[1:])
    return subprocess.call(args, cwd=project_root)


if __name__ == "__main__":
    raise SystemExit(main())
