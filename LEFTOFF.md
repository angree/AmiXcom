# LEFTOFF — hand-off for the next session (written 2026-08-19 night, after v0.6.0 build)

Read this, then `CLAUDE.md` (rules), then the top entry of `PROGRESS.md` (proofs).

## PLAN RYSOWANIA BITWY (2026-08-19 rano, zatwierdzony przez usera) - AKTUALNA ROBOTA

Pomiar (sonda us:/us2:, E-clock, 040/40-ekw. -80%): pelne zlozenie 160-240 ms
= blit 110-126 (70%; 426-499 blitow, 463-549 tys. px PRZETWORZONYCH na 64 tys.
ekranu, gcc -O1 robi ~7 instr/px przez stos) + logika per kafel 50-115
(386-1169 kafli, ~100-130 us/kafel nawet pusty, 523-602 getFrame = 2x std::map).
Scroll 8 fps = box naprawy (pas u kursor-kolumny) = 82% ekranu -> drawTerrain
150-190 ms/krok + ksiegowosc cache 22 + ui 35 + flip 13. Kursor 58 ms (kolumna,
130 kafli). Staly koszt kazdej klatki: mapa->bufor 6 ms (colour-key 0 na
Surface mapy = sciezka per-piksel), bufor->ekran diff 6, c2p+fill 5.
Siec: PCK to RLE (0xFE skip/0xFF end); oryginal rysowal z run-ow, nigdy nie
dotykal przezroczystych px. OpenXcom dekoduje do plaskich 32x40 = zrodlo kosztu.

Kolejnosc (user: "1 a-d, potem e, potem dopiero 2", test usera miedzy krokami,
jedna zmiana na build, backup przed krokiem):
 1A. [x] (0.6.1) Sprite'y jako listy run-ow w blitNShade (C): tabela per wiersz
        (n, (x,len)..), budowana leniwie przy 1. blicie, kasowana przez kazda
        sciezke zapisu Surface (setPixel/clear/blit-dest/draw*/load*/lock).
        Kod: C:\temp\amiga_oxcom\spans.py (blok 6ab). Zysk: blit 110 -> ~35-40.
 1B. [x] (0.6.1, niedokonczone - patrz 1B2) Scroll: osobne boxy (pas, stary kursor, nowy kursor) zamiast unii;
        kursor bez pelnej kolumny (= stary pkt 0a: sprite + 1-2 kafle nad nim).
        Zysk: krok scrolla 150-190 -> ~30-40 ms, kursor 58 -> ~15.
 1B2.[ ] Kursor: box = DOKLADNY prostokat sprite'a kursora (32x40 na kafel,
        stara+nowa pozycja, poziomy 0..vl), bez otoczki 3x3 i bez kolumny;
        scalanie boxow tylko gdy unia nie marnuje >25%. Powod: przy krawedzi
        kursor styka sie z pasem scrolla -> unia 73% ekranu = stan sprzed 1B.
 1F. [x] (0.6.1) Memo visible() - krok byl 2-3 s przy ukrytych obcych w stozku
        (canTargetUnit: do 37 promieni na kazdego niewidocznego, 3-4x na krok).
 1C. [ ] Logika per kafel: filtr Y 3 wysokosci -> 1 + 24 px; szybki continue
        dla pustych kafli (pietra!); Surface* cache w MapData zamiast
        SurfaceSet::getFrame (2x std::map); wskazniki CURSOR/SMOKE/FLOOROB
        raz w Map::init; sonda per kafel (skad 100 us na pusty kafel?).
        Zysk: logika 50 -> ~25.
 1D. [ ] Surface mapy bez colour-key -> memcpy: -4 ms na KAZDEJ klatce.
 1E. [ ] Leniwe przesuwanie 7 nieaktywnych faz przy scrollu: -15 ms/krok.
 2.  [ ] Asm (vasm, jak c2p): amiga_span_blit(src,dst,spans,rowoff,rows,
        spitch,dpitch,lut) dla blitow BEZ obcinania w X (reszta w C), 68020,
        raz na sprite; przelacznik C/asm + suma kontrolna klatki. Zysk: blit
        ~35 -> ~15. Asm NIE pomaga na logike/scroll - to algorytm.
 Potem: sprzatanie sond (us:/us2:/prof:/cache:/sig:/seed:/frameprof: ...).
OBSERWACJA (raz, pilnowac): CPU TRAP 7/TRAPV w turze AI, stos:
UnitWalkBState::think -> calculateFOV -> visible -> canTargetUnit ->
distanceSq(bool) - soft-float przepelnienie, handler exit(20). Szczegoly
LISTA-ROBOT na gorze.
Szacunek uczciwy: scroll gesty 125 -> 60-70 ms (8 -> 14-17 fps), pelne
zlozenie 160 -> ~70-80 ms. Nie 5x; 2-2.5x.

