# Capture a numbered series of WinUAE window screenshots.
# Usage: capture_series.ps1 -Prefix I:\...\shots\run1 -Count 20 -IntervalSec 8
param(
  [string]$Prefix = "series",
  [int]$Count = 20,
  [int]$IntervalSec = 8,
  [string]$ProcName = "winuae1"
)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
for ($i = 1; $i -le $Count; $i++) {
  $out = "{0}_{1:d2}.png" -f $Prefix, $i
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $here 'capture.ps1') -Out $out -ProcName $ProcName | Out-Null
  Write-Output ("shot {0}" -f $out)
  if ($i -lt $Count) { Start-Sleep -Seconds $IntervalSec }
}
