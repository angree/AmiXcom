# Start WinUAE on one of the OpenXcom configs and wait for the game's log to
# appear, so an agent-driven test run needs no human at the emulator.
#
# WinUAE MUST be started as "winuae.exe -f <config>" with use_gui=no in the
# config: anything else opens the configuration window and sits there waiting
# for a person. That is the single most common way to waste a test cycle.
#
# Usage:
#   run-oxc.ps1                      # AGA config, 90 s for a log line
#   run-oxc.ps1 -Config oxc-rtg.uae -TimeoutSec 180
param(
  [string]$Config = "I:\GITHUB\Amiga_OpenXCOM\winuae\oxc-aga.uae",
  [int]$TimeoutSec = 90,
  [switch]$KeepRunning
)

$exe = "I:\GITHUB\Amiga_OpenTTD\tools\winuae281\winuae-oxc.exe"
$wd  = "I:\GITHUB\Amiga_OpenTTD\tools\winuae281"
# The runtime (Work:, the hardfile, the Kickstart) lives on the SSD, not in the
# repository on the network drive - see the note in oxc-aga.uae.
$log = "C:\temp\amiga_oxcom\work\oxc.log"

if (-not (Test-Path $exe)) { Write-Output "ERROR: WinUAE not found at $exe"; exit 1 }
if (-not (Test-Path $Config)) { Write-Output "ERROR: config not found: $Config"; exit 1 }

& (Join-Path $PSScriptRoot "kill_ours.ps1") | Out-Null   # ONLY ours - never Stop-Process -Name winuae
Start-Sleep 3
Remove-Item $log -ErrorAction SilentlyContinue

# -log turns on winuaelog.txt in the WinUAE directory. Without it the only
# trace of a failed boot is the boot log, which stops before emulation starts -
# so a HALT or a Guru leaves nothing at all to read.
$uaelog = Join-Path $wd "winuaelog.txt"
Remove-Item $uaelog -ErrorAction SilentlyContinue
# Plain launch (raw input on). Synthetic mouse input reaches the emulator only
# as RELATIVE deltas while it has the mouse trapped - that is what
# click_ours.ps1 does, and it verifies every click against the game's log.
# (-nodirectinput -norawinput was tried for absolute SetCursorPos driving:
# WinUAE 2.8.1 then ignored synthetic moves entirely.)
# WinUAE 2.8.1 ignores win32.posx/posy in the config and opens the emulation
# window where winuae.ini remembers it (MainPosX/MainPosY). With gfx_api=0
# (DirectDraw) a window created on a SECONDARY monitor comes up black - for the
# user and for every capture - and stays black. That happened after the user
# dragged a running instance to their second monitor: every launch after it was
# a black window with a perfectly healthy game inside. So the remembered
# position is forced back onto the primary monitor before each start. Only new
# windows are affected; nothing running is touched.
$ini = Join-Path $wd "winuae.ini"
if (Test-Path $ini) {
  $txt = Get-Content $ini -Raw
  $txt = [regex]::Replace($txt, '(?m)^MainPosX=.*$', 'MainPosX=100')
  $txt = [regex]::Replace($txt, '(?m)^MainPosY=.*$', 'MainPosY=60')
  Set-Content $ini $txt -Encoding ASCII -NoNewline
}
Start-Process -FilePath $exe -ArgumentList '-log', '-f', $Config -WorkingDirectory $wd

$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
  if (Test-Path $log) {
    Start-Sleep 2
    Write-Output "--- oxc.log ---"
    Get-Content $log
    if (-not $KeepRunning) {
      & (Join-Path $PSScriptRoot "kill_ours.ps1") | Out-Null   # ONLY ours - never Stop-Process -Name winuae
    }
    exit 0
  }
  Start-Sleep 3
}

Write-Output "TIMEOUT: no $log after $TimeoutSec s"
if (Test-Path $uaelog) {
  Write-Output "--- winuaelog.txt (last 60 lines) ---"
  Get-Content $uaelog -Tail 60
}
if (-not $KeepRunning) {
  & (Join-Path $PSScriptRoot "kill_ours.ps1") | Out-Null   # ONLY ours - never Stop-Process -Name winuae
}
exit 1
