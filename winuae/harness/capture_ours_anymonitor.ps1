# Capture our WinUAE window even when it sits on a secondary monitor: DirectDraw
# windowed output cannot be read there (PrintWindow/CopyFromScreen give black),
# so the window is moved to the primary monitor for the capture and moved back.
param([string]$Out)
$proc = Get-CimInstance Win32_Process -Filter "Name = 'winuae.exe'" | Where-Object { $_.CommandLine -match 'oxc-' } | Select-Object -First 1
$p = Get-Process -Id $proc.ProcessId
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W3 {
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
 [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
 public struct R { public int L,T,Rr,B; } }
"@
$h = $p.MainWindowHandle
$r = New-Object W3+R; [void][W3]::GetWindowRect($h,[ref]$r)
$w=$r.Rr-$r.L; $ht=$r.B-$r.T
$moved = $false
if ($r.L -ge 1900 -or $r.L -lt 0) { [void][W3]::SetWindowPos($h,[IntPtr]::Zero,100,60,0,0,0x0015); $moved=$true; Start-Sleep -Milliseconds 700 }
$r2 = New-Object W3+R; [void][W3]::GetWindowRect($h,[ref]$r2)
$bmp = New-Object System.Drawing.Bitmap($w,$ht); $g=[System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r2.L,$r2.T,0,0,(New-Object System.Drawing.Size($w,$ht))); $g.Dispose()
$bmp.Save($Out); $bmp.Dispose()
if ($moved) { [void][W3]::SetWindowPos($h,[IntPtr]::Zero,$r.L,$r.T,0,0,0x0015) }
"saved $Out (window was at $($r.L),$($r.T); moved=$moved)"
