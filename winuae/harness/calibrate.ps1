# Calibrate the emulated CPU against a real 68040, using SysInfo as the reference.
#
# Lesson learned the hard way: cpu_speed=real pins the machine to A500 timing
# (SysInfo read 68040 @ 7.09 MHz = 0.22x of an A4000/040/25) and it OVERRIDES
# both cpu_frequency and finegrain_cpu_speed - finegrain 169 and 6200 gave the
# identical 0.05x. The setting that actually works is cpu_speed=max plus
# cpu_throttle, which is the "CPU/chipset speed" slider as a percentage.
#
# Target: SysInfo's "A4000 68040 25MHz" line should read 1.33 (= a 68040/33).
#
# Usage: calibrate.ps1 -Throttle -69

param(
  [double]$Throttle = -69,
  [string]$Shot = "",
  [int]$WaitSec = 45
)

$cfg = "I:\GITHUB\Amiga_OpenTTD\winuae\otd-aga-cal.uae"
$src = Get-Content "I:\GITHUB\Amiga_OpenTTD\winuae\otd-aga.uae"
$out = @()
foreach ($line in $src) {
  if ($line -match '^cpu_speed=')           { continue }
  if ($line -match '^cpu_frequency=')       { continue }
  if ($line -match '^finegrain_cpu_speed=') { continue }
  if ($line -match '^cpu_throttle=')        { continue }
  if ($line -match '^config_description=') {
    $out += "config_description=Amiga_OpenTTD - AGA speed calibration (throttle=$Throttle)"
    continue
  }
  $out += $line
}
$out += "cpu_speed=max"
$out += ("cpu_throttle={0:F1}" -f $Throttle)
[System.IO.File]::WriteAllLines($cfg, $out, (New-Object System.Text.ASCIIEncoding))

& (Join-Path $PSScriptRoot "kill_ours.ps1") | Out-Null   # ONLY ours - never Stop-Process -Name winuae
Start-Sleep -Seconds 2
Start-Process -FilePath "I:\GITHUB\Amiga_OpenTTD\tools\winuae281\winuae.exe" -ArgumentList "-f",$cfg
Start-Sleep -Seconds 6
$p = Get-Process winuae -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -First 1
if (-not $p) { Write-Output "ERROR: winuae exited (bad config value?)"; exit 1 }
Add-Type @"
using System; using System.Runtime.InteropServices;
public class Cal { [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x,int y,int w,int t, uint f); }
"@
[void][Cal]::SetWindowPos($p.MainWindowHandle,[IntPtr]::Zero,60,60,0,0,0x0001 -bor 0x0010 -bor 0x0040)

if ($Shot -eq "") { $Shot = "I:\GITHUB\Amiga_OpenTTD\winuae\shots\cal_thr$Throttle.png" }
Start-Sleep -Seconds $WaitSec
& I:\GITHUB\Amiga_OpenTTD\winuae\harness\capture_pw.ps1 -Out $Shot
Write-Output "throttle=$Throttle -> $Shot"
