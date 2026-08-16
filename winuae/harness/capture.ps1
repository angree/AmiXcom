# Capture the WinUAE emulation window to a PNG via host-side CopyFromScreen.
# Works regardless of WinUAE version; grabs the real composited pixels of the
# windowed DirectDraw surface. Usage: capture.ps1 -Out shot.png [-ProcName winuae1]
param(
  [string]$Out = "shot.png",
  [string]$ProcName = "winuae1",
  [switch]$Foreground
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinCap {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@
Add-Type -AssemblyName System.Drawing

$p = Get-Process -Name $ProcName -ErrorAction SilentlyContinue |
     Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero } |
     Select-Object -First 1
if (-not $p) { Write-Output "ERROR: no window for process '$ProcName'"; exit 1 }
$h = $p.MainWindowHandle

if ($Foreground) { [void][WinCap]::SetForegroundWindow($h); Start-Sleep -Milliseconds 300 }

$r = New-Object WinCap+RECT
[void][WinCap]::GetWindowRect($h, [ref]$r)
$w = $r.Right - $r.Left
$ht = $r.Bottom - $r.Top
if ($w -le 0 -or $ht -le 0) { Write-Output "ERROR: bad rect $w x $ht"; exit 1 }

$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, (New-Object System.Drawing.Size($w, $ht)))
$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "OK saved $Out (${w}x${ht}) rect=($($r.Left),$($r.Top))-($($r.Right),$($r.Bottom))"
