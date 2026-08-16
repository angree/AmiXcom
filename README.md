# AmiXcom — OpenXcom for classic Amiga (68k, AGA)

**Made with Claude Code** (Anthropic's Claude, driven from the terminal), by angree — contact: **angree@wp.pl**. Follow-up to the same author's
[OpenTTD 68k port](https://github.com/angree/openttd_amiga_68k), which lends this port
its whole platform layer (c2p, Paula audio, startup code).

AmiXcom is a native AmigaOS 3.x port of [OpenXcom](https://openxcom.org) — the open
source reimplementation of *X-COM: UFO Defense* and *X-COM: Terror from the Deep* —
for **real classic hardware**: 68020+ without FPU, AGA chipset. Not PiStorm-, Vampire-
or Emu68-only. No SDL: the SDL 1.2 API the game expects is a small shim
(`native/sdlmini/`) on top of a bare-metal Amiga graphics/audio layer.

## Status: 0.1.0 — complete alpha

The whole game compiles and runs on the Amiga: main menu → new game → Geoscape → base
→ battle briefing → inventory → Battlescape. Both rulesets (UFO and TFTD) load.
**Zero guarantee that a full game plays through** — it has been tested for a few
hours in an emulator, not played to the end. Expect crashes, expect them to be reported
in `oxc.log` (every Guru is caught and logged with its PC).

Known problems and gaps in this release, briefly:

- **The Geoscape globe is slow** (~20 fps on a fast 68020 emulation, full redraw every
  250 ms at most; rotating/zooming stalls for a moment). Rendering still uses soft-float
  in a few places; span fills, radar cache, sin/cos tables and flat sun-shaded land
  polygons are next on the list.
- **No dirty rectangles** — the whole 320×200 screen is c2p-converted every frame
  (~35–40 ms on a 68020), which caps everything at ~25 fps.
- **AGA only, 320×200, 8-bit.** An RTG build (`openxcom-rtg`) is compiled but untested;
  the `-ask` build asks which one to use at start.
- **No sound and no music yet** (built with `__NO_MUSIC`; the Paula/ADPCM path from the
  OpenTTD port is not wired in).
- **Keyboard text entry is broken** (every key types the same character) — the mouse
  works, and the game is playable with it.
- **RAM: needs a lot.** Tested with 256 MB of fast RAM in WinUAE; a 32 MB machine still
  runs out of memory while loading. Memory reduction has not been started.
- An FPS counter is drawn in the corner on purpose (measurement aid, stays for now).
- Only tested in WinUAE (68020 no-FPU, no JIT). No report from real hardware yet.
- Only Kickstart 3.1 / OS 3.1 tested; the game writes only to its own directory
  (`PROGDIR:`).

## Installing on the Amiga

The release archive contains **no X-COM game data** — you need the original PC game
(UFO: Enemy Unknown / X-COM: UFO Defense and/or Terror from the Deep — GOG/Steam
copies work).

1. Unpack the release archive into a directory of your choice, e.g. `Work:AmiXcom/`.
   It contains `openxcom-aga`, `openxcom-rtg`, `openxcom-ask`, the `run` script and the
   `data/` directory with OpenXcom's own files (`common/`, `standard/`).
2. Copy the game data from your PC installation:
   - UFO: the folders `GEODATA GEOGRAPH MAPS ROUTES SOUND TERRAIN UFOGRAPH UNITS`
     into `data/UFO/`
   - TFTD: the same set of folders (`GEODATA GEOGRAPH MAPS ROUTES SOUND TERRAIN UFOGRAPH
     UNITS`, plus `ANIMS FLOP_INT` if present) into `data/TFTD/`
   File and folder names must keep their case as on the PC (upper case is fine).
3. Start from a Shell: `cd Work:AmiXcom` then `execute run` — the script sets the
   1 MB stack the game needs and starts `openxcom-aga` (`run-rtg` / `run-ask` for the
   other two binaries; log goes to `oxc.log`). Do not run the binary from Workbench
   without a stack of at least 1 MB.
4. The first start creates `user/options.cfg`. UFO is the default ruleset; to play TFTD
   open *Options → Mods* in the game and switch from *X-COM: UFO Defense* to
   *X-COM: Terror from the Deep*, or edit `user/options.cfg` (`xcom1` → `active: false`,
   `xcom2` → `active: true`).

Requirements: 68020 or better (no FPU needed or used), AGA, Kickstart 3.0+, lots of fast
RAM (see above), ~40 MB of disk for the game data.

## Building

The repository never contains a modified copy of OpenXcom. The port is:

- `upstream/openxcom-00fbacde.tar.gz` — pristine upstream (commit `00fbacde`, 2016-06-27,
  the last mature TFTD-capable, pre-OXCE base),
- `build/apply-amiga-patches.py` — the mechanical, idempotent patch set,
- `native/` — everything Amiga-specific (sdlmini SDL shim, gfx/audio/startup layer,
  c2p, whole-file replacements in `native/oxc-replace/`),
- `build/build.sh` — unpacks upstream, applies the patches, builds all three binaries.

Toolchain: [bebbo's amiga-gcc](https://github.com/bebbo/amiga-gcc) 6.5.0b
(`m68k-amigaos-gcc`), built at `-O1 -mcpu=68020 -msoft-float -noixemul` — the flags are
not negotiable, each one cost real time to find (see `PROGRESS.md`). yaml-cpp 0.6.3 is
built as one translation unit (the Hunk format has no COMDAT). The RTG build needs the
CyberGraphX developer headers in `native/cgx-include/` (not redistributable, not
included). Run `sh build/build.sh` inside WSL/Linux; the header comment of the script
tells the rest.

`winuae/` holds the WinUAE configs and the host-side test harness (autoinput driven
from inside the guest, screenshots, trap-to-symbol mapping) used to develop this without
a human at the emulator.

`PORT_RESEARCH.md`, `PROGRESS.md` (facts and proofs, newest first) and `LEFTOFF.md`
(what is open, how to run) document the work in detail.

## License

GPL 3.0, like OpenXcom itself — see `LICENSE`. OpenXcom is © the OpenXcom developers
(https://openxcom.org). X-COM is a trademark of Take-Two Interactive; no game data is
included or distributed here. The c2p routines are Mikael Kalms'; the graphics/audio
platform layer comes from the author's OpenTTD Amiga port (MIT).
