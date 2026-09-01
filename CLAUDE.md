# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

0.9.8 released (2026-09-02): **github.com/angree/AmiXcom** - code (no ROM/HDF/
CGX headers/game data) + release archives, `.zip` and `.lha` (no X-COM data).
The game calls itself AmiXcom; the ONE version source is the version.h patch in
the patch script. Playable end to end with TFTD data (`data/UFO/` holds TFTD
files, ruleset xcom2). Music from the player's own GM.CAT through a software
mixer, pre-rendered to disk by default (~36 MB, `data/common/music.bnk` MUST
ship). 27 translations besides English, fetched by `build/fetch_translations.py`
from OpenXcom's own Transifex artifact; the language follows Prefs/Locale unless
the player picks one. Screen standard is a setting (Auto/PAL/NTSC).
On the 040/40 reference machine (no JIT, -70%): battle save ~8 s, battle load
~20-25 s, geoscape idle 50 fps, battle step ~0.3 s,
`data/common/earthfix.dat` precomputed shadow tables - MUST ship in releases.
Numbers/proofs: top of `PROGRESS.md`, newest first.

Rules unchanged: **backup zip before every step (winuae/harness/backup.ps1),
one change per build, test it yourself** - when alone ALWAYS on
`oxc-aga-nojit-040-40.uae` (JIT configs only when the user sits at the
emulator; `oxc-aga-fast.uae` has the CPU throttled UP and is diagnostics only,
never a measurement). run-oxc.ps1 needs `-KeepRunning` or it kills the emulator
after printing the log. Before each build restore heavily-patched files from the
tarball (restore_file.sh) - overlapping patches stack duplicates on an
already-patched tree; `build.sh clean` is always safe, and
`AMIGA_NO_PATCH=1 sh build.sh` skips the patcher for an incremental rebuild
after editing the tree by hand (and is the only way to build the FPU variants
straight after a clean build). Mod.cpp MUST stay -O0 (gcc miscompiles it at -O1:
black palettes). Never leave `Work:autoinput.txt` behind (boot-replay incident,
PROGRESS.md). **Read `LEFTOFF.md` first** - it is the hand-off.

## Layout and build

The repository never stores a modified copy of OpenXcom. The port is
`upstream/openxcom-00fbacde.tar.gz` (pristine) + `build/apply-amiga-patches.py`
(mechanical, idempotent) + `native/` (everything new), rebuilt from scratch on every run —
the same model as `openttd_amiga_68k`.

```
native/sdlmini/     SDL 1.2 API shim on top of amiga_gfx.c / amiga_audio.c
native/oxc-replace/ whole-file replacements dropped into src/ by the patch script
native/*.c          amiga_gfx, amiga_audio, amiga_adpcm, amiga_startup, c2p (from the OpenTTD port)
native/cgx-include/ CyberGraphX developer headers (not redistributable, supplied locally)
build/build.sh      the build; run it inside WSL
winuae/             configs, boot.hdf, shared work folder, host-side harness
```

```sh
# build all three binaries (aga / rtg / ask) and deploy to winuae/work
wsl sh /mnt/i/GITHUB/Amiga_OpenXCOM/build/build.sh
wsl sh /mnt/i/GITHUB/Amiga_OpenXCOM/build/build.sh clean   # re-unpack upstream first
```

Toolchain: bebbo amiga-gcc 6.5.0b at `/opt/amiga/bin` inside WSL (Ubuntu 22.04, WSL1).
`/mnt/i` drops out of WSL regularly — every command starts with
`ls /mnt/i/GITHUB >/dev/null 2>&1 || sudo -n mount -t drvfs I: /mnt/i`.

Eight toolchain and platform defects shape this build; each one looks exactly like a bug in the game.
They are documented with their proofs in `PROGRESS.md`:

1. **Never strip.** `m68k-amigaos-strip` produces a Hunk executable that halts the machine
   (WinUAE `HALT1`, black screen, no Guru, no output).
