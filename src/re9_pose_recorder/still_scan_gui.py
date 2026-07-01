from __future__ import annotations

import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .config import AppConfig
from .paths import ensure_dir
from .still_scan import (
    StillSample,
    build_layered_still_scan_plan,
    build_still_scan_plan,
    load_still_layers,
    parse_float_list,
    run_layered_still_scan,
    run_still_scan,
)


class StillScanApp:
    """Small progress window for OBS still-image grid scans."""

    def __init__(
        self,
        config: AppConfig,
        obs_password: str,
        x_min: float,
        x_max: float,
        z_min: float,
        z_max: float,
        y_values: str,
        points_x: int,
        points_z: int,
        settle_seconds: float,
        source_name: str | None,
        image_format: str,
        image_width: int,
        image_height: int,
        image_quality: int,
        max_samples: int | None,
        session_id: str | None,
        layers_config: Path | None = None,
        topmost: bool = True,
    ) -> None:
        self.config = config
        self.obs_password = obs_password
        self.x_min = x_min
        self.x_max = x_max
        self.z_min = z_min
        self.z_max = z_max
        self.y_values = y_values
        self.points_x = points_x
        self.points_z = points_z
        self.settle_seconds = settle_seconds
        self.source_name = source_name
        self.image_format = image_format
        self.image_width = image_width
        self.image_height = image_height
        self.image_quality = image_quality
        self.max_samples = max_samples
        self.session_id = session_id
        self.layers_config = layers_config
        self.stop_event = threading.Event()
        self.running = False
        self.output_dir: Path | None = None
        self.captured_count = 0

        if layers_config is not None:
            layers = load_still_layers(layers_config)
            planned = build_layered_still_scan_plan(layers, points_x, points_z)
            layer_count = len({layer.layer_id for layer in layers})
            zone_count = len(layers)
        else:
            heights = parse_float_list(y_values)
            planned = build_still_scan_plan(x_min, x_max, z_min, z_max, heights, points_x, points_z)
            layer_count = len(heights)
            zone_count = layer_count
        self.total = len(planned) if max_samples is None else min(len(planned), max_samples)

        self.root = tk.Tk()
        self.root.title("RE9 Still Scan Progress")
        self.root.geometry("760x360")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", topmost)

        self.status_var = tk.StringVar(value="Ready")
        self.plan_var = tk.StringVar(
            value=f"Plan: {layer_count} layers, {zone_count} zones, 22 views per point, {self.total} images"
        )
        self.pose_var = tk.StringVar(value="Current pose: -")
        self.file_var = tk.StringVar(value="Last image: -")
        self.output_var = tk.StringVar(value="Output: -")
        self.progress_var = tk.IntVar(value=0)

        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=16, pady=14)

        self.start_button = ttk.Button(frame, text="Start Still Scan", command=self.start)
        self.start_button.pack(fill="x", pady=4)
        self.stop_button = ttk.Button(frame, text="Stop After Current Shot", command=self.stop, state="disabled")
        self.stop_button.pack(fill="x", pady=4)

        ttk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 11, "bold"), wraplength=720).pack(anchor="w", pady=5)
        ttk.Label(frame, textvariable=self.plan_var, wraplength=720).pack(anchor="w", pady=5)
        self.progress = ttk.Progressbar(frame, maximum=max(1, self.total), variable=self.progress_var)
        self.progress.pack(fill="x", pady=8)
        ttk.Label(frame, textvariable=self.pose_var, wraplength=720).pack(anchor="w", pady=5)
        ttk.Label(frame, textvariable=self.file_var, wraplength=720).pack(anchor="w", pady=5)
        ttk.Label(frame, textvariable=self.output_var, wraplength=720).pack(anchor="w", pady=5)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def run(self) -> None:
        self.root.mainloop()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("Starting in 5 seconds. Press Insert to close REFramework/FreeCam UI now.")
        self._countdown_start(5)

    def _countdown_start(self, seconds_left: int) -> None:
        if self.stop_event.is_set():
            self.running = False
            self.status_var.set("Start cancelled.")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            return
        if seconds_left <= 0:
            self.status_var.set("Connecting to OBS and starting still scan...")
            threading.Thread(target=self._worker, daemon=True).start()
            return
        self.status_var.set(
            f"Starting in {seconds_left}s. Close REFramework/FreeCam UI before capture starts."
        )
        self.root.after(1000, lambda: self._countdown_start(seconds_left - 1))

    def stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("Stopping after the current shot finishes...")
        self.stop_button.configure(state="disabled")

    def on_close(self) -> None:
        if self.running:
            should_stop = messagebox.askyesno("Scan active", "Stop after the current shot and close?")
            if should_stop:
                self.stop()
            return
        self.root.destroy()

    def _worker(self) -> None:
        try:
            if self.layers_config is not None:
                outputs = run_layered_still_scan(
                    self.config,
                    obs_password=self.obs_password,
                    layers=load_still_layers(self.layers_config),
                    points_x=self.points_x,
                    points_z=self.points_z,
                    settle_seconds=self.settle_seconds,
                    source_name=self.source_name,
                    image_format=self.image_format,
                    image_width=self.image_width,
                    image_height=self.image_height,
                    image_quality=self.image_quality,
                    session_id=self.session_id,
                    max_samples=self.max_samples,
                    progress_callback=self._progress,
                    stop_event=self.stop_event,
                )
            else:
                heights = parse_float_list(self.y_values)
                outputs = run_still_scan(
                    self.config,
                    obs_password=self.obs_password,
                    x_min=self.x_min,
                    x_max=self.x_max,
                    z_min=self.z_min,
                    z_max=self.z_max,
                    y_values=heights,
                    points_x=self.points_x,
                    points_z=self.points_z,
                    settle_seconds=self.settle_seconds,
                    source_name=self.source_name,
                    image_format=self.image_format,
                    image_width=self.image_width,
                    image_height=self.image_height,
                    image_quality=self.image_quality,
                    session_id=self.session_id,
                    max_samples=self.max_samples,
                    progress_callback=self._progress,
                    stop_event=self.stop_event,
                )
            self.output_dir = outputs["output_dir"]
            done = self.captured_count
            status = "Stopped." if self.stop_event.is_set() and done < self.total else "Done."
            self._set_done(status, outputs["output_dir"])
        except Exception as exc:
            error_log = ensure_dir(self.config.output_dir) / "still_scan_errors.log"
            with error_log.open("a", encoding="utf-8") as handle:
                handle.write(traceback.format_exc())
                handle.write("\n")
            self.root.after(0, lambda: self._set_error(str(exc), error_log))

    def _progress(self, sample: StillSample, total: int, image_path: Path) -> None:
        self.captured_count = sample.sample_index

        def apply() -> None:
            self.progress.configure(maximum=max(1, total))
            self.progress_var.set(sample.sample_index)
            self.status_var.set(f"Captured {sample.sample_index}/{total}")
            self.pose_var.set(
                f"Current pose: {sample.layer_id}/{sample.zone_id}, x={sample.x:.2f}, y={sample.y:.2f}, z={sample.z:.2f}, "
                f"yaw={sample.yaw_deg:.1f}, pitch={sample.pitch_deg:.1f}, {sample.pattern}"
            )
            self.file_var.set(f"Last image: {image_path}")
            self.output_var.set(f"Output: {image_path.parent.parent}")

        self.root.after(0, apply)

    def _set_done(self, status: str, output_dir: Path) -> None:
        def apply() -> None:
            self.running = False
            self.status_var.set(status)
            self.output_var.set(f"Output: {output_dir}")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

        self.root.after(0, apply)

    def _set_error(self, message: str, error_log: Path) -> None:
        self.running = False
        self.status_var.set(f"Failed: {message}")
        self.output_var.set(f"Error log: {error_log}")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        messagebox.showerror("Still scan failed", message)


def run_still_scan_gui(
    config: AppConfig,
    obs_password: str,
    x_min: float = 22.63,
    x_max: float = 153.83,
    z_min: float = -6.16,
    z_max: float = 11.49,
    y_values: str = "9.41,10.10,10.78",
    points_x: int = 5,
    points_z: int = 3,
    settle_seconds: float = 0.35,
    source_name: str | None = None,
    image_format: str = "png",
    image_width: int = 0,
    image_height: int = 0,
    image_quality: int = 100,
    max_samples: int | None = None,
    session_id: str | None = None,
    layers_config: Path | None = None,
    topmost: bool = True,
) -> None:
    StillScanApp(
        config,
        obs_password=obs_password,
        x_min=x_min,
        x_max=x_max,
        z_min=z_min,
        z_max=z_max,
        y_values=y_values,
        points_x=points_x,
        points_z=points_z,
        settle_seconds=settle_seconds,
        source_name=source_name,
        image_format=image_format,
        image_width=image_width,
        image_height=image_height,
        image_quality=image_quality,
        max_samples=max_samples,
        session_id=session_id,
        layers_config=layers_config,
        topmost=topmost,
    ).run()

