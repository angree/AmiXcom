# Drive WinUAE's debugger console WITHOUT stealing focus.
# Attaches to the target process console, injects a command line
# (WriteConsoleInput) and/or scrapes the screen buffer
# (ReadConsoleOutputCharacter).
# Usage:
#   dbg_console.ps1 -ProcName winuae -Send "w 1 101262d4 4 w"
#   dbg_console.ps1 -ProcName winuae -ReadLines 30
param(
  [string]$ProcName = "winuae",
  [string]$Send = "",
  [int]$ReadLines = 0
)

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public class DbgCon {
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint pid);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
  [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr CreateFile(string name, uint access, uint share, IntPtr sec, uint disp, uint flags, IntPtr tmpl);

  [StructLayout(LayoutKind.Sequential)] public struct COORD { public short X; public short Y; }
  [StructLayout(LayoutKind.Sequential)] public struct SMALL_RECT { public short L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct CSBI {
    public COORD dwSize; public COORD dwCursorPosition; public ushort wAttributes;
    public SMALL_RECT srWindow; public COORD dwMaximumWindowSize;
  }
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GetConsoleScreenBufferInfo(IntPtr h, out CSBI info);
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] public static extern bool ReadConsoleOutputCharacterW(IntPtr h, StringBuilder buf, uint len, COORD coord, out uint read);

  [StructLayout(LayoutKind.Explicit)] public struct INPUT_RECORD {
    [FieldOffset(0)] public ushort EventType;
    [FieldOffset(4)] public KEY_EVENT_RECORD KeyEvent;
  }
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct KEY_EVENT_RECORD {
    public int bKeyDown; public ushort wRepeatCount; public ushort wVirtualKeyCode;
    public ushort wVirtualScanCode; public char UnicodeChar; public uint dwControlKeyState;
  }
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] public static extern bool WriteConsoleInputW(IntPtr h, INPUT_RECORD[] recs, uint len, out uint written);

  public static IntPtr OpenConIn()  { return CreateFile("CONIN$",  0xC0000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero); }
  public static IntPtr OpenConOut() { return CreateFile("CONOUT$", 0xC0000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero); }

  public static void SendLine(IntPtr h, string text) {
    var recs = new System.Collections.Generic.List<INPUT_RECORD>();
    foreach (char c in text + "\r") {
      var k = new KEY_EVENT_RECORD();
      k.bKeyDown = 1; k.wRepeatCount = 1; k.UnicodeChar = c;
      k.wVirtualKeyCode = (ushort)(c == '\r' ? 0x0D : 0);
      var r = new INPUT_RECORD(); r.EventType = 1; r.KeyEvent = k;
      recs.Add(r);
      k.bKeyDown = 0; r.KeyEvent = k; recs.Add(r);
    }
    uint written;
    WriteConsoleInputW(h, recs.ToArray(), (uint)recs.Count, out written);
  }

  public static string ReadTail(IntPtr h, int lines) {
    CSBI info;
    if (!GetConsoleScreenBufferInfo(h, out info)) return "(no csbi)";
    var sb = new StringBuilder();
    int last = info.dwCursorPosition.Y;
    int first = Math.Max(0, last - lines + 1);
    for (int y = first; y <= last; y++) {
      var line = new StringBuilder(info.dwSize.X);
      COORD c; c.X = 0; c.Y = (short)y;
      uint read;
      ReadConsoleOutputCharacterW(h, line, (uint)info.dwSize.X, c, out read);
      sb.AppendLine(line.ToString().TrimEnd());
    }
    return sb.ToString();
  }
}
"@

$p = Get-Process -Name $ProcName -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Write-Output "ERROR: no process $ProcName"; exit 1 }

[void][DbgCon]::FreeConsole()
if (-not [DbgCon]::AttachConsole([uint32]$p.Id)) {
  Write-Output "ERROR: AttachConsole failed (no console on target?)"
  exit 1
}
try {
  if ($Send -ne "") {
    $hin = [DbgCon]::OpenConIn()
    [DbgCon]::SendLine($hin, $Send)
    Write-Output "SENT: $Send"
  }
  if ($ReadLines -gt 0) {
    Start-Sleep -Milliseconds 300
    $hout = [DbgCon]::OpenConOut()
    Write-Output ([DbgCon]::ReadTail($hout, $ReadLines))
  }
} finally {
  [void][DbgCon]::FreeConsole()
}