2. **Never use `std::ifstream`/`std::ofstream`.** libstdc++'s `close()` never returns on an
   open file. Use `AmigaIFStream` / `AmigaOFStream` from `native/amiga_fstream.h`; the patch
   script swaps them in across the game and rewrites `YAML::LoadFile` to stdio.
3. **The Hunk format has no COMDAT.** Duplicated template instantiations are de-duplicated by
   the linker, which warns `duplicate section ... has different size` and sometimes keeps the
   wrong one. That made `YAML::LoadFile` loop forever until yaml-cpp was built as a single
   translation unit. Those warnings are not cosmetic — treat them as a live suspect whenever
   something behaves impossibly.
4. **Never call `sprintf`.** It produces nonsense on this libc — wrong values, shifted
   arguments, empty `%s`. `fprintf`, `snprintf`, `vsprintf` and `vsnprintf` are all correct;
   use `snprintf`. This defect lies to you in your own diagnostics, so a log line that makes
   no sense is a `sprintf` until proven otherwise (proof and numbers in `PROGRESS.md`).
5. **`float * float` and `float / float` must never reach the ROM.** With `-msoft-float`
   libgcc has no float arithmetic; libnix's `-lm` maps it onto the AmigaOS IEEE libraries,
   and Kickstart 3.1's `mathieeesingbas.library` has broken `IEEESPMul`/`IEEESPDiv` entries
   on machines without an FPU (they point into the function table itself → Line-F,
   Guru `#8000000B`). `native/fp_single.c` provides `__mulsf3`/`__divsf3` and is linked
   ahead of `-lm`; keep it there. Everything else in the IEEE path (SP add/sub, all DP,
   `sqrt`/`sin`/`pow`) is verified good. `#8000000B` is **Line-F**, not a bus error.

6. **A file that DEFINES library functions must be compiled `-fno-builtin`.**
   `native/fp_double.c` wrote `float floorf(float x) { return (float)floor((double)x); }`
   and gcc, which knows that narrowing identity, rewrote the body into a call to
   `floorf` - the function being defined. `sqrtf`, `floorf` and `ceilf` were all
   infinite recursion in 0.9.3; the first one the battlescape reached (the TU cost
   of a reserved shot, on the first attempt to move) blew the stack, and a blown
   stack on the 68020 arrives as address error `#80000003` with the machine dead
   before `amiga_trap.c` can log anything. **A Guru that left NO `CPU TRAP` line is
   a stack overflow until proven otherwise.** `build.sh` compiles `fp_single.c`,
   `fp_double.c` and `fp_conv.c` with `-fno-builtin`; keep it that way.

7. **`AbortIO()` does not cancel an `audio.device` CMD_WRITE that is already
   playing.** The request stays NT_MESSAGE with `CheckIO()` returning 0 across the
   AbortIO (measured, 2026-09-01), so the `WaitIO()` after it waits for a reply that
   never comes and the machine sits there with no Guru, no log line and no CPU load.
   That was the freeze on every music change, and it got likelier the faster the CPU
   ran, because the window is exactly the time the device spends playing a buffer.
   Cancel with **`CMD_FLUSH` on the channel** - it aborts every request queued there,
   the one in progress included, and replies them all - and only then `WaitIO`.
   `native/amiga_audio.c` has no `AbortIO` left; keep it that way.

8. **The C library takes the decimal separator from `locale.library`, and
   `setlocale` cannot stop it.** Measured on 2026-09-01, one line after
   `setlocale(LC_ALL, "C")`: `locale: snprintf gives 1,500, decimal_point .` -
   `localeconv()` reports a dot while `snprintf` prints a comma in the same
   breath. So on a Workbench whose country uses a decimal comma, every
   `printf`/`snprintf`/`std::ostringstream`/`strtod` in the program is affected
   and **there is no global switch that turns it off**. That is why the same bug
   came back seven times between 0.9.1 and 0.9.8, each time in one more place:
   ruleset parsing, then number writing, then `serializeDouble` - every base and
   craft coordinate in every save, which is why bases vanished from the globe.
   **Any float that goes to or comes from a file must be formatted and parsed by
   hand** (`amiga_to_string`, `amiga_parse_double_c`, `serializeDouble`). A
   `snprintf` followed by a comma-to-dot fixup is not paranoia - it is the only
   thing that works, and code that does it is evidence someone met this before.

