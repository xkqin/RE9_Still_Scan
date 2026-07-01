from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

from .paths import ensure_dir


def detect_inaccessible_points(
    samples_csv: str | Path,
    output_dir: str | Path | None = None,
    entropy_threshold: float = 3.0,
    std_threshold: float = 8.0,
    edge_density_threshold: float = 0.004,
    dark_ratio_threshold: float = 0.85,
    bright_ratio_threshold: float = 0.92,
) -> dict[str, Path]:
    """Detect bad stills and mark their whole camera point as inaccessible.

    This is image-based QA. It does not delete captured images, read game memory,
    or know the game's collision mesh. If any view at a point is suspicious, every
    row from that point is excluded from ``valid_samples.csv``.
    """
    samples_path = Path(samples_csv)
    if not samples_path.exists():
        raise FileNotFoundError(f"samples.csv not found: {samples_path}")
    out_dir = ensure_dir(output_dir or samples_path.parent / "qa")
    samples = pd.read_csv(samples_path)

    quality_rows: list[dict[str, Any]] = []
    for _, row in samples.iterrows():
        image_path = _resolve_image_path(samples_path, row.get("image_path", ""))
        metrics = _image_metrics(image_path)
        reasons = _bad_reasons(
            metrics,
            entropy_threshold=entropy_threshold,
            std_threshold=std_threshold,
            edge_density_threshold=edge_density_threshold,
            dark_ratio_threshold=dark_ratio_threshold,
            bright_ratio_threshold=bright_ratio_threshold,
        )
        result = row.to_dict()
        result.update(metrics)
        result["bad_still"] = bool(reasons)
        result["bad_reasons"] = ";".join(reasons)
        quality_rows.append(result)

    quality = pd.DataFrame(quality_rows)
    point_cols = [col for col in ["layer_id", "zone_id", "point_index", "x", "y", "z"] if col in quality.columns]
    if not point_cols:
        raise ValueError("samples.csv must contain point metadata such as point_index, x, y, and z.")

    bad_views = quality[quality["bad_still"] == True].copy()  # noqa: E712
    if bad_views.empty:
        inaccessible_points = pd.DataFrame(columns=point_cols + ["bad_view_count", "bad_patterns", "bad_reasons"])
        inaccessible_keys = set()
    else:
        inaccessible_points = (
            bad_views.groupby(point_cols, dropna=False)
            .agg(
                bad_view_count=("bad_still", "size"),
                bad_patterns=("pattern", lambda values: ",".join(sorted({str(v) for v in values}))),
                bad_reasons=("bad_reasons", _join_reasons),
            )
            .reset_index()
            .sort_values("bad_view_count", ascending=False)
        )
        inaccessible_keys = {_point_key(row, point_cols) for _, row in inaccessible_points.iterrows()}

    quality["inaccessible_point"] = [
        _point_key(row, point_cols) in inaccessible_keys for _, row in quality.iterrows()
    ]
    valid = quality[quality["inaccessible_point"] == False].copy()  # noqa: E712
    invalid = quality[quality["inaccessible_point"] == True].copy()  # noqa: E712

    quality_csv = out_dir / "still_quality.csv"
    bad_views_csv = out_dir / "bad_views.csv"
    inaccessible_points_csv = out_dir / "inaccessible_points.csv"
    invalid_samples_csv = out_dir / "invalid_samples_by_point.csv"
    valid_samples_csv = out_dir / "valid_samples.csv"

    quality.to_csv(quality_csv, index=False, quoting=csv.QUOTE_MINIMAL)
    bad_views.to_csv(bad_views_csv, index=False, quoting=csv.QUOTE_MINIMAL)
    inaccessible_points.to_csv(inaccessible_points_csv, index=False, quoting=csv.QUOTE_MINIMAL)
    invalid.to_csv(invalid_samples_csv, index=False, quoting=csv.QUOTE_MINIMAL)
    valid.to_csv(valid_samples_csv, index=False, quoting=csv.QUOTE_MINIMAL)

    return {
        "quality_csv": quality_csv,
        "bad_views_csv": bad_views_csv,
        "inaccessible_points_csv": inaccessible_points_csv,
        "invalid_samples_csv": invalid_samples_csv,
        "valid_samples_csv": valid_samples_csv,
    }


def _resolve_image_path(samples_path: Path, value: object) -> Path:
    image_path = Path(str(value))
    if image_path.is_absolute():
        return image_path
    candidate = samples_path.parent / image_path
    if candidate.exists():
        return candidate
    return image_path.resolve()


def _image_metrics(path: Path) -> dict[str, Any]:
    empty = {
        "image_exists": False,
        "image_width": "",
        "image_height": "",
        "gray_mean": "",
        "gray_std": "",
        "entropy": "",
        "edge_density": "",
        "dark_ratio": "",
        "bright_ratio": "",
    }
    if not path.exists():
        return empty
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return empty
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
    probabilities = hist / max(float(hist.sum()), 1.0)
    entropy = -sum(float(p) * math.log2(float(p)) for p in probabilities if p > 0)
    return {
        "image_exists": True,
        "image_width": int(image.shape[1]),
        "image_height": int(image.shape[0]),
        "gray_mean": round(float(gray.mean()), 6),
        "gray_std": round(float(gray.std()), 6),
        "entropy": round(float(entropy), 6),
        "edge_density": round(float(np.count_nonzero(edges)) / float(edges.size), 6),
        "dark_ratio": round(float(np.count_nonzero(gray < 12)) / float(gray.size), 6),
        "bright_ratio": round(float(np.count_nonzero(gray > 242)) / float(gray.size), 6),
    }


def _bad_reasons(
    metrics: dict[str, Any],
    entropy_threshold: float,
    std_threshold: float,
    edge_density_threshold: float,
    dark_ratio_threshold: float,
    bright_ratio_threshold: float,
) -> list[str]:
    if not metrics.get("image_exists"):
        return ["missing_or_unreadable"]
    reasons: list[str] = []
    if float(metrics["gray_std"]) < std_threshold:
        reasons.append("low_std")
    if float(metrics["entropy"]) < entropy_threshold:
        reasons.append("low_entropy")
    if float(metrics["edge_density"]) < edge_density_threshold:
        reasons.append("low_edge_density")
    if float(metrics["dark_ratio"]) > dark_ratio_threshold:
        reasons.append("mostly_dark")
    if float(metrics["bright_ratio"]) > bright_ratio_threshold:
        reasons.append("mostly_bright")
    return reasons


def _point_key(row: Any, point_cols: list[str]) -> tuple[str, ...]:
    return tuple(str(row[col]) for col in point_cols)


def _join_reasons(values: Any) -> str:
    reasons = sorted({part for value in values for part in str(value).split(";") if part})
    return ";".join(reasons)
