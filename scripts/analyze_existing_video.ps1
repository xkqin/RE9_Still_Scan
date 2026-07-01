param(
  [Parameter(Mandatory=$true)][string]$Video,
  [Parameter(Mandatory=$true)][string]$PoseLog,
  [double]$Fps = 2.0,
  [string]$Device = "auto",
  [int]$TopK = 50,
  [string]$Config = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Python = ".\.venv\Scripts\python.exe"
if (!(Test-Path $Python)) { $Python = "python" }

$argsList = @("-m", "re9_pose_recorder.cli", "analyze-video", "--video", $Video, "--pose-log", $PoseLog, "--fps", "$Fps", "--device", $Device, "--top-k", "$TopK")
if ($Config) { $argsList += @("--config", $Config) }
& $Python @argsList