Two things that make the next crash cheap instead of a day: every Guru is logged with its
PC by `native/amiga_trap.c` (armed in `main.cpp`; look for `CPU TRAP` in `sdlmini.log`,
then `wsl python3 winuae/harness/trapmap.py`, which maps the PC and the stack dump to symbols), and a ten-line probe linked exactly like
the game (`C:\temp\oxctest\*.c`, deployed to `Work:` and run from `Work:run`) settles
"toolchain or game?" faster than any amount of reading. Restore `Work:run` to
`openxcom-aga` afterwards — a forgotten probe in `run` looks like a regression.

Two more traps that are the game's code, not the toolchain, and that the patch script fixes:
`Surface::loadImage` runs the filename through `wstrToUtf8(fsToWstr(...))` before `IMG_Load`,
which libnix's wide-character conversion turns into garbage; and a missing sound CAT aborts
mod loading, so one absent data file reads as a port bug.

The port writes only to `Work:` (`PROGDIR:`), never to the boot hardfile — and since
2026-08-16 that is enforced rather than trusted: every `winuae/*.uae` config mounts the
hardfile `ro`. AmigaOS boots fine write-protected (`T:` and `ENV:` are in `RAM:`).

Flags that are not negotiable (all inherited from the OpenTTD port, each cost real time to find):
`-O1` (not `-O2`: it breaks C++ exception unwinding), `-mcpu=68020 -msoft-float`
(not `-m68040`: it silently selects the 68881 multilib), never `-lpthread` or `-lc`
(they pull newlib in beside libnix), `-std=gnu++11` (yaml-cpp 0.6.3 needs it), RTTI on
(the game uses `dynamic_cast`).

## Running it

WinUAE 2.8.1 lives in the OpenTTD repo (`I:\GITHUB\Amiga_OpenTTD\tools\winuae281\winuae.exe`).
**Always launch it as `winuae.exe -f <config>` with `use_gui=no` in the config** — anything else
opens the configuration window and waits for a human. `winuae/harness/run-oxc.ps1` does this and
waits for `winuae/work/oxc.log`. The HDF's User-Startup runs `Work:run` from the shared folder,
so binaries and data are swapped on the host and the HDF image is never touched (it is mounted
read-only, so it *cannot* be).

