# LEFTOFF — hand-off for the next session (written 2026-08-16 ~20:30)

Read this, then `CLAUDE.md` (rules), then the top entry of `PROGRESS.md` (proofs).

## Where the port stands (2026-08-17, after 0.3.0)

**Released**: github.com/angree/AmiXcom - v0.1.0/0.2.0/0.3.0 (code without
ROM/HDF/CGX-headers/game data; releases without X-COM data; mkicon.py icons
carry the 1 MB stack). Game shows "AmiXcom 0.3.0 alpha" (version.h is the one
source). Main branch = everything; step1-amiga-wip branch merged and obsolete.

**Performance today** (numbers in PROGRESS.md top entry):
- Geoscape ~40 fps (was 5): draw-only-on-change globe + colorkey blit A/B/C
  in sdlmini + the 20 ms SDL_Delay(1) nap removed.
- Battlescape playable: unit step ~0.3 s (was ~6 s): mover-only FOV, pair
  spotting, incremental discovery (Amiga tab: Fast/Accurate[default]/Test),
  integer addLight; map render 10-16 ms (was 100): blitNShade in plain C;
  battle anim tick 200 ms by default (option).
- Amiga options tab: screen bar (screen opens TALLER, game keeps 320x200,
  mouse 1:1), Amiga pointer (default), map reveal, anim speed.

**THE PLAN** - remaining, in the user's priority (details LISTA-ROBOT.txt):
1. Dirty rectangles (c2p_rect.s ready in native/) - menu/Bases/geoscape.
2. Globe leftovers: span fills, radar-circle cache, sin/cos LUTs, flat
   sun-shaded land polygons (user demands DIFFERENT shades per sun angle).
3. Fast game save (~1 min now: yaml double->text on soft-float).
4. Cleanup TEMP probes (perf:/slow frame/step:/fov:/map:/globe:) before 0.4.0.
5. Keyboard "6", sound (Paula/ADPCM), RTG test, 32 MB RAM reduction.

**Rules** (user, unchanged): backup zip before each step (harness/backup.ps1
-Label X -Note Y), one change per build, self-test via autoinput+log, revert
rather than stack fixes. RESTORE heavily-patched files from the tarball before
each build (sh /mnt/c/temp/amiga_oxcom/restore_file.sh Battlescape/TileEngine.cpp
Battlescape/UnitWalkBState.cpp Battlescape/Map.cpp Engine/Game.cpp ...) - some
overlapping patches are not idempotent on an already-patched file and stack
duplicate declarations. `build.sh clean` is always safe.

**Measuring**: the user toggles JIT/cpu_throttle by hand in the WinUAE GUI (F12)
- launch with JIT (oxc-aga-ram256.uae) for fast load, they switch, then read
the probes from oxc.log (Monitor on `tail -f`). Timer resolution is 20 ms -
only averaged numbers mean anything. NEVER leave a Work:autoinput.txt behind
(the f12-in-file incident cost a night: game replays it on every boot and the
in-game screenshot path (8->24bpp) halts the machine).

## What was fixed, and how it was proven

| symptom | cause | fix |
|---|---|---|
| Guru `#8000000B` on the first frame | `#8000000B` = **Line-F**. Kickstart 3.1 `mathieeesingbas.library 40.4`: on a CPU without FPU its `IEEESPMul`/`IEEESPDiv` table entries point into the table itself; libnix `-lm` sends every `float*`/`float/` there | `native/fp_single.c` (`__mulsf3`/`__divsf3`), linked before `-lm` |
| garbled fonts / menu text | libnix `wmemcpy` copies `n*2` bytes (wchar_t is 4) | `native/libnix_fixes.c` |
| Gurus tell you nothing | — | `native/amiga_trap.c`: logs `CPU TRAP n at PC … + regs + raw frame + 512 bytes of user stack`; `winuae/harness/trapmap.py` (WSL) turns that into a backtrace |
| `TRAP 4 at PC 0xnnnn0000` on new game | `__NO_MUSIC` build → `Mod::getMusic` returns 0 → `music->play()` through a NULL vtable | patch script: `getMusic`/`getSound` fall back to the mute objects |
| globe land = blue speckle | TFTD data in `data/UFO/` + `xcom1` ruleset active | data placement + `options.cfg` (above); **no code change** |
| a screenshot came back as WinUAE's boot log | `capture_ours.ps1` used `MainWindowHandle`, which follows focus when `-log` is on | it now enumerates the process's windows and picks the title starting with "WinUAE" |
| driving the game clicked the user's desktop | host-side `mouse_event` | **retired**; `sdlmini_autoinput.c` + `winuae/harness/autoinput.ps1` inject events inside the guest |

Verified NOT broken (probe `C:\temp\oxctest\fptest2.c`, host vs Amiga diff): every
soft-float and libm routine the binary links.

## How to run and drive it

