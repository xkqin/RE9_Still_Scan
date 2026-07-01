param(
  [string]$ObsPassword = "",
  [double]$Fps = 2.0,
  [string]$Device = "auto",
  [int]$TopK = 50,
  [switch]$AutoSetupLaion,
  [string]$Config = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Python = ".\.venv\Scripts\python.exe"
if (!(Test-Path $Python)) { $Python = "python" }

$argsList = @("-m", "re9_pose_recorder.cli", "record-and-score", "--obs-password", $ObsPassword, "--fps", "$Fps", "--device", $Device, "--top-k", "$TopK")
if ($AutoSetupLaion) { $argsList += "--auto-setup-laion" }
if ($Config) { $argsList += @("--config", $Config) }
& $Python @argsList