**Never `Stop-Process -Name winuae`.** Other Amiga machines run from the same `winuae.exe`
(other agents, the author's own sessions) and killing by name shoots them down mid-run. Kill the
PID you started, or use `winuae/harness/kill_ours.ps1`, which matches the command line against
`oxc-*.uae` and prints what it deliberately left alone. `capture_ours.ps1` picks the window the
same way.

**Never synthesise mouse or keyboard input on the host** (`mouse_event`, `SetCursorPos`,
`SendInput`, the retired `click_*.ps1`/`drive_*.ps1`). WinUAE drops the mouse trap silently
and the clicks then go to whatever the user has on screen — it once posted a half-written
forum message from their browser. Drive the game from **inside** the guest instead: sdlmini
reads `Work:autoinput.txt` and feeds its own SDL event queue (`sdlmini_autoinput.c`).
Screenshots via `capture_ours.ps1` (PrintWindow) are fine — they take control of nothing.

`winuae/oxc-aga-ram256.uae` is the same machine with 256 MB of Z3 fast RAM. It exists to answer
"is this symptom just memory pressure?" in one run — it is a diagnostic, never a target machine.
The real targets are `oxc-aga.uae` and `oxc-rtg.uae` at 32 MB.

## What this project is

A native AmigaOS 68k port of **OpenXcom** (X-COM: UFO Defense + **X-COM: Terror from the Deep**),
targeting *classic* hardware (020+, AGA and RTG), not PiStorm/Vampire/Emu68.
It is the follow-up to the same author's `openttd_amiga_68k` port, and deliberately reuses that
port's platform layer.

`PORT_RESEARCH.md` is the authoritative research/plan document — read it before proposing work.
Key conclusions it records (do not re-derive them):

- Upstream is https://github.com/SupSuper/OpenXcom (mirror `OpenXcom/OpenXcom`). **No tagged release
  ever contained TFTD** — the last tag is `v1.0` (2014-06); everything after is nightly-only.
- TFTD becomes playable only from commit `f1e6f01` (2015-08-03, "Summon the Kraken!", adds the TFTD
  ruleset). The chosen practical base is `00fbacde` (2016-06-27) — TFTD matured, upstream activity
  then goes near-dormant.
- Vanilla upstream master is **not** bloated (~175k LOC, still SDL 1.2, still ~C++03). The "modern
  bloat" is the separate **OXCE** fork (`MeridianOXC/OpenXcom`) — do not base work on it.
- yaml-cpp cannot be avoided; rulesets are the engine core since 0.9.
- Rebuilding TFTD on top of `v1.0` is *more* work than debloating the 2016 base (the v1.0→Kraken
  diff is ~82k lines across 562 files — 14 months of unrelated development, not a TFTD delta).

## Porting constraints that shape every code decision

- **Target CPU is plain 68020, no FPU.** Do not introduce `float`/`double` in ported code; convert to
  fixed-point (+ sin/cos LUTs). The FP hotspots are `src/Engine/` and `src/Geoscape/` (spherical
  coordinates, dogfight, trajectories); `src/Savegame/` and `src/Ruleset/` FP is mostly YAML parsing
  and can be converted at load time. 040/060 FPUs are partly trap-emulated, so FPU code is a
  pessimisation, not an optimisation.
- **SDL is replaced, not ported.** Video (c2p for AGA, RTG, and windowed WB mode with palette
  negotiation) and audio come from `openttd_amiga_68k`. That code is MIT — the only obligation is a
  credit line in `README`; nothing else needs to be bundled.
- **Audio is deliberately primitive**: Paula directly, 4 channels (2 music streamed from disk,
  2 SFX), ADPCM 22 kHz instead of OGG. When all SFX channels are busy, steal one with a fast
  fade-out rather than dropping the new sound. No mixer — CPU is the scarce resource and this is a
  turn-based game.
- **Debloat rather than reimplement**: OpenGL (`src/Engine/OpenGL.*`), `Zoom.*`/scalers and the
  video option surface are removable; force 320x200 8bpp. Upstream has exactly one thread
  (`src/Menu/StartState.cpp`, resource loading) — trivial to serialise.
- **RAM is the top unresolved risk**, ahead of CPU speed. Measure real RSS of the base build on PC
  for both UFO and TFTD before committing to a hardware floor.
- TFTD needs PC game data; the Amiga never had a TFTD release.

## Testing / iteration setup (planned)

WinUAE 2.8 with a WB 3.x HDF and RTG, plus a shared folder next to the HDF so binaries can be
swapped without touching the HDF image. Autostart the build and log to a file so runs can be checked
without a human in the loop; ask the user for feedback only when a log cannot answer the question.
Agent-driven test runs may use JIT / max speed for turnaround; final performance calibration must be
done **without** JIT (JIT distorts results by roughly -70% slowdown when disabled) and cross-checked
with sysinfo.

## Working style for this repo

- Take backups/branch points before each layered change — the port proceeds in layers
  (debloat → platform layer → audio → FPU removal), and each layer must stay independently bisectable.
- Prefer simple, Amiga-friendly non-FPU C++ over clever generic code; upstream idioms are C++03 and
  the m68k-amigaos GCC toolchain should not be pushed past that.
