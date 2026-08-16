# Capture the WinUAE window via PrintWindow (no focus steal, works when occluded).
# Requires WinUAE running with gfx_api=0 (DirectDraw) or PrintWindow returns black.
# Usage: capture_pw.ps1 -Out shot.png [-ProcName winuae]
param(
  [string]$Out = "shot.png",
  [string]$ProcName = "winuae"
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class PWCap {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
"@
Add-Type -AssemblyName System.Drawing

$p = Get-Process -Name $ProcName -ErrorAction SilentlyContinue |
     Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero } |
     Select-Object -First 1
if (-not $p) { Write-Output "ERROR: no window for process '$ProcName'"; exit 1 }
$h = $p.MainWindowHandle

$r = New-Object PWCap+RECT
[void][PWCap]::GetWindowRect($h, [ref]$r)
$w = $r.Right - $r.Left
$ht = $r.Bottom - $r.Top
if ($w -le 0 -or $ht -le 0) { Write-Output "ERROR: bad rect $w x $ht"; exit 1 }

$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [PWCap]::PrintWindow($h, $hdc, 2)   # 2 = PW_RENDERFULLCONTENT
$g.ReleaseHdc($hdc)
if (-not $ok) { Write-Output "WARN: PrintWindow returned false" }
$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "OK saved $Out (${w}x${ht})"
