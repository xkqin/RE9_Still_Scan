param(
  [Parameter(Mandatory=$true)][string]$Backup,
  [string]$Config = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Python = ".\.venv\Scripts\python.exe"
if (!(Test-Path $Python)) { $Python = "python" }

if ($Config) {
  & $Python -m re9_pose_recorder.cli restore-lua --backup $Backup --config $Config
} else {
  & $Python -m re9_pose_recorder.cli restore-lua --backup $Backup
}