```powershell
# build (WSL), ~2 min incremental
wsl sh /mnt/i/GITHUB/Amiga_OpenXCOM/build/build.sh
# start (waits for the game log), leave it running
winuae\harness\run-oxc.ps1 -Config I:\GITHUB\Amiga_OpenXCOM\winuae\oxc-aga-ram256.uae -TimeoutSec 240 -KeepRunning
# WAIT until oxc.log contains "state: resetAll done" (main menu up, ~25 s) - clicks
# injected while the game is still loading are silently lost.
winuae\harness\autoinput.ps1 "click 100 100" "wait 3000" "click 110 42" "wait 1000" "click 118 172"
winuae\harness\capture_ours.ps1 -Out C:\temp\amiga_oxcom\x.png
winuae\harness\kill_ours.ps1
wsl python3 /mnt/i/GITHUB/Amiga_OpenXCOM/winuae/harness/trapmap.py   # map a CPU TRAP to symbols
```

Game-pixel coordinates for `autoinput` (screen is 320x200; in a WinUAE window
screenshot, game pixel = 2.0 window px, origin (106,78) — so
`game = (window - 106or78) / 2`):

| target | click |
|---|---|
| main menu: New Game / New Battle | `100 100` / `211 101` |
| difficulty: Beginner / OK | `110 42` / `118 172` |
| geoscape sidebar INTERCEPT..FUNDING | `288 6`, `288 18` (BASES), `288 30`, `288 42`, `288 54`, `288 66` |
| ocean (base site, South Atlantic) | `97 101` |
| Mission Generator OK | `57 184` |
| briefing OK | `160 173` |
| inventory OK | `254 11` |
| a message box's OK | `160 163` |

Typing: `autoinput.ps1 "key a" "key m" "key i" "key g" "key a" "key enter"`.

Logs: `C:\temp\amiga_oxcom\work\oxc.log` (game stdout + sdlmini), `sdlmini.log`,
`work\user\openxcom.log`.

## Gotchas that cost time

- **`build.sh` used to ignore header changes** (only `.cpp` vs `.o`); a header that grew a
  class left every other TU with the old `sizeof` → heap corruption that looked like five
  different bugs over one evening. Fixed (`needs_build()` + `-MMD` `.d` files). If you ever
  see "impossible" behaviour after touching a `.h`, wipe `~/build/obj` and rebuild before
  reading a single line of code.
- **A black WinUAE window with a healthy log** = the window opened on the secondary
  monitor (WinUAE 2.8.1 reads `MainPosX/Y` from `winuae.ini`, ignores the config's
  `win32.posx`; DirectDraw there is black for the user AND for every capture).
  `run-oxc.ps1` now forces the ini position to the primary monitor before each start.
- The patch script's `edit()` is idempotent only for an identical patch. If you change a
  patch for a file already patched in `~/build/openxcom/src/`, restore that file from the
  tarball first — `C:\temp\amiga_oxcom\restore2.sh` does `Geoscape/Globe.cpp` + `Globe.h`,
  `restore_main.sh` one file (edit the path inside) — or run `build.sh clean`.
- Timing of autoinput clicks: with JIT the game is much faster than the waits used
  without JIT and clicks land on the wrong screen (a base name typed before OK was
  clicked, a zoom click during base placement). Poll `oxc.log` for the state marker
  (`BuildNewBaseState pushed`, `state: resetAll done`) instead of fixed waits.
- Multiple detections at "1 Day" speed pile up identical "TOUCHDOWN SITE" dialogs;
  clicking Cancel just reveals the next one — go back to "5 Secs" first.
- No Python on the Windows side; use `wsl python3`. In the Bash tool, heredocs and perl
  one-liners mangle backslashes and `||` — write scripts with the Write tool and edit
  source with the Edit tool.
- `~/build/oxc.nm` goes stale after every build; `trapmap.py` regenerates it, hand-made
  `objdump` lookups must too (a stale nm sent one session chasing a "corrupt vtable").
- `Work:run` must end up pointing at `openxcom-aga`; a probe left in `run` looks like a
  regression to the user.
- The user runs other Amigas from the same `winuae.exe`: only `kill_ours.ps1` /
  `capture_ours.ps1`, never `Stop-Process -Name winuae`, never host input synthesis.
- The trap handler's `a7` is the supervisor stack; the crashed task's stack is the USP.
- **Before blaming the port for wrong graphics, check the data.** Rendering the raw
  asset on the host with the game's own palette (`C:\temp\amiga_oxcom\texsheet.py`)
  answers "is this what the file actually contains?" in one minute.

## Backups

`I:\GITHUB\Amiga_OpenXCOM_backup_<date>_<time>_<label>.zip`, following the author's
convention from `Amiga_Remote_Play`. The zip holds the repo without `winuae/work`
(stale deploy) and includes `winuae/boot.hdf`. Latest known-good: `Amiga_OpenXCOM_backup_2026-08-16_2140_globus-22fps-znany-dobry.zip`
(throttles + fixed-point shadow + textures, fixed build.sh). Older:
`..._2030_tftd-battlescape-dziala.zip` (before any globe work), `..._1833_geoscape-dziala.zip`.

## Probes (C:\temp\oxctest)

`fptest.c` (IEEE library path), `fptest2.c` (all FP routines, host-diffable), `traptest.c`
(handler self-test), `fmttest.c`, `cattest.cpp`, `filetest.c`, `paltest.c`. Build like the
game (`-mcpu=68020 -msoft-float -O1 -noixemul -I native ... native/amiga_trap.c
native/fp_conv.c native/fp_single.c -lamiga -lm`), copy to `Work:`, point `Work:run` at it,
restore `run` afterwards (`C:\temp\amiga_oxcom\probe.sh` builds fptest2 both ways).
