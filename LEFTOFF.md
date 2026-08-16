# LEFTOFF — hand-off for the next session (written 2026-08-16 ~20:30)

Read this, then `CLAUDE.md` (rules), then the top entry of `PROGRESS.md` (proofs).

## Where the port stands

**The game is playable end to end: main menu → new game → Geoscape → base →
New Battle → briefing → inventory → Battlescape, with a unit walking around.**
Every step is screenshotted in `C:\temp\amiga_oxcom\tftd_*.png` and listed in the
top entry of `PROGRESS.md`. No `CPU TRAP` anywhere along that path.

- Binary: `openxcom-aga` (+ `-rtg`, `-ask`), built by `build/build.sh`, deployed to
  `C:\temp\amiga_oxcom\work\` (= `Work:` on the emulated Amiga).
- Test machines: `winuae/oxc-aga-ram256.uae` (68020, no FPU, **JIT on**, 256 MB) for
  turnaround, and `winuae/oxc-aga-nojit-ram256.uae` (**JIT off**, 256 MB) for every
  timing claim — `CLAUDE.md` requires that, and the older `oxc-aga-nojit.uae` is
  useless here because it has only 32 MB and cannot load the game. Note both still
  run `cpu_speed=max`, so they are "no JIT", not "a real A1200".
  The real target `oxc-aga.uae` (32 MB) still runs out of memory while loading —
  **parked** by the user ("get it running first, optimise later").
- **The game being played is TFTD**, because that is the data the user has. See below.

### Data setup — read this before debugging anything that looks like wrong graphics

`data/UFO/` contains **TFTD's** files (proof in `PROGRESS.md`: `AQUA.PCK`,
`DEEPONE.PCK`, `ATLANTIS.MCD`, `UP*.BDY`, a 3-palette `PALETTES.DAT`, and 39
underwater globe textures). Running it under the `xcom1` (UFO) ruleset produced a
globe of blue speckle, which cost a session to chase as a "port bug". It was not.

The live deploy is now set up as:

- `C:\temp\amiga_oxcom\work\data\TFTD\` — a **copy** of the TFTD data
  (`data/UFO/` was left untouched; nothing was deleted).
- `C:\temp\amiga_oxcom\work\user\options.cfg` — `xcom2` active, `xcom1` inactive.
  The previous file is kept as `options.cfg.bak-xcom1`.
- `standard/xcom1/metadata.yml` says `loadResources: [UFO]`,
  `standard/xcom2/metadata.yml` says `[TFTD]` — that mapping is the whole story.

`build.sh` deploys game data with `cp -rn` (no overwrite), so a rebuild does not
disturb any of this. If the user ever supplies real UFO data, drop it in
`data/UFO/` and flip the two `active:` flags back.

### THE PLAN THE USER SET (2026-08-16 21:45) — do these, in this order

Rules for every step, set by the user after an evening of regressions:
**full backup zip before each step** (`I:\GITHUB\Amiga_OpenXCOM_backup_<date>_<HHMM>_<label>.zip`,
convention in "Backups" below), **one change per build**, **test it yourself without the
user** (no-JIT config, drive with autoinput, screenshot, read `globe: 10 draws` /
`globe: ms/draw` in `oxc.log`), and only then the next step. If a step makes anything
worse, revert to its backup — do not stack a fix on top.

Baseline you start from (backup `..._2140_globus-22fps-znany-dobry.zip`): all of the game
works, globe = throttles + fixed-point shadow + textured land, cap 250 ms, **22 fps**
geoscape without JIT, redraw ~40 ms (shadow 22, land 14–20). `build.sh` tracks header
dependencies now (see PROGRESS.md top entry — that was the cause of the whole evening).

1. **"Amiga" options tab, placed BEFORE "General" (i.e. first) in the options screen**, with
   two settings copied from the OpenTTD port ("more things will land there"):
   - **Amiga application bar** on/off — the window title bar in window/WB mode:
     `amigagfx_open(w, h, show_bar, backend)` already takes it (`native/amiga_gfx.h`;
     sdlmini passes 0 today in `sdlmini_video.c:546`). OpenTTD calls it `wb_bar`.
   - **Cursor: original (game-drawn) / Amiga cursor only** — the platform layer already has
     `amigagfx_set_hide_system_pointer(on)`; sdlmini's `SDL_ShowCursor`/`SDL_SetCursor`
     drive it (`sdlmini_events.c:436-453`). "Amiga cursor only" = show the Intuition
     pointer and suppress the game's `Cursor` blit (`Game::run` blits `_cursor` every
     frame — skip it under the option); "original" = today's behaviour.
   - Where: `src/Menu/OptionsBaseState.cpp` builds the tab buttons at fixed y (Video 8,
     Audio 28, Controls 48, Geoscape 68, Battlescape 88, Advanced 108, Mods 128); add an
     "Amiga" button first and shift the rest, or reuse the Video screen pattern
     (`OptionsVideoState.cpp`) for the new `OptionsAmigaState`. Options live in
     `Engine/Options.cpp/.h` (`OptionInfo` list; the Amiga defaults block is already
     patched there — see the "small-screen video defaults" patch). New options need
     language strings: add them to `bin/common/Language/en-US.yml` via the patch script or
     use plain literals for now. Persist in `options.cfg` like the others.
   - Do it in the patch script (whole-file replacements in `native/oxc-replace/` are fine
     for a NEW file such as `OptionsAmigaState.cpp/.h`; remember to add it to the game
     source list — check how `build.sh` collects sources).
2. **Span fills** (`native/sdlmini/src/sdlmini_gfx.c`): `hspan()` (clip once per row,
   `memset` for 8bpp) for `filledCircleColor`/`span_flat`, and `span_textured` with ONE
   modulo per span then incremental wrap instead of two `%` per pixel. Already written and
   measured (ocean 0 ms, land 0 ms) — the code is in `C:\temp\amiga_oxcom\gfx_body.txt`,
   `gfx_tex.txt`, `gfx_idx.txt` (`SDLmini_FilledPolygon8`, index fill; keep it, step 5
   needs it) and `gfx_patch.py`/`gfx_patch2.py` apply them. Expect redraw 40 → ~25 ms.
3. **Radar surface cache** (patch script, Globe.h/.cpp): redraw `_radars` only when the
   projection changed, `_hover`, the base/craft/facility key changed, or 2 s passed.
   Written: `C:\temp\amiga_oxcom\radar_patch.py` (applies onto the current script; it
   adds `_radarKey/_radarTime` members — a header change, which is exactly why build.sh
   had to be fixed). Saves ~20 ms per base per redraw.
4. **`polarToCart` / `pointBack` on sin/cos LUTs** (Q16, ~4096 entries) so `cachePolygons`
   (~400 ms per rotation/zoom today) and `getSunDirection` stop going through the ROM.
   Then `XuLine` (radar circles, coastlines at zoom ≥ 1: ~40 ms) as integer Bresenham.
5. **Flat sun-shaded land polygons** — the user's stated preference: NO textures, but each
   polygon a different shade by its angle to the sun (dominant texture index, darkened
   0..5 steps by the dot product of the centre normal from `_earthFix` and the sun),
   still per-pixel day/night shaded on top. Written: `C:\temp\amiga_oxcom\shadepoly2.py`
   (needs `SDLmini_FilledPolygon8` from step 2). Do it LAST and show a screenshot; the
   user was explicit that "one flat colour for all land" is not acceptable.
6. When the redraw is ~20 ms, lower `AMIGA_GLOBE_MIN_MS` (Globe.cpp marker-include patch)
   from 250 towards 100.

Later, not now: dirty rectangles in sdlmini/amiga_gfx (the c2p of the whole 320x200 is
~35–40 ms/frame = the ~25 fps ceiling; the OpenTTD/StarCraft ports have it), the
keyboard ("6" for every key — see below), removing temporary diagnostics, sound.

### Still open, unrelated

- **Keyboard: typing produces only "6".** Real keypresses logged
  `event: key raw 0x13 down -> sym 54`, but the compiled key table maps raw 0x13 to 114
  (`r`) — verified byte by byte (`C:\temp\amiga_oxcom\keytab.py`; `sizeof(AmigaKey)` is
  10 on m68k). Either `lookup()` in `sdlmini_events.c` returns the wrong entry or the log
  lies (CLAUDE.md rule 4). The log now prints index / entry.raw / sym / sizeof on three
  short lines. Needs a human at the keyboard: autoinput injects at the SDL level.
- Temporary diagnostics still compiled in (list at the end of the "evening" entry in
  PROGRESS.md, plus the Globe draw timing — keep the timing until the globe work is done).

### Globe work already in place (do not re-derive)

- One full globe redraw per `AMIGA_GLOBE_MIN_MS` (250), unconditional, `_redraw` left set.
- `cachePolygons()` only when `_cenLon/_cenLat/_radius` changed (`_cache*` members).
- `drawShadow` in Q1.14: `CordFix`/`_earthFix` (Globe.h), `CreateShadowFix`/`cordToFix`
  (Globe.cpp); double `CreateShadow` kept for `getPolygonTextureAndShade`.

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
