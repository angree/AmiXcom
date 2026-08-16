# Full backup zip of the repository (the author's convention, one zip per step):
#   I:\GITHUB\Amiga_OpenXCOM_backup_<yyyy-MM-dd>_<HHmm>_<label>.zip
# Contents: the whole repo tree (minus .git and winuae\work), plus a copy of the
# live Work: options.cfg and the current openxcom-aga binary, plus BACKUP-INFO.txt
# with the note passed on the command line.
#
# Usage: backup.ps1 -Label "glob-cache" -Note "one line describing the state"
param(
  [Parameter(Mandatory=$true)][string]$Label,
  [string]$Note = ""
)
$repo = "I:\GITHUB\Amiga_OpenXCOM"
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$zip = "I:\GITHUB\Amiga_OpenXCOM_backup_${stamp}_${Label}.zip"
$stage = Join-Path $env:TEMP ("oxc_backup_" + $stamp)
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path "$stage\Amiga_OpenXCOM" | Out-Null
robocopy $repo "$stage\Amiga_OpenXCOM" /E /XD ".git" "work" "__pycache__" /NFL /NDL /NJH /NJS | Out-Null
Copy-Item "C:\temp\amiga_oxcom\work\user\options.cfg" "$stage\Amiga_OpenXCOM\winuae\options.cfg.tftd-reference" -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$stage\Amiga_OpenXCOM\bin" | Out-Null
Copy-Item "C:\temp\amiga_oxcom\work\openxcom-aga" "$stage\Amiga_OpenXCOM\bin\openxcom-aga" -Force -ErrorAction SilentlyContinue
"Backup: Amiga OpenXCOM, $stamp - $Label`n$Note`nSzczegoly: LEFTOFF.md, PROGRESS.md." | Set-Content "$stage\Amiga_OpenXCOM\BACKUP-INFO.txt" -Encoding UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $false)
Remove-Item $stage -Recurse -Force
Write-Output ("OK " + $zip + " " + [math]::Round((Get-Item $zip).Length / 1MB, 1) + " MB")
