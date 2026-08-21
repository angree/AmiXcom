# AmiXcom — OpenXcom for classic Amiga (68k, AGA)

**Made with Claude Code** (Anthropic's Claude, driven from the terminal), by angree — contact: **angree@wp.pl**. Follow-up to the same author's
[OpenTTD 68k port](https://github.com/angree/openttd_amiga_68k), which lends this port
its whole platform layer (c2p, Paula audio, startup code).

AmiXcom is a native AmigaOS 3.x port of [OpenXcom](https://openxcom.org) — the open
source reimplementation of *X-COM: UFO Defense* and *X-COM: Terror from the Deep* —
for **real classic hardware**: 68020+ without FPU, AGA chipset. Not PiStorm-, Vampire-
or Emu68-only. No SDL: the SDL 1.2 API the game expects is a small shim
(`native/sdlmini/`) on top of a bare-metal Amiga graphics/audio layer.

## Status: 0.9.0 — alpha

New in 0.9.0: **music**. X-COM's tunes are read from your own `GM.CAT` and played
through a software wavetable mixer written for this port — sixteen voices folded into
one 8-bit stream, so Paula's four hardware channels stop being the limit. The
instrument bank (`data/common/music.bnk`, samples from the MIT-licensed FluidR3
soundfont) ships with the port; the music itself never leaves your own data.

**Music needs about 36 MB of free disk space.** By default the game mixes every tune
to disk once, at first start (a few minutes, with its own progress bar), and simply
plays those files afterwards. Mixing live while you play is implemented too and can be
picked in *Options → Amiga*, but on a slow machine it costs real CPU — a quarter of an
030/50 — and, worse, it breaks up whenever the game stops drawing for a moment, such
as during a globe redraw or a savegame parse. Pre-rendered audio has no such failure
mode, so that is the default; "Mixed live" stays for anyone who would rather keep the
disk space.

New in 0.8.0: **walking no longer freezes at every tile** — the per-step visibility and
lighting scan runs in slices across the walk animation (new Amiga option "Split movement
calculation", ON by default), the Amiga options tab is a scrolling list, and the New
Battle screen opens ~2× faster.

New in 0.7.2: **game startup ~2.7× faster** (040/40-class: ~6 min → ~2 min; 030/50:
~15 min → ~5.5 min) — graphics loaders no longer read byte-by-byte, yaml rulesets get
a binary cache (`.ybc`), transparency tables and fonts fixed; the system mouse pointer
stays visible during loading. Earlier 0.6-0.7.1 (see releases): battlescape drawing
reworked (idle ~35 fps on 040/40), alien turn 280 → ~84 s, mid-turn TRAPV crash fixed.

## Older status (0.5.0)

The whole game compiles and runs on the Amiga: main menu → new game → Geoscape → base
→ battle briefing → inventory → Battlescape. Both rulesets (UFO and TFTD) load.
**Zero guarantee that a full game plays through** — it has been tested for a few
hours in an emulator, not played to the end. Expect crashes, expect them to be reported
in `oxc.log` (every Guru is caught and logged with its PC).

New in 0.5.0 (details in the release notes):

- **Saving ~7x faster** (battle save 45-60 s → ~8 s) and **loading ~4x faster**
  (~90 s → ~20-25 s) on an 040/40-class machine: yaml-cpp scalar conversion and
  memory pooling fixed, a direct YAML writer replaces the emitter, the battle
  state serializes without building a node tree, and a whole compiler-ICE
  workaround put the save/load path back at -O1 after living at -O0.
- **Globe 3D ~10x faster**: integer fixed-point geometry with precomputed vertex
  trig, shadow tables precomputed at build time (`data/common/earthfix.dat` —
  first zoom to any level used to stall ~5 s), half-resolution day/night shadow,
  radar circles in pure vector math, fixed-point line drawing, dogfight zoom in
  one jump (reaching a fight took 30-60 s), flat sun-shaded water polygons
  (option `amigaFlatGlobe`, set 0 for the old textured look).
- **Dirty rectangles** in the SDL shim: unchanged frames skip chunky-to-planar
  entirely (groundwork for a future hi-res mode).
- Boot detaches the game (`Run <NIL:`) so the CLI closes and Workbench stays
  usable — the free-memory gauge shows the port needs ~50 MB right now.

New in 0.3.0: playable battlescape (unit step ~6 s → ~0.3 s, map render
~100 → ~10-16 ms), geoscape ~40 fps (was ~5), "Amiga" options tab.

Known problems and gaps in this release, briefly:

- **Load is still ~20 s** (yaml parse dominates) and the save-list dates show "????".
- **~50 MB RAM required**; 32 MB machines will not load the game yet.
- **Music is new in 0.9.0** and has had little testing; if it misbehaves, *Options →
  Amiga → Music* turns it off.
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
3. Start it: double-click the `openxcom-aga` icon on Workbench (the icons carry the
   1 MB stack the game needs), or from a Shell `execute run` in that directory (the
   script sets the stack; `run-rtg` / `run-ask` for the other two binaries; the log
   goes to `oxc.log`). Everything is relative to the program directory (`PROGDIR:`),
   so it can live anywhere.
4. The first start creates `user/options.cfg`. UFO is the default ruleset; to play TFTD
   open *Options → Mods* in the game and switch from *X-COM: UFO Defense* to
   *X-COM: Terror from the Deep*, or edit `user/options.cfg` (`xcom1` → `active: false`,
   `xcom2` → `active: true`).

Requirements: 68020 or better (no FPU needed or used), AGA, Kickstart 3.0+, lots of fast
RAM (see above), ~40 MB of disk for the game data, plus **~36 MB for the pre-rendered
music** (or none at all if you set *Options → Amiga → Music* to "Mixed live" or "Off").

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

The instrument bank for the music (`data/music.bnk`, deployed to
`data/common/music.bnk`) is generated, not stored in the repository — the same way
`data/common/earthfix.dat` is. To rebuild it you need Frank Wen's **FluidR3_GM.sf2**
(MIT; it is the `fluid-soundfont` source package in Debian/Ubuntu), the `sf2utils`
Python package, and any X-COM `GM.CAT` to tell the generator which instruments the
tunes actually use:

```sh
export AMX_SF2=/path/to/FluidR3_GM.sf2
export AMX_GMCAT=/path/to/SOUND/GM.CAT
python3 build/gen_music_bank.py          # writes music.bnk -> put it in data/
```

Without the bank the build still succeeds and simply plays no music.

`winuae/` holds the WinUAE configs and the host-side test harness (autoinput driven
from inside the guest, screenshots, trap-to-symbol mapping) used to develop this without
a human at the emulator.

`PORT_RESEARCH.md`, `PROGRESS.md` (facts and proofs, newest first) and `LEFTOFF.md`
(what is open, how to run) document the work in detail.

## License

GPL 3.0, like OpenXcom itself — see `LICENSE`. OpenXcom is © the OpenXcom developers
(https://openxcom.org). X-COM is a trademark of Take-Two Interactive; no game data is
included or distributed here — including the music, which is rendered on your own
machine from your own `GM.CAT`. The c2p routines are Mikael Kalms'; the graphics/audio
platform layer comes from the author's OpenTTD Amiga port (MIT). The instrument samples
in `data/common/music.bnk` come from Frank Wen's FluidR3 soundfont, MIT licensed — see
`data/common/FluidR3_License.txt`.
