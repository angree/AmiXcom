# Drive the game from INSIDE the emulated machine: write a script to
# Work:autoinput.txt and wait until sdlmini has consumed (deleted) it.
#
# This touches nothing on the host - no mouse, no keyboard, no focus. It is
# the only permitted way to click in the game under test (see CLAUDE.md for
# why the host-input scripts were retired).
#
# Usage:
#   autoinput.ps1 "click 100 100" "wait 1000" "click 100 25"
#   autoinput.ps1 -File steps.txt
# Commands: move X Y | click X Y | rclick X Y | key NAME | wait MS | quit
[CmdletBinding(PositionalBinding = $false)]
param(
  [string]$File = "",
  [string]$Target = "C:\temp\amiga_oxcom\work\autoinput.txt",
  [int]$TimeoutSec = 60,
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$Commands
)
if ($File -ne "") { $Commands = Get-Content $File }
if (-not $Commands -or $Commands.Count -eq 0) { Write-Output "nothing to send"; exit 1 }
if (Test-Path $Target) { Write-Output "ERROR: previous script not consumed yet ($Target exists)"; exit 1 }

# write atomically: temp file then rename, so the guest never reads a partial file
$tmp = "$Target.part"
($Commands -join "`n") + "`n" | Set-Content -Path $tmp -Encoding Ascii -NoNewline
Move-Item -Path $tmp -Destination $Target -Force

$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
  if (-not (Test-Path $Target)) { Write-Output "consumed: $($Commands -join ' ; ')"; exit 0 }
  Start-Sleep -Milliseconds 300
}
Write-Output "TIMEOUT: the game did not consume $Target in $TimeoutSec s (is it running the main loop?)"
exit 1
