from __future__ import annotations

import json
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .config import AppConfig
from .paths import PROJECT_ROOT, ensure_dir
from .still_scan import (
    StillSample,
    build_layered_still_scan_plan,
    build_still_scan_plan,
    load_still_layers,
    load_still_pose_plan,
    parse_float_list,
    run_layered_still_scan,
    run_still_pose_plan,
    run_still_scan,
)
from .trajectory_replay import load_replay_trajectory, replay_trajectory_to_obs
from .utils import timestamp_id


DEFAULT_TRAJECTORY_JSON = PROJECT_ROOT / "data" / "trajectories" / "scene_1.1" / "scene_1_1_trajectories.json"
DEFAULT_TRAJECTORY_OUTPUT_DIR = PROJECT_ROOT / "data" / "videos" / "trajectories" / "scene_1.1_low_to_high"


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
        pose_plan_config: Path | None = None,
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
        self.pose_plan_config = pose_plan_config
        self.stop_event = threading.Event()
        self.trajectory_stop_event = threading.Event()
        self.running = False
        self.qa_running = False
        self.trajectory_running = False
        self.output_dir: Path | None = None
        self.captured_count = 0
        self.trajectory_json = DEFAULT_TRAJECTORY_JSON
        self.trajectory_output_dir = DEFAULT_TRAJECTORY_OUTPUT_DIR
        self.current_trajectory_run_dir: Path | None = None
        self.trajectory_count = self._load_trajectory_count()

        if pose_plan_config is not None:
            planned = load_still_pose_plan(pose_plan_config, group_id=session_id or "scene_1_extra")
            layer_count = len({sample.layer_id for sample in planned})
            zone_count = len({sample.zone_id for sample in planned})
            plan_text = f"Plan: {layer_count} subscenes, {zone_count} sample kinds, {len(planned)} explicit images"
        elif layers_config is not None:
            layers = load_still_layers(layers_config)
            planned = build_layered_still_scan_plan(layers, points_x, points_z)
            layer_count = len({layer.layer_id for layer in layers})
            zone_count = len(layers)
            plan_text = f"Plan: {layer_count} layers, {zone_count} zones, 22 views per point, {len(planned)} images"
        else:
            heights = parse_float_list(y_values)
            planned = build_still_scan_plan(x_min, x_max, z_min, z_max, heights, points_x, points_z)
            layer_count = len(heights)
            zone_count = layer_count
            plan_text = f"Plan: {layer_count} layers, {zone_count} zones, 22 views per point, {len(planned)} images"
        self.total = len(planned) if max_samples is None else min(len(planned), max_samples)

        self.root = tk.Tk()
        self.root.title("RE9 Still Scan Progress")
        self.root.geometry("820x520")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", topmost)

        self.status_var = tk.StringVar(value="Ready")
        if max_samples is not None and self.total != len(planned):
            plan_text = f"{plan_text} (limited to {self.total})"
        self.plan_var = tk.StringVar(value=plan_text)
        self.pose_var = tk.StringVar(value="Current pose: -")
        self.file_var = tk.StringVar(value="Last image: -")
        self.output_var = tk.StringVar(value="Output: -")
        self.progress_var = tk.IntVar(value=0)
        self.trajectory_index_var = tk.IntVar(value=1)
        self.trajectory_var = tk.StringVar(
            value=f"Trajectory replay: scene_1.1 loaded {self.trajectory_count} paths, direction low -> high"
        )

        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=16, pady=14)

        capture_frame = ttk.LabelFrame(frame, text="Still image capture")
        capture_frame.pack(fill="x", pady=(0, 8))
        self.start_button = ttk.Button(capture_frame, text="Start Still Scan", command=self.start)
        self.start_button.pack(fill="x", padx=8, pady=4)
        self.stop_button = ttk.Button(capture_frame, text="Stop After Current Shot", command=self.stop, state="disabled")
        self.stop_button.pack(fill="x", padx=8, pady=4)
        self.qa_button = ttk.Button(
            capture_frame,
            text="Delete Broken Capture Images",
            command=self.run_bad_image_cleanup,
            state="disabled",
        )
        self.qa_button.pack(fill="x", padx=8, pady=4)

        trajectory_frame = ttk.LabelFrame(frame, text="Trajectory video capture")
        trajectory_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(trajectory_frame, textvariable=self.trajectory_var, wraplength=760).pack(anchor="w", padx=8, pady=(5, 2))
        ttk.Label(trajectory_frame, text=f"Output: {self.trajectory_output_dir}", wraplength=760).pack(anchor="w", padx=8, pady=(0, 5))
        trajectory_controls = ttk.Frame(trajectory_frame)
        trajectory_controls.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(trajectory_controls, text="Index").pack(side="left")
        self.trajectory_spinbox = ttk.Spinbox(
            trajectory_controls,
            from_=1,
            to=max(1, self.trajectory_count),
            textvariable=self.trajectory_index_var,
            width=6,
        )
        self.trajectory_spinbox.pack(side="left", padx=(6, 12))
        self.record_one_trajectory_button = ttk.Button(
            trajectory_controls,
            text="Record Selected Low -> High",
            command=self.record_selected_trajectory,
        )
        self.record_one_trajectory_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.record_all_trajectories_button = ttk.Button(
            trajectory_controls,
            text="Record All Low -> High",
            command=self.record_all_trajectories,
        )
        self.record_all_trajectories_button.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.stop_trajectory_button = ttk.Button(
            trajectory_frame,
            text="Stop After Current Trajectory",
            command=self.stop_after_current_trajectory,
            state="disabled",
        )
        self.stop_trajectory_button.pack(fill="x", padx=8, pady=(0, 8))

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
        if self.running or self.trajectory_running:
            return
        self.running = True
        self.stop_event.clear()
        self.start_button.configure(state="disabled")
        self._set_trajectory_buttons("disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("Starting in 5 seconds. Press Insert to close REFramework/FreeCam UI now.")
        self._countdown_start(5)

    def _countdown_start(self, seconds_left: int) -> None:
        if self.stop_event.is_set():
            self.running = False
            self.status_var.set("Start cancelled.")
            self.start_button.configure(state="normal")
            self._set_trajectory_buttons("normal")
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

    def run_bad_image_cleanup(self) -> None:
        if self.running or self.qa_running or self.trajectory_running:
            return
        if self.output_dir is None:
            messagebox.showerror("QA unavailable", "No scan output folder is available yet.")
            return
        samples_csv = self.output_dir / "samples.csv"
        if not samples_csv.exists():
            messagebox.showerror("QA unavailable", f"samples.csv was not found:\n{samples_csv}")
            return
        self.qa_running = True
        self.start_button.configure(state="disabled")
        self.qa_button.configure(state="disabled")
        self.status_var.set("Checking for broken capture images and deleting only obvious failures...")
        threading.Thread(target=self._qa_worker, args=(samples_csv,), daemon=True).start()

    def record_selected_trajectory(self) -> None:
        if self.running or self.trajectory_running:
            return
        if self.trajectory_count <= 0:
            messagebox.showerror("Trajectory unavailable", f"No trajectory JSON found:\n{self.trajectory_json}")
            return
        index = max(1, min(int(self.trajectory_index_var.get()), self.trajectory_count))
        if not self._confirm_trajectory_ready(f"Record trajectory {index:02d} low -> high?"):
            return
        self._start_trajectory_worker([index])

    def record_all_trajectories(self) -> None:
        if self.running or self.trajectory_running:
            return
        if self.trajectory_count <= 0:
            messagebox.showerror("Trajectory unavailable", f"No trajectory JSON found:\n{self.trajectory_json}")
            return
        if not self._confirm_trajectory_ready(f"Record all {self.trajectory_count} scene_1.1 trajectories low -> high?"):
            return
        self._start_trajectory_worker(list(range(1, self.trajectory_count + 1)))

    def stop_after_current_trajectory(self) -> None:
        self.trajectory_stop_event.set()
        self.status_var.set("Stopping after the current trajectory finishes...")
        self.stop_trajectory_button.configure(state="disabled")

    def on_close(self) -> None:
        if self.trajectory_running:
            should_stop = messagebox.askyesno("Trajectory active", "Stop after the current trajectory and close?")
            if should_stop:
                self.stop_after_current_trajectory()
            return
        if self.running:
            should_stop = messagebox.askyesno("Scan active", "Stop after the current shot and close?")
            if should_stop:
                self.stop()
            return
        self.root.destroy()

    def _worker(self) -> None:
        try:
            if self.pose_plan_config is not None:
                outputs = run_still_pose_plan(
                    self.config,
                    obs_password=self.obs_password,
                    pose_plan=self.pose_plan_config,
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
            elif self.layers_config is not None:
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

    def _start_trajectory_worker(self, indices: list[int]) -> None:
        self.trajectory_running = True
        self.trajectory_stop_event.clear()
        label = "all" if len(indices) > 1 else f"traj_{indices[0]:02d}"
        self.current_trajectory_run_dir = ensure_dir(self.trajectory_output_dir / f"run_{timestamp_id()}_{label}_low_to_high")
        self.progress_var.set(0)
        self.progress.configure(maximum=max(1, len(indices)))
        self.start_button.configure(state="disabled")
        self.qa_button.configure(state="disabled")
        self._set_trajectory_buttons("disabled")
        self.stop_trajectory_button.configure(state="normal")
        self.status_var.set("Starting trajectory recording. Hide REFramework UI before countdown finishes.")
        self.output_var.set(f"Output: {self.current_trajectory_run_dir}")
        threading.Thread(target=self._trajectory_worker, args=(indices,), daemon=True).start()

    def _trajectory_worker(self, indices: list[int]) -> None:
        completed = 0
        try:
            run_dir = self.current_trajectory_run_dir or ensure_dir(self.trajectory_output_dir / f"run_{timestamp_id()}_low_to_high")
            for position, trajectory_index in enumerate(indices, start=1):
                if self.trajectory_stop_event.is_set():
                    break
                trajectory = load_replay_trajectory(
                    self.trajectory_json,
                    trajectory_index=trajectory_index,
                    reverse=False,
                )
                session = f"scene_1_1_low_to_high_traj_{trajectory_index:02d}"
                output_dir = run_dir / f"traj_{trajectory_index:02d}"
                self.root.after(
                    0,
                    lambda pos=position, total=len(indices), idx=trajectory_index, traj=trajectory: self._set_trajectory_progress_text(
                        pos, total, idx, traj.trajectory_id
                    ),
                )
                replay_trajectory_to_obs(
                    self.config,
                    trajectory,
                    obs_password=self.obs_password,
                    output_dir=output_dir,
                    session_id=session,
                    countdown_sec=3.0,
                    settle_sec=1.0,
                    post_roll_sec=1.0,
                    speed=1.0,
                    duration_sec=None,
                    record=True,
                    write_pose_log=True,
                )
                completed += 1
                self.root.after(0, lambda value=completed: self.progress_var.set(value))

            status = f"Trajectory recording done. Recorded {completed}/{len(indices)} low -> high videos."
            if self.trajectory_stop_event.is_set():
                status = f"Trajectory recording stopped. Recorded {completed}/{len(indices)} videos."
            self.root.after(0, lambda: self._set_trajectory_done(status))
        except Exception as exc:
            error_log = ensure_dir(self.config.output_dir) / "trajectory_replay_gui_errors.log"
            with error_log.open("a", encoding="utf-8") as handle:
                handle.write(traceback.format_exc())
                handle.write("\n")
            self.root.after(0, lambda: self._set_trajectory_error(str(exc), error_log))

    def _qa_worker(self, samples_csv: Path) -> None:
        try:
            from .bad_still_detector import detect_inaccessible_points

            outputs = detect_inaccessible_points(
                samples_csv,
                output_dir=samples_csv.parent / "qa",
                delete_invalid_images=True,
            )
            self.root.after(0, lambda: self._set_qa_done(outputs))
        except Exception as exc:
            error_log = ensure_dir(self.config.output_dir) / "still_scan_errors.log"
            with error_log.open("a", encoding="utf-8") as handle:
                handle.write(traceback.format_exc())
                handle.write("\n")
            self.root.after(0, lambda: self._set_qa_error(str(exc), error_log))

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

    def _set_trajectory_progress_text(self, position: int, total: int, index: int, trajectory_id: str) -> None:
        self.status_var.set(f"Recording trajectory {position}/{total}: {trajectory_id} low -> high")
        self.pose_var.set(f"Current trajectory index: {index:02d}")
        self.file_var.set("Current mode: OBS video recording from trajectory JSON")
        base = self.current_trajectory_run_dir or self.trajectory_output_dir
        self.output_var.set(f"Output: {base / f'traj_{index:02d}'}")

    def _set_done(self, status: str, output_dir: Path) -> None:
        def apply() -> None:
            self.running = False
            self.status_var.set(status)
            self.output_var.set(f"Output: {output_dir}")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self._set_trajectory_buttons("normal")
            self._refresh_qa_button()

        self.root.after(0, apply)

    def _set_error(self, message: str, error_log: Path) -> None:
        self.running = False
        self.status_var.set(f"Failed: {message}")
        self.output_var.set(f"Error log: {error_log}")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._set_trajectory_buttons("normal")
        self._refresh_qa_button()
        messagebox.showerror("Still scan failed", message)

    def _set_trajectory_done(self, status: str) -> None:
        self.trajectory_running = False
        self.status_var.set(status)
        self.output_var.set(f"Output: {self.current_trajectory_run_dir or self.trajectory_output_dir}")
        self.start_button.configure(state="normal")
        self._set_trajectory_buttons("normal")
        self.stop_trajectory_button.configure(state="disabled")
        self._refresh_qa_button()

    def _set_trajectory_error(self, message: str, error_log: Path) -> None:
        self.trajectory_running = False
        self.status_var.set(f"Trajectory failed: {message}")
        self.output_var.set(f"Error log: {error_log}")
        self.start_button.configure(state="normal")
        self._set_trajectory_buttons("normal")
        self.stop_trajectory_button.configure(state="disabled")
        self._refresh_qa_button()
        messagebox.showerror("Trajectory replay failed", message)

    def _set_qa_done(self, outputs: dict[str, Path]) -> None:
        self.qa_running = False
        self.status_var.set("Capture QA done. Broken original images were deleted.")
        self.file_var.set(f"QA report: {outputs['inaccessible_points_csv']}")
        self.output_var.set(f"Deleted image log: {outputs['deleted_images_csv']}")
        self.start_button.configure(state="normal")
        self._refresh_qa_button()

    def _set_qa_error(self, message: str, error_log: Path) -> None:
        self.qa_running = False
        self.status_var.set(f"Bad-image QA failed: {message}")
        self.output_var.set(f"Error log: {error_log}")
        self.start_button.configure(state="normal")
        self._refresh_qa_button()
        messagebox.showerror("Bad-image QA failed", message)

    def _refresh_qa_button(self) -> None:
        samples_csv = self.output_dir / "samples.csv" if self.output_dir is not None else None
        state = "normal" if samples_csv is not None and samples_csv.exists() and not self.running else "disabled"
        self.qa_button.configure(state=state)

    def _set_trajectory_buttons(self, state: str) -> None:
        if self.trajectory_count <= 0:
            state = "disabled"
        self.record_one_trajectory_button.configure(state=state)
        self.record_all_trajectories_button.configure(state=state)
        self.trajectory_spinbox.configure(state=state)

    def _confirm_trajectory_ready(self, title: str) -> bool:
        return messagebox.askyesno(
            "Start trajectory video capture",
            (
                f"{title}\n\n"
                "Before clicking Yes:\n"
                "1. Open the game and enter the target scene.\n"
                "2. Enable FreeCam.\n"
                "3. Hide the REFramework/FreeCam UI with Insert.\n"
                "4. Keep OBS open and connected.\n\n"
                "The replay direction is low score -> high score."
            ),
        )

    def _load_trajectory_count(self) -> int:
        if not self.trajectory_json.exists():
            return 0
        try:
            with self.trajectory_json.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            trajectories = payload.get("trajectories")
            if isinstance(trajectories, list):
                return len(trajectories)
            if isinstance(payload.get("keyframes"), list):
                return 1
        except Exception:
            return 0
        return 0


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
    image_format: str = "jpg",
    image_width: int = 1920,
    image_height: int = 1080,
    image_quality: int = 100,
    max_samples: int | None = None,
    session_id: str | None = None,
    layers_config: Path | None = None,
    pose_plan_config: Path | None = None,
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
        pose_plan_config=pose_plan_config,
        topmost=topmost,
    ).run()