## Where the port stands (2026-08-19, 0.6.0 built, release pending user test)

**Released**: github.com/angree/AmiXcom - v0.1.0..v0.5.7 (code without
ROM/HDF/CGX-headers/game data; releases without X-COM data). Bar shows
"AmiXcom 68K 0.5.7" (version.h patch in apply-amiga-patches.py is the ONE source).

**New since 0.5.0**: 0.5.5 keyboard fix (raw-key lookup was MISCOMPILED at
-O1 - every key typed 'r'; direct 128-entry map at optimize(0)) + title
credit "PORT MADE BY GRZEGORZ KORYCKI". 0.5.6 loading splash: 6 intro/
backgrounds baked into the EXE (gen_splash.py -> amiga_splash_data.c),
progress bar linear vs real time (ticks all through Mod loading incl. a
YamlTickHook inside yaml-cpp Stream::get for the language parse), palette
blanked at OpenScreen, Intuition pens fixed at indices 0/15/17/19.
Swap intro/*.png -> next build re-bakes automatically.

**0.5.7**: geoscape no longer freezes 10-30 s on mouse movement. Motion
events are coalesced in the sdlmini queue (queue_push) - one move used to
cost 370-1500 ms with an FPU present (Globe::cartToPolar -> the 68881
flavour of mathieeedoub*.library) and they piled up on each other. Full
diagnosis and numbers: PROGRESS.md top entry. Also in 0.5.7: an
experimental hardware-FPU build (`AMIGA_FPU=1 build.sh`, ships as
openxcom-aga-fpu, title bar says "0.5.7 FPU") - user measured no real
difference in battle, kept for testing only; opaque Workbench icons
(build/mkicon.py, OpenTTD icon format); autostart of the game removed
from Work:run (old one kept as Work:run.autostart) - binaries are
launched from Workbench icons, so oxc.log stays empty and the probes
land in sdlmini.log instead.

**0.6.0 (released 2026-08-19)**: battlescape frame cache + options.cfg
migration (`amigaCfgVersion`: forces battleFireSpeed 12 / battleScrollSpeed 16 /
amigaAnimMs 100 once on old files). Idle 3.8 -> ~35 fps, cursor
~9-13, shot ~9 (gameTimer-bound: 100 ms per bullet step), scroll 8-13, walking
~6 (FOV logic). Full story + numbers + the one known gap (dense map: dirty
tile box = whole column, should be sprite + 1-2 tiles up) in PROGRESS.md top
entry. Design in one line: 8 cached pictures (one per animation phase), a
per-phase dirty TILE grid + screen box, producers mark tiles, repair =
one clipped drawTerrain, seed/propagate to the other 7 phases after a full
compose or a scroll. All of it is the "6z" block in apply-amiga-patches.py.
`amigaAutoBattle: 1` (options.cfg) boots straight into a battle. Autoinput
is gated behind `Work:autoinput.on` (absent = never reads a script).
Reference machine is now -80% (all older numbers were -70%).

**Performance today** (040/40-class = 68020, no JIT, **-80% throttle** -
the user's calibration since 0.5.7, all older numbers were at -70%;
proofs in PROGRESS.md):
- Battle save 45-60 s -> ~8 s; battle load ~90 s -> ~20-25 s (probes
  `save:`/`load:` in oxc.log show the phase split; parse ~11 s dominates load).
- Globe 3D ~10x: integer Q1.14 geometry + precomputed vertex trig, shadow
  tables from `data/common/earthfix.dat` (gen at build: build/gen_earthfix.py -
  MUST ship in releases), 2x2 shadow, vector radar circles, 16.16 XuLine,
  one-jump dogfight zoom, flat sun-shaded WATER polygons (in TFTD the globe
  polygons are the ocean; option amigaFlatGlobe, 0 = old textured).
- Geoscape idle 50 fps; battle as at 0.3.0 (step ~0.3 s, render 10-16 ms).
- RAM: 48+2 MB works, less does not (user-measured on Workbench gauge).
- Boot: Work:run detaches via `Run <NIL: >NIL:` -> CLI closes, WB visible.
  run.normal = plain boot; autotest mode: `Copy Work:autotest.txt
  Work:autoinput.txt` in run (boot drives menu->battle->autosave->F5->F9).

**THE PLAN** - remaining (details LISTA-ROBOT.txt):
0a. BATTLE CACHE, known gap (user is right, do this next in the cache): on a
   dense map a dirty tile's screen box is its whole column up to the view
   level (~110 px) because every level has content -> 3x3 halo x column =
   ~15% of the screen per change; repair cost scales with map density, not
   with the change. Correct box = the tile's sprite + the 1-2 tiles ABOVE it
   in iso order (whose sprites overlap), clipped - not the column. The naive
   "draw only grid tiles" filter left holes (tall objects 2-3 tiles behind on
   a higher level) and flickered - reverted; that is not the fix, the box is.
   Ceiling after that: ui+flip (map blit to screen + c2p) = ~45 ms/frame at
   -80% -> ~20 fps for anything that moves.
0. MEASURED IN 0.5.7, NOT FIXED - both are the biggest waits the user hits:
   a) New Battle OK -> briefing = `bgen.run` 9.2 s unthrottled (~35 s for the
      user). `recalcFOV` 3.0 s (runs the full tiles=true FOV for ALIENS too -
      they only need our fast tiles=false path), MCD+PCK terrain reload 2.5 s
      (byte-at-a-time istream, same loadPck as the 110 s startup), initMap +
      initUtilities 2.5 s (14k separate `new Tile` + as many Pathfinding nodes).
   b) Main menu -> New Battle screen = ~17 s unthrottled (~35 s for the user):
      `NewBattleState::load()` parses user/xcom2/battle.cfg (27 KB of dense
      YAML) and rebuilds base + 30 soldiers + all mod items/research EVERY
      time. Cheapest fix: keep the built SavedGame and reuse it on re-entry.
   c) `Globe::cartToPolar` still double trig - with an FPU one mouse move is
      still expensive, it just no longer accumulates. Q1.14 + LUT like the
      rest of the globe.
1. GAME START ~3 min: loadVanillaResources+loadBattlescapeResources
   (screens/PCK/CAT) = ~110 s of it (measured via splash probes) - speed up
   loadPck/loadScr/loadCat; rulesets ~60 s; language parse ~20 s.
2. Save-load: load parse ~11 s (hand parser for battleGame - our format);
   dziwne 5.5 s/region w sanityzacji regionow (zmierzone, niewyjasnione).
3. Cleanup TEMP probes (perf:/slow frame/step:/fov:/map:/globe:/load:/
   save:/splash:/geo:/frameprof:/bgen:/gmap:/newbattle:/prof:/cache:/sig:/
   seed:). frameprof: fires on every frame >=300 ms.
4. Save-list dates show "????" (cosmetic); guard in-game F12 screenshot.
5. MUSIC (SFX work; Paula/ADPCM streaming from OpenTTD port not wired),
   RTG test, 32 MB RAM reduction (now needs ~50 MB).
6. Maybe: geoscape span fills, AMIGA_GLOBE_MIN_MS 1000->250, markers trig-out.

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

## NEXT STEP AFTER COMPACTION: dirty rectangles (user-approved)

Most of the plumbing already exists - this is a TRACKING task, not a c2p task:
- `amigagfx_blit(x, y, w, h)` (amiga_gfx.c) already converts ONLY the given
  rectangle via Kalms' `c2p_rect` (x and w snapped to the 32-pixel grid
  internally; RTG path does per-row memcpy). Full-screen = 320x200 call.
- sdlmini already routes `SDL_UpdateRect(s)` to it; the game however only ever
  calls `SDL_Flip`, which converts the full screen every frame.

Plan (one change per build, backup first, as always):
1. In sdlmini_video.c track a dirty union (or a small list, 8-16 rects) of
   everything written to the SCREEN surface (`s_screen`): blit8 dst==s_screen,
   SDL_FillRect dst==s_screen, SDL_LockSurface(s_screen) -> whole screen dirty
   (direct pixel writes - Surface::draw paths), SDL_SetColors -> whole screen.
2. SDL_Flip: convert only the dirty rects (amigagfx_blit per rect), clear list.
   Empty list -> skip the c2p entirely (but still count the frame).
3. Watch out: the game "clears + redraws everything" per frame, so the naive
   union is the whole screen again. The win comes from step 4:
4. Teach Game::run (patch script) not to clear/re-blit states when NOTHING
   invalidated since the last frame: upstream Surface::_redraw flags exist;
   cheapest correct proxy measured today: on the geoscape only the FPS counter
   and blink markers change between globe redraws; in menus nothing changes.
   Alternative smaller first step: skip the FULL c2p when the frame's pixel
   content is unchanged (compare a per-frame write counter in blit8/FillRect).
Expected: menus/Bases at c2p-limited rates; geoscape beyond 40 fps; battle
unchanged (Map has its own path).

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
