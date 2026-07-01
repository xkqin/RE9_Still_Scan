param(
  [string]$ObsPassword = "",
  [double]$LiveScoreInterval = 2.0,
  [double]$LiveSummaryWindow = 10.0,
  [double]$SegmentWindow = 5.0,
  [string]$Device = "auto",
  [switch]$NoLiveScore,
  [switch]$NoTopmost,
  [string]$Config = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Python = ".\.venv\Scripts\python.exe"
if (!(Test-Path $Python)) { $Python = "python" }

$argsList = @("-m", "re9_pose_recorder.cli", "one-click-record", "--obs-password", $ObsPassword, "--live-score-interval", "$LiveScoreInterval", "--live-summary-window", "$LiveSummaryWindow", "--segment-window", "$SegmentWindow", "--device", $Device)
if ($NoLiveScore) { $argsList += "--no-live-score" }
if ($NoTopmost) { $argsList += "--no-topmost" }
if ($Config) { $argsList += @("--config", $Config) }
& $Python @argsList
