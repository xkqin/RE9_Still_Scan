param(
  [string]$Config = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Python = ".\.venv\Scripts\python.exe"
if (!(Test-Path $Python)) { $Python = "python" }

if ($Config) {
  & $Python -m re9_pose_recorder.cli setup-laion --config $Config
} else {
  & $Python -m re9_pose_recorder.cli setup-laion
}
