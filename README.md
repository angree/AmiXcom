# AmiXcom — OpenXcom for classic Amiga (68k, AGA)

**Made with Claude Code** (Anthropic's Claude, driven from the terminal), by angree — contact: **angree@wp.pl**. Follow-up to the same author's
[OpenTTD 68k port](https://github.com/angree/openttd_amiga_68k), which lends this port
its whole platform layer (c2p, Paula audio, startup code).

AmiXcom is a native AmigaOS 3.x port of [OpenXcom](https://openxcom.org) — the open
source reimplementation of *X-COM: UFO Defense* and *X-COM: Terror from the Deep* —
for **real classic hardware**: 68020+ without FPU, AGA chipset. Not PiStorm-, Vampire-
or Emu68-only. No SDL: the SDL 1.2 API the game expects is a small shim
(`native/sdlmini/`) on top of a bare-metal Amiga graphics/audio layer.

## Status: 0.9.8 — alpha

The whole game runs on the Amiga: main menu, Geoscape, bases, Battlescape, and both
rulesets (UFO and TFTD). It has been tested for hours, not played to the end, so expect
rough edges; every Guru is caught and logged with its PC in `oxc.log`.

**Music** (0.9.0) comes from your own `GM.CAT`, played through a software mixer written
for this port: sixteen voices folded into one stream, so Paula's four hardware channels
stop being the limit. The instrument bank ships with the port (FluidR3, MIT); the music
itself never leaves your own data. It needs about **36 MB of free disk**, because by
default every tune is mixed to disk once at first start and simply played back after
that. Mixing live while you play is an option too (*Options → Amiga*), but on a slow
machine it costs a quarter of an 030/50 and breaks up whenever the game stops drawing.

Speed, compared to the first version that ran at all: startup about 2.7x faster,
Geoscape ~50 fps, Battlescape idle ~35 fps on an 040/40, unit step 6 s to 0.3 s, alien
turn 280 s to ~84 s, saving 45-60 s to ~8 s. The globe is integer fixed-point with
precomputed shadow tables.

Earlier releases and their numbers are on the
[releases page](https://github.com/angree/AmiXcom/releases).

Known problems and gaps:

- **~50 MB of fast RAM required**; 32 MB machines still run out while loading.
- **Music is new** and lightly tested. If it misbehaves, *Options → Amiga → Music*
  turns it off.
- **AGA, 320x200, 8-bit.** The RTG build (`openxcom-rtg`) compiles and has had far less
  testing; the `-ask` build asks which to use at startup.
- **Keyboard text entry is broken** (every key types the same character). The mouse
  works and the game is playable with it.
- Loading is still slow, and save-list dates show "????".
- An FPS counter is drawn in the corner on purpose, as a measurement aid.
- Developed in WinUAE. Real-hardware reports are welcome and have already fixed two
  bugs no emulator here reproduces.

### Languages

The port ships 27 translations besides English - Polish, German, French,
Spanish, Italian, Dutch, Portuguese, Russian, Ukrainian, Czech, Slovak,
Hungarian, Romanian, Bulgarian, Greek, Turkish and the Nordic ones among them.
Pick one in *Options -> Video*, or leave *Options -> Amiga -> LANGUAGE FROM
WORKBENCH* on and the game follows `Prefs/Locale`. Choosing by hand turns the
automatic mode off; either way it applies at the next start.

They are OpenXcom's own translations, pulled from Transifex by OpenXcom's daily
workflow and shipped in its own builds - same project, same licence. The
languages left out are the ones whose letters are not in the fonts this port
draws with (Japanese, Korean, Chinese, Arabic, Thai, Vietnamese, Latvian,
Serbian, Tatar, Croatian), plus three that are barely started. Refresh or
re-pick the set with `build/fetch_translations.py` (`--list` just prints what it
would keep and why).

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
