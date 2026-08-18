# Amiga OpenXcom - progress log

Newest first. Facts and measurements only; plans live in `PORT_RESEARCH.md`.

## 2026-08-18 (przedpoludnie): 0.5.6 - loading splash z paskiem postepu

Wydane jako v0.5.6. Boot->menu trwa ~3 min na 040/40 -70%; teraz zamiast
czarnego ekranu jest splash: losowe z 6 tel z intro/ (320x184, konwersja
na PC przez build/gen_splash.py do 8-bit chunky+paleta, WPIECZONE w
binarke jako amiga_splash_data.c ~360 KB), logo AmiXcom -2 px od krawedzi
(przyciete alpha-bbox, clipping), fade-in paleta, pasek (stalowy niebieski
253 na czarnym pasie), fade-out 0.5 s przy przejsciu do menu.

Mechanika (native/amiga_splash.c + sdlmini): splash rysuje sie w
SDL_SetVideoMode; SDL_Flip i paleta ekranu STLUMIONE na czas ladowania
(gra rysuje swoj "Loading..." w prozni); pas paska odtwarzany z prywatnej
kopii przed kazdym blitem (gra mazie po chunky); SDLmini_SplashFinish()
(StartState) przywraca palete gry + pelny dirty. Paleta: peny Intuition
zarezerwowane na ICH PRAWDZIWYCH indeksach z g_screen_pens (0 trim,
15 tekst paska, 17 tlo paska = zolty jak w grze, 19 gadzet) - pasek
tytulowy identyczny na kazdym tle; cala paleta CZERNIONA w amiga_gfx
zaraz po OpenScreen (koniec szarego blysku Intuition).

Pasek liniowy wzgledem czasu (odchylka 13 pkt, najwiekszy przestoj
74 s -> 14.6 s) - tick per: plik rulesetu (5..37), region (39), ekran
SCR/BDY/SPK (40..57), zestawy (58), CAT dzwiekow (59..70), PCK jednostek
(71..76), sorty (77-79), fonty (80), sprite/dzwiek extra (81..88), jezyk
88..98 TYKA W TRAKCIE PARSOWANIA (hak YamlTickHook w yaml-cpp
Stream::get co 8 KB). Wszystko wymierzone sondami "splash: X% at T ms"
(TEMP, do sprzatniecia).

Pomiar przy okazji: loadVanillaResources+loadBattlescapeResources
(ekrany, PCK, CAT-y) = ~110 s z ~180 s startu - GLOWNY kandydat na
przyspieszenie ladowania gry. Dithering FS wyprobowany i COFNIETY
(user: brzydkie ziarno w lores; zostaly gladkie przejscia).

## 2026-08-18 (rano): 0.5.5 - klawiatura naprawiona

Pisanie tekstu wstawialo zawsze 'r' (czasem '6') niezaleznie od klawisza.
Log sondy pokazal dowod: `key raw 0x25 idx 36 entry.raw 0x13` - szukanie
'h' ZWRACALO wpis 'r'. Petla porownujaca tablice klawiszy w
sdlmini_events.c byla miskompilowana przez gcc 6.5 przy -O1 (ta sama
rodzina co Mod.cpp). Fix: lookup jako bezposrednia mapa 128 wpisow,
init z volatile, __attribute__((optimize(0))). Potwierdzone przez
uzytkownika na prawdziwej klawiaturze. Wydane jako v0.5.5 (+ napis
"PORT MADE BY GRZEGORZ KORYCKI" male czcionka na title screen; asset
0.5.0 podmieniony z napisem i poprawka notek: SFX dzialaja od 0.1.0,
brakuje MUZYKI, nie dzwieku).

## 2026-08-17/18 (wieczor+noc): 0.5.0 - zapis 8 s, odczyt ~20 s, glob 3D ~10x

Pomiary na maszynie referencyjnej (68020, JIT OFF, cpu_throttle -70%,
`oxc-aga-nojit-040-40.uae`), sondy w oxc.log. Wydane jako v0.5.0
(github.com/angree/AmiXcom); po drodze wewnetrzne 0.3.5/0.3.6/0.3.7.

**Zapis bitwy 45-60 s -> ~8 s** (sonda `save: build/emit/write`):
- yaml-cpp convert.h: konwersje skalarne bez std::stringstream (kazda
  konstrukcja strumienia = koszt ms na 020); recznie 64-bit parse dla
  long long (strtoul jest 32-bit - rng seed wywalal load "bad conversion").
- yaml-cpp memory.cpp: small-to-large merge puli wezlow (budowa drzewa
  bottom-up byla kwadratowa; 17 KB save = 16.9 s buildu NA JIT).
- Wlasny writer YAML (native/amiga_yamlout.h) zamiast YAML::Emitter
  (emit 23-25 s -> 3 s); plik pozostaje zwyklym YAML-em.
- Zapis battleGame bez drzewa Node: saveFastAmiga() w BattleUnit/
  BattleItem/Node/AIModule/BattleUnitStatistics/SavedBattleGame pisza
  "klucz: wartosc" wprost do stringa (build 15 s -> 2-4 s). UWAGA FORMAT:
  pola tileIndexSize itd. MUSZA byc znakami ("\x04") bo loader czyta
  as<Uint8> (semantyka ZNAKU); binTiles w apostrofach (goly 95 KB plain
  scalar = kwadratowy skaner yaml-cpp - load "wisi").
- gcc 6.5 ICE: Node::AssignData/set_data wywalaly kompilator przy -O1 w
  KAZDYM pliku z yaml.h - 22 pliki (cala sciezka save/load, Mod.cpp) byly
  na -O0 od poczatku portu. Fallback build.sh: -O1 -fno-inline (attrybuty
  optimize(0) na 2 funkcjach); Mod.cpp MUSI zostac -O0 (miscompilacja na
  -O1 = czarne palety za menu - udowodnione bisekcja).

**Odczyt zapisu bitwy ~90 s -> ~20-25 s** (sondy `load:`):
parse yaml 31->11-13 s, geoscape 1.3 s, bitwa 3-4 s, mapres (MCD) 4.5 s,
FOV ~3 s. Najwiekszy fix: GeoscapeState budowany pod bitwa liczyl w
konstruktorze CALY glob - 36.8 s: cachePolygons (teraz leniwe, pierwsze
draw()) + _earthFix (tabele cienia; patrz nizej). Zostalo: parse 11 s
(pomysl: reczny parser battleGame - format jest nasz wlasny).

**Glob 3D ~10x** (uzytkownik: obrot 1.5 s, "zoom in 5-7 s masakra"):
- earthfix.dat: tabele normalnych cienia (6 zoomow x 256x200 Q1.14)
  liczone na PC przy buildzie (build/gen_earthfix.py, 1.8 MB, walidacja
  naglowka+promienia, fallback na liczenie). Bylo: 307k soft-double sqrt
  = ~5 s przy KAZDYM pierwszym wejsciu na dany poziom zoomu.
- cachePolygons: sin/cos wierzcholkow policzone RAZ (tablica Sint16 Q14);
  przeliczenie = 4 trig (srodek) + mnozenia 32-bit - cala geometria na
  intach Q1.14, promien Q4 (1/16 px). Bylo 650-1010 ms na obrot/zoom.
- Cien 2x2: iloczyn skalarny raz na blok, paleta per piksel (brzegi
  dokladne). Bylo ~110 ms na przerysowanie.
- Kolka radarow: czysta algebra wektorowa P=C cosr+(N1 cost+N2 sint)sinr
  rotowana tozsamosciami do view-space - 12 trig na okrag zamiast ~250
  (asin/atan2/polarToCart per segment). Do tego dedup promieni przy
  hoverze (bylo ~15 identycznych okregow = 700 ms na przerysowanie).
- XuLine (granice, kolka): krok 16.16 fixed-point zamiast double+castow.
- Dogfight: zoom jednym skokiem zamiast ~10 krokow animacji (kazdy krok
  = pelne przeliczenie; dojscie do walki bylo 30-60 s).
- Plaskie poligony cieniowane wg slonca zamiast tekstur (opcja
  amigaFlatGlobe, domyslnie ON; 0 w options.cfg = stare tekstury).
  W TFTD poligony globu to WODA - teksture traci woda, lad byl plaski.

**Dirty rectangles w sdlmini** (bez widocznego skoku fps w lores - c2p
to bylo tylko ~7 ms - ale 82-100/100 klatek idzie zupelnie bez c2p;
kluczowe pod przyszly hires laced): unia dirty + diff-blit 32-bajtowymi
komorkami pelnoekranowego blitu Screen::flip; Screen::clear nie zeruje
juz fizycznego ekranu (zerowanie wymuszalo pelny c2p co klatke).

**Start**: Work:run odpala gre przez `Run <NIL: >NIL:` - CLI sie domyka,
LoadWB z konca startup-sequence pokazuje Workbench z licznikiem RAM.
Zmierzone przez uzytkownika: 48+2 MB dziala, mniej nie.

**Tryb autotestu**: `Copy Work:autotest.txt Work:autoinput.txt` w Work:run
- boot sam przechodzi menu->New Battle->briefing->ekwipunek->bitwa->
autosave->F5->F9 (test save+load bez czlowieka). Powrot: run.normal.

**Lekcje**: TaskStop nie zabija dziecka skryptu-drivera (osierocony bash
wciskal F5/F9 w sesji uzytkownika); run-oxc.ps1 bez -KeepRunning ZABIJA
emulator po wypisaniu loga (6x "czemu sie zamknelo"); heredoc przez
git-bash podwaja backslashe przed cudzyslowem (patch-pythony pisac
Write-toolem); nasz WinUAE to teraz winuae-oxc.exe (kill po nazwie
winuae z innych sesji nas nie trafia).

## 2026-08-17: 0.1.0-0.3.0 wydane; geoscape 5->40 fps; bitwa grywalna (krok 6 s -> 0.3 s)

**Wydania**: github.com/angree/AmiXcom - kod (bez ROM/HDF/CGX/danych gry, .gitignore
pilnuje) + release zipy (binaria+ikony+data/common+standard, bez danych X-COM).
v0.1.0 (wieczor 16.08), v0.2.0 (rano: geoscape), v0.3.0 (popoludnie: bitwa).
Wersja gry z jednego zrodla: patch version.h (OPENXCOM_VERSION_SHORT).

**Nocna lekcja**: "uszkodzona binarka" ktora wieszala kazda wersje = zostawiony
Work:autoinput.txt z klawiszem f12 (gra odtwarzala go po kazdym starcie; f12 w grze
= screenshot = konwersja 8->24bpp = HALT). Kasacja pliku = 8/10 czystych testow.
Suma md5 binarek identyczna przed/po - build deterministyczny.

**Geoscape 5 -> ~40 fps** (pomiary: sondy perf:/globe: w oxc.log):
1. Blity colorkey byly 5 ekranow/klatke (4 warstwy globu + UI). Wariant A: 4 px
   na raz (trick (x-0x01010101)&~x&0x80808080). B: flaga "powierzchnia bez klucza"
   w unused1 -> memcpy. C: cache spanow per powierzchnia w hwdata (runy nie-klucza
   per wiersz; niewazniane w FillRect/Lock/Unlock/SetColorKey/blit-dst). 11->16 fps.
2. GLOWNY zlodziej: SDL_Delay(1) na koncu KAZDEJ klatki (upstream "save CPU")
   zaokraglane w SDLmini_Sleep do 1 tiku = 20 ms; z 20-ms zegarem limiter FPS
   gubil klatki i spal 1-2x na klatke. Fix: opoznienia <=2 ms = no-op. 16->40 fps.
   c2p okazal sie NIE byc problemem (~7 ms/klatke) - uzytkownik mial racje.

**Bitwa: krok 6 s -> ~0.3 s** (sondy slow frame/step:/fov: z rozbiciem):
- fovAll 3.2-3.5 s = pelne FOV KAZDEJ jednostki w 20 kratkach po kazdym kroku,
  w tym raycast odkrywania mapy do ~1700 kafli na jednostke. Naprawy kolejno:
  (1) pelne FOV tylko dla ruszajacego (tiles=false dla reszty), (2) spotting
  po liscie jednostek zamiast enumeracji stozka (enumeracja ~170 ms/jednostke!),
  (3) spotting par: po kroku zmienily sie tylko pary "ktos<->ruszajacy" -
  reszta list nietykana (vu->erase(remove)+addToVisibleUnits, test stozka int),
  (4) przyrostowe odkrywanie (mapa<int,pair<Position,int>> lastDisco_; needRay_
  pomija cele w starym stozku JUZ odkryte - k1korner-peek zachowany bo nieodkryte
  dostaja promien), (5) obroty w marszu = spotting only. Tryby w zakladce AMIGA:
  Fast (krawedzie stozka+przyrost) / Accurate (bez przyrostu; DOMYSLNY - po (3)
  kosztuje tyle samo) / Test (krawedzie+pierscien). Regres "odkrywa mniej"
  z wersji krawedziowej naprawiony powrotem do promienia per kafel + przyrost.
- unitLighting 550->100 ms: addLight na intach (najblizszy pierwiastek
  przyrostowo, wyniesiony przed petle z, 1 lookup/narozn). [Wklad innej sesji
  Claude, przywrocony po jej sprzataniu.]
- render mapy 100 -> 10-16 ms: blitNShade w golym C zamiast ShaderDraw
  (StandardShade/ColorReplace: dolny nibble+off, saturacja 15, gorny nibble
  zachowany/zamieniony; przeskok przezroczystych po 4 px; cien 0 = czysta kopia).
  Timer animacji bitwy: opcja, domyslnie 200 ms (bylo 100 = zadanie pelnego
  renderu 10x/s = nasycenie = 3-6 fps nawet bez ruchu).
- ogien reakcyjny zmierzony <100 ms - NIE byl problemem (teoria obalona sondami).

**Original research**: 1994 robil to tak jak my teraz: LOFTEMPS.DAT = prekalk.
bitmapy 16x16 (LOS/LOF bez geometrii), 1 promien miedzy srodkami kafli tylko do
KANDYDATOW, odkrywanie przyrostowe, przeliczenie tylko ruszajacego. A500 7MHz
wcale nie bylo plynne (tury obcych = minuty); punkt odniesienia = 486.

**Zakladka AMIGA** (OptionsAmigaState w native/oxc-replace/Menu/): pasek ekranu
Amigi (amigagfx otwiera ekran WYZSZY o pasek: 320x211, gra pelne 320x200 pod nim,
mysz 1:1 - a nie zmniejsza pola gry jak OpenTTD), kursor amigowy (domyslny;
Intuition pointer, gra nie blituje kursora), map reveal, tempo animacji.
Tytul paska = SDL_WM_SetCaption -> amigagfx_set_screen_title (zywe SetWindowTitles).

**Gotcha buildowe**: czesc lat nakladajacych sie na te same miejsca nie jest
idempotentna na juz zlatanym pliku (duplikaty deklaracji). Przed buildem:
sh /mnt/c/temp/amiga_oxcom/restore_file.sh Battlescape/TileEngine.cpp itd.
`build.sh clean` zawsze bezpieczny. Pomiar: 20-ms zegar - liczby tylko usrednione.

**Sondy TYMCZASOWE aktywne** (do usuniecia przed nastepnym wydaniem): perf: co 100
klatek (sdlmini_video), slow frame >=300ms (Game.cpp), step: >=100ms
(UnitWalkBState), fov: per pelne FOV (TileEngine), map: co 20 renderow (Map.cpp),
globe: co 50 wywolan (Globe.cpp).

## 2026-08-16 (night, 3) - the "every change makes it worse" evening: it was build.sh

Symptoms over ~2 hours: a globe surface with half its pixels zeroed by a shader
whose input table was proven correct, the ocean vanishing at zoom, an earlier
"colour key lost" on a surface, a build that hung constructing the Geoscape - and
each rebuild seemed to make it worse. None of it was the code being changed.

**Cause: `build.sh` compared only the `.cpp` against its `.o`.** A change to a
HEADER recompiled nothing else. `Globe.h` grew members that evening (cache keys,
`_earthFix`); `Globe.cpp` was rebuilt, but `GeoscapeState.cpp` (which does
`new Globe(...)`) kept the old `sizeof(Globe)`, so the constructor wrote past the
allocation and corrupted the heap - randomly, differently on every run and JIT
setting. Fix: `compile_c`/`compile_cxx` now emit `-MMD -MP` dependency files and
`needs_build()` rebuilds when any listed dependency is newer or missing; all 325
objects were wiped and rebuilt once to seed the `.d` files.

**Second, unrelated trap: black WinUAE windows.** WinUAE 2.8.1 ignores
`win32.posx/posy` in the config and opens where `winuae.ini` remembers
(`MainPosX/MainPosY`). The user dragged a running instance to their second
monitor; with `gfx_api=0` (DirectDraw) every window created there afterwards was
black - for the user and for every capture, PrintWindow and CopyFromScreen alike -
with a perfectly healthy game inside. `run-oxc.ps1` now rewrites those two ini
keys to the primary monitor before each start; `capture_ours_anymonitor.ps1`
exists for the case where it happens anyway.

**Where the code stands** (backup `..._2140_globus-22fps-znany-dobry.zip`):
throttles + fixed-point `drawShadow` + textured land, redraw cap 250 ms, all
rebuilt clean. Measured without JIT after placing a base: `10 draws in 2820 ms over
62 frames` = **22 fps**, redraw ~40 ms (shadow 22, land 14-20). Screenshot
`C:\temp\amiga_oxcom\rb_geo.png`.

**Written but rolled back, to be re-landed one at a time on the clean build:**
`hspan()` span fills with one clip per row and incremental texture wrap
(sdlmini_gfx.c - measured ocean 0 / land 0 ms), `SDLmini_FilledPolygon8` (index
fill), the radar-surface cache (`_radarKey/_radarTime`, redraw only when
projection/hover/bases/crafts change or 2 s passed), and flat sun-shaded land
polygons (dominant texture index darkened 0..5 steps by the normal-sun dot
product; the user wants this - flat colours per polygon, differing by sun angle,
NOT textures). The Python that applied/removed them is in
`C:\temp\amiga_oxcom\*.py` (`gfx_patch*.py`, `radar_patch.py`, `shadepoly2.py`,
`rollback16.py`).

Land colour note, once more: index 16 = (152,172,0) is what TFTD's PALETTES.DAT
says; it has been identical in every run since morning (pixel-compared).

## 2026-08-16 (night, 2) - drawShadow in fixed point: 280 ms -> 22 ms per redraw

Follow-up to the entry below. `CreateShadow` (the day/night shader) now has an
integer twin, `CreateShadowFix`, and the per-pixel normal table is Q1.14
(`CordFix`, three `Sint16`) instead of `Cord` (three doubles). Same decision tree,
same `shade_gradient` table, same palette arithmetic; only the double maths went:

- differences `earth - sun` in Q14 (|d| <= 2), squared to Q28 and dropped to Q24
  each before summing (max 3*2^26, no overflow),
- `(n - 2) * 125` computed in Q16, then C division by 65536 for the gradient
  index - truncation toward zero, exactly what the original `(Sint16)` cast did,
- inside the disc `z` is stored as at least 1, so a rim pixel whose true z rounds
  to 0 in Q14 is still shaded rather than blacked out (`func()` uses `earth.z`
  as the inside test).

`getSunDirection()` stays double (once per redraw). `CreateShadow` (double) stays
for the one call per query in `getPolygonTextureAndShade`. `_earthData` is left
empty on the Amiga: 256x200 x 6 zoom levels x 24 B = 7.4 MB of doubles became
1.8 MB of `CordFix`.

**Measured (JIT off, `oxc-aga-nojit-ram256.uae`, same scenario as before):**

| phase | before | after |
|---|---|---|
| drawShadow | 280 ms | **20-24 ms** |
| ocean / land / radar | 14 / 16 / 18 | 8 / 18 / 20 (unchanged) |
| whole redraw | ~330 ms | **~65 ms** |

With `AMIGA_GLOBE_MIN_MS` lowered from 1000 to 250: `10 draws in 3040 ms over
60 frames` - a redraw every 300 ms, **~20 fps**, and identical at "1 Day"
(`10 draws in 3200 ms over 60 frames`). The visible hitch went from one 330 ms
stall per second to a 65 ms one every 300 ms. Verified visually
(`C:\temp\amiga_oxcom\fix_geo.png`, `fix_1day.png`): terminator gradient, night
side, shaded land all as before; the game ran to 6 Jan with a USO on the map.

**What is left in a redraw** is now `drawRadars` (~20 ms: it clears a 256x200
surface and draws circles), `drawLand` (~18 ms, textured polygons through
`poly_spans` with per-pixel `put()` clipping) and `drawOcean` (~10 ms, a filled
circle drawn pixel by pixel). Each is a span-fill job, not an FP job; together
they are the difference between 20 fps and the ~25 fps blit ceiling. Not urgent.

## 2026-08-16 (night) - the globe was the bottleneck: measured, throttled, 5 -> 18 fps

All numbers below are from `winuae/oxc-aga-nojit-ram256.uae` - **JIT off**, the
config `CLAUDE.md` requires for timing claims (it is new; the old
`oxc-aga-nojit.uae` had only 32 MB and could not load the game).

**The measurement.** `Globe::draw()` is instrumented (patch script, "Globe draw
timing"): it times each phase and compares its own call count against
`SDLmini_flips`, which sdlmini increments once per rendered frame. Reading the
geoscape with the game clock running:

| phase | ms per redraw |
|---|---|
| cachePolygons | 0 (400 when the projection changed) |
| drawOcean | 14 |
| drawLand | 16 |
| drawRadars | 18 |
| **drawShadow** | **280** |
| markers / detail / flights | 0 |

`10 draws in 4160 ms over 21 frames` - a redraw every other frame, **~5 fps**.
In base-placement mode it was far worse: `10 draws in 13660 ms`, because every
mouse move invalidated the globe and paid `cachePolygons()` (400 ms) and
`drawRadars()` (250 ms) again.

**Why drawShadow costs 280 ms.** Disassembling it (`Globe::drawShadow`, 2306
bytes with the shader inlined) shows the per-pixel loop calling the
double-precision soft-float routines **26 times**: 9x `__cmpdf2`, 4x `__muldf3`,
4x `__adddf3`, 1x `__subdf3`, 4x `__floatsidf`, 4x `__fixdfsi`. Every one of
those is a libnix stub that `jsr`s into Kickstart's `mathieeedoubbas.library`.
At 256x200 that is **~1.3 million ROM calls per globe redraw**. The user's guess
("soft floats") was right, and so was the second one ("drawn more often than it
needs to be") - just not literally every frame.

**Two throttles (this entry's change, no maths touched yet):**

1. **Hard cap of one full globe redraw per second** (`AMIGA_GLOBE_MIN_MS`,
   defined in the Globe.cpp marker-include patch). `Globe::draw()` returns early
   if the last redraw was less than that ago, *leaving `_redraw` set* so the
   request is serviced later rather than lost, and without clearing the surface
   so the previous image stays up. The cap is deliberately unconditional: the
   geoscape got worse the faster the clock ran, and this makes time
   acceleration free.
2. **`cachePolygons()` only when the projection actually changed.** New members
   `_cacheLon/_cacheLat/_cacheRadius/_cacheValid` (Globe.h patch, seeded in the
   constructor) record what `_cacheLand` was projected for; `draw()` re-projects
   only when centre longitude, latitude or radius differ. Members rather than
   function statics on purpose - a new game builds a new Globe, and a stale
   "still valid" would leave the land unprojected.

**Result, same machine, same scenario:**

| | before | after |
|---|---|---|
| geoscape, clock running | `10 draws in 4160 ms over 21 frames` = **5 fps** | `10 draws in 10300 ms over 183 frames` = **17.8 fps** |
| at "1 Day" time acceleration | worse | unchanged: `10 draws in 10140 ms over 180 frames` |
| redraw interval | every ~2 frames | exactly 1 s, at any game speed |

Verified visually (`C:\temp\amiga_oxcom\throttle_geo.png`, `throttle_1day.png`):
the globe still renders correctly, and at "1 Day" the game ran five days forward
and raised an "ALIEN SUB-1 Detected" interception dialog.

The remaining ~300 ms redraw still eats about a third of every second, which is
why it is 18 fps and not the ~25 fps blit-only ceiling. That is what the
fixed-point work below is for.

**Next (the point this leaves open): drawShadow in fixed point.**
`CreateShadow::getShadowValue` computes the squared distance between two unit
vectors, scales it by 125, clamps, and indexes a gradient table - all of it fits
in integers. `_earthData` is a `std::vector<std::vector<Cord> >` with one Cord
(3 doubles = 24 bytes) per pixel per zoom level: 256x200 x 24 x 6 zoom levels is
**~7.4 MB of doubles**, so converting it to 16-bit fixed point is worth roughly
6.5 MB of RAM as well as the speed. Expect 280 ms -> 20-30 ms; then
`AMIGA_GLOBE_MIN_MS` can come down from 1000.

**Still open, unrelated:** the keyboard. Real (not injected) keypresses produced
`event: key raw 0x13 down -> sym 54`, but the compiled table in the binary maps
raw 0x13 to 114 (`r`), and 54 is `SDLK_6` - which matches the user's report that
typing produces only "6". Either `lookup()` returns the wrong entry or the log
line itself lies (this libc has form: `CLAUDE.md` rule 4). The log now prints
the table index, the matched entry's own `raw`, the sym, and `sizeof(AmigaKey)`
on three short lines instead of one long one. It needs a human at the keyboard:
autoinput's `key` command injects at the SDL level and bypasses the IDCMP path
entirely, and synthesising keys on the host is forbidden.

## 2026-08-16 (late) - the whole game runs: Geoscape, base, and the Battlescape

The "globe land textures are wrong" bug was not a bug in the port. **The data in
`data/UFO/` is TFTD's**, and the active mod was `xcom1` (UFO). Proof, in order:

- The Amiga's sampled texture bytes for the first land polygons
  (`69 69 68 69 68 69 53 69 69 68 68 54`) are **byte-identical** to what the host
  reads at the same offsets of `TEXTURE.DAT` frame 34 - so `SurfaceSet::loadDat`,
  the `SurfaceSet` copy constructor and `AmigaIFStream` are all correct.
- The screen palette matches `GEODATA/PALETTES.DAT` palette 0 at **16/16** sampled
  indices (`Palette::palOffset(i) = i*774`, no header skip) - the palette path is
  correct too.
- Rendering all 39 `TEXTURE.DAT` frames on the host with that palette
  (`C:\temp\amiga_oxcom\texsheet.png`) shows 39 **underwater** tiles; every frame
  uses only palette blocks 3, 4, 6, 12, 13, which are all blue in that palette.
- `data/UFO/UNITS` holds `AQUA.PCK`, `BIODRON.PCK`, `CALCIN.PCK`, `DEEPONE.PCK`,
  `GILLMAN.PCK`; `data/UFO/TERRAIN` holds `ATLANTIS.MCD`, `ASUNK.MCD`;
  `data/UFO/GEOGRAPH` holds `UP001.BDY`...`UP112.BDY`. Those are TFTD files.
  `PALETTES.DAT` is 2322 bytes = 3 palettes (UFO's has 5).
- `data/TFTD/` contained only OpenXcom's placeholder `README.txt`, and
  `user/options.cfg` had `xcom1` active. `standard/xcom1/metadata.yml` says
  `loadResources: [UFO]`, `standard/xcom2/metadata.yml` says `[TFTD]`.

**Fix (data placement, no code change):** copied `data/UFO/*` to `data/TFTD/`
(the UFO copy is left in place; nothing was deleted) and set `xcom2` active /
`xcom1` inactive in `user/options.cfg` (old file kept as `options.cfg.bak-xcom1`).

**Result - the port plays TFTD end to end.** Verified in one session, each step
screenshotted in `C:\temp\amiga_oxcom\`:

| step | evidence |
|---|---|
| main menu, correct palette | `tftd_menu.png` |
| New Game -> difficulty -> Geoscape: continents, textured ocean, terminator, year 2040 | `tftd_geo.png` |
| clicking land: "X-Com Aqua-Facilities cannot be built on land" (correct TFTD rule) | `tftd_base1.png` |
| clicking ocean: "Base Name?", typed via autoinput | `tftd_base2.png` |
| base placed, clock running (12:06:50), radar circle drawn | `tftd_base3.png` |
| base view: "amiga", South Atlantic, $4,139,000, facility grid, full menu | `tftd_baseview.png` |
| New Battle -> TFTD "MISSION GENERATOR" (Survey Ship / Triton / Atlantis / Aquatoid) | `tftd_nb3.png` |
| briefing "ALIEN SUBMARINE ASSAULT" (map generation succeeded) | `tftd_battle1.png` |
| inventory paperdoll, aquanaut "Donal Walsh" | `tftd_battle2.png` |
| "TURN 1 / SIDE X-Com" | `tftd_battle3.png` |
| **Battlescape**: Triton on the seabed, aquanauts, full tactical UI | `tftd_battle4.png` |
| unit walks out of the sub; TUs spent, selection box follows | `tftd_battle5.png` |

No `CPU TRAP` anywhere along that path.

**Harness fix.** `capture_ours.ps1` used `Process.MainWindowHandle`, which with
`-log` points at WinUAE's console window whenever that got focus last - one
screenshot came back as the boot log. It now enumerates the process's visible
top-level windows and picks the one whose title starts with "WinUAE"
(the console's title is the exe path), falling back to the old behaviour.

**Still open:** performance has not been measured (JIT was on for all of this),
sound/music are silent by design so far, 32 MB is still not enough, and the
temporary diagnostics from the previous entry are still compiled in.

## 2026-08-16 (evening) - the Geoscape draws; the new-game crash was a null Music

**New-game TRAP 4.** `CPU TRAP 4 at PC 0xnnnn0000` after the difficulty OK. The
trap handler now records the USP (the crashed task's stack; the a7 the movem
saw was the supervisor stack) and dumps 512 bytes of it, and
`winuae/harness/trapmap.py` (run in WSL) maps every stack word that lands in
the text hunk to `symbol+offset` via `m68k-amigaos-nm` - a poor man's
backtrace. It said `Mod::playMusic+0x13e` under `GeoscapeState::init()+0x1e2`,
and the disassembly there is `movea.l (a0),a0; lea 16(a0),a0; jsr (a0)` -
a virtual call through a NULL object: `music->play(loop)`. Cause: the port
builds with `__NO_MUSIC`, so `Mod::loadMusic` never fills `_musics`, and
`Mod::getMusic("GMGEO1")` returns 0 (`getRule` returns 0 for missing ids;
upstream never builds without music, so nobody saw it). Fix in the patch
script: `getMusic` returns `_muteMusic` when the rule is missing, `getSound`
returns `_muteSound` likewise (callers do `getSound(...)->play()` unguarded).
The `d4 = 172.0` in the register dump was a red herring (the click's Y from
`Action`), and none of the three suspects in the previous LEFTOFF was right.

**FP runtime is verified.** `C:\temp\oxctest\fptest2.c` runs every soft-float
and libm routine the binary links (dp/sp add sub mul div cmp neg fix float,
extend/trunc, xf ops, sin cos tan atan atan2 asin acos sqrt pow floor ceil exp
log fabs, `snprintf %f`) with volatile inputs on the Amiga and on the host
(`-DHOST`); the logs differ only in word order (host is little-endian), 1 ulp
in `(float)1e-3` (ROM `IEEEDPTieee` truncates), `ceil(-0.5)` = 0 vs -0, and
UB overflow cases. Numbers that matter (globe radius `0.45*200+20 = 110`,
sun vector, shading) are bit-exact.

**Geoscape.** With the null-safe getMusic the game reaches the Geoscape:
GEOBORD background, sidebar with buttons, clock, "Select Site for New Base"
window, base-placement radar circles following the mouse, and the globe with
ocean and shaded land. Verified with the in-guest autoinput and
`capture_ours.ps1` (`C:\temp\amiga_oxcom\geo_r2.png`).

**Open on the globe:** land polygons render as blue-grey speckle instead of
the terrain textures (TEXTURE.DAT frames 26-38 at zoom 0). Not diagnosed;
a `globe: land poly tex ... tex px:` marker is in the patch script (Globe.cpp
"land markers") and prints, for the first four polygons, texture id,
`_zoomTexture`, frame count, screen points and 12 sample texture bytes -
nobody has read its output yet (the last run's clicks landed while the game
was still loading; wait for the third `state: resetAll done` before
clicking).

**Seen once, not reproduced (watch for it):** in three runs the globe surface
blitted WITHOUT its colour key (`flags 1000000` instead of `1001000` in the
`globe: blit` line), which wiped the GEOBORD background, and the whole left
256 columns of the display were black; after unrelated rebuilds every run
shows `1001000` and the correct picture. `SDL_SetColorKey` is only defined
once and its logging shows the flag being set. If the black globe returns,
this is where to look: something clearing `SDL_Surface::flags`, or a
duplicate-section pick by the linker.

**Diagnostics left in the code (all one-shot or armed, cheap; remove when the
Geoscape is stable):** `SDLmini_diag_armed` in `sdlmini_video.c` (set for 3
frames by the Globe blit marker; while set, `SDL_FillRect`/`SDL_UpperBlit`/
`SDL_Flip` count the left 256 columns of the back buffer), the "first
filledCircle / texturedPolygon" lines in `sdlmini_gfx.c`, `SetColorKey`
first-6 log, and in the patch script the Globe blit/shadow/land markers and
`NewGameState` markers.

## 2026-08-16 - the main menu is up; the first-frame Guru was the Kickstart ROM

The game now runs its main loop and draws the main menu every time (with
256 MB; see RAM below). What killed it on the first frame for the better part
of a day was **`#8000000B` on the first `float / float` of the game loop**
(`Game::run`: `1000.0f / fps`), and the cause is not in the game, the port
or the toolchain: it is a defect in Kickstart 3.1's `mathieeesingbas.library`.

**What `#8000000B` means.** Vector 11 is the **Line-F emulator** exception -
the CPU met an `Fxxx` opcode (an FPU instruction on a CPU without FPU, or a
jump into data). Not a bus error, as an earlier entry here said.

**How float arithmetic reaches the ROM.** With `-msoft-float`, bebbo's libgcc
(`libm020/libgcc.a`) deliberately contains no `__addsf3/__mulsf3/__divsf3/...`
- only the int<->float conversions and `__fixsfsi` (verified: every routine
that is there is pure integer code, no F-line words). The arithmetic comes
from libnix's `libm.a`, whose members are eight-byte stubs into the AmigaOS
IEEE libraries: `__divsf3` = `movea.l _MathIeeeSingBasBase,a6; jsr -84(a6)`
(`IEEESPDiv`), `__subsf3` -> `IEEESPSub`, `__extendsfdf2` -> `IEEEDPFieee`
in mathieeedoubtrans, and so on. libnix opens all of them at startup via
`__initlibraries` (they are on `__LIB_LIST__`, checked in the binary).

**The ROM bug.** `mathieeesingbas.library 40.4 (16.3.93)`, resident at
`$FC9DDC` in `ROM3.1_A4000.40.70.ROM` (image checksum valid), picks its
function table at init on `AttnFlags & AFF_68881`. The table it installs on
a machine **without** an FPU (`$FCA0A0`, relative offsets) has:

| LVO | function | offset | resolves to |
|---|---|---|---|
| -66 | IEEESPAdd | `0788` | `$FCA828` code |
| -72 | IEEESPSub | `0784` | `$FCA824` code |
| **-78** | **IEEESPMul** | **`001a`** | **`$FCA0BA` - inside the table itself** |
| **-84** | **IEEESPDiv** | **`001c`** | **`$FCA0BC` - inside the table itself** |

Open/Close/Expunge/Add/Sub in the same table decode correctly, so this is
not a misreading. Calling Div executes the table bytes: `001c fe5e` =
`ori.b #$5e,(a4)+` (a stray byte write through whatever a4 holds), then
`fe3c` = Line-F -> Guru `8000000B`. Kickstart 3.0's `mathieeesingbas 37.3`
has three tables (FPU / 020 / 000) and every entry points at code. Software
multiply and divide **do exist** in the 40.4 module (`mulu.l` at `$FCA734`,
`divu.l` at `$FCA81C`); the table simply does not point at them. SetPatch
40.16 (run by the boot HDF's startup-sequence) does not patch it. A real
A1200/A4000 without FPU on 3.1 has the same ROM module, so this is not an
emulator artefact - and it is invisible on any machine with an FPU, which is
why it is not common knowledge.

**Proof on the machine** (`C:\temp\oxctest\fptest.c`, linked exactly like
the game, with the new trap handler): `AttnFlags 0x0003`, then

```
2: float divide (__divsf3 -> IEEESPDiv) next
CPU TRAP 11 (line-F emulator) at PC 0x00fca0c0 SR 0x0000
  opcode words: fe3c ffff ffff ffc4 ffd2 ffc0 ffa0 fd78   (PC is inside the Kickstart ROM)
12: float multiply (__mulsf3 -> IEEESPMul) next
CPU TRAP 11 (line-F emulator) at PC 0x00fca0be SR 0x0000
  opcode words: fe5e fe3c ffff ffff ffc4 ffd2 ffc0 ffa0
```

Everything else tested works: SP Add/Sub, SP<->DP conversion, DP Div/Mul
(mathieeedoubbas 38.1 from disk - off by one ulp: `1000.0/60` gives
`...aaaa` not `...aaab`, harmless for a game), `sqrt`/`sin`/`pow`
(mathieeedoubtrans 37.1) bit-exact. Same result with JIT off and with
`cpu_compatible` either way. The earlier "sometimes a menu appeared" was
runs in which the FPS branch happened not to execute the division before the
first draw.

**Fix.** `native/fp_single.c`: `__mulsf3` and `__divsf3` in pure integer C
(24x24-bit product via `mulu.l`; quotient via `divu.l` 64/32 in inline asm -
gas MIT mnemonic `divul` is the 64-bit-dividend form, encoding `4c4x 04xx`,
`divull` is the 32-bit one), round-to-nearest-even, subnormals, inf, NaN.
`build/test_fp_single.c` compares it against hardware IEEE on the host:
10,401,800 cases, 0 mismatches. Linked as an object ahead of `-lm`, so the
libm stub members are never pulled (each is its own archive member; no
duplicate-definition clash). Only the two broken entry points are replaced -
the rest of the ROM/disk IEEE path is verified good and stays.

**Every Guru is now a log line.** `native/amiga_trap.c` installs a
`tc_TrapCode` handler on the game's task (armed in `main.cpp` around
`game->run()`). On any CPU exception it records trap number, PC, SR, frame
format and d0-d7/a0-a7, rewrites the frame so `rte` lands in user mode
(SR forced to 0, Forbid/Disable nesting undone), longjmps to `main`, logs
"CPU TRAP n at PC ..." plus the opcode words under the PC to `sdlmini.log`
and `openxcom.log`, and exits. `nm` on the (unstripped) binary then turns the
PC into a function name. Verified with `illegal`, an F-line word and
`trap #0` (`C:\temp\oxctest\traptest.c`). Two things learned building it:
`setjmp` must be in a frame that is still live (it is a macro,
`amiga_trap_arm()`), and a trap that fires inside a ROM routine that just did
a stray write can still take the machine down with the *stray write*, not the
trap - the handler is not magic.

**RAM, again.** On the 32 MB target (`oxc-aga.uae`) this build grinds for
~100 s in "loading battlescape resources" and dies with the game's own
"Failed to allocate surface"; on `oxc-aga-ram256.uae` it loads in 4 s and
runs. Same binary. This is the top open problem and is now reproducible on
demand.

**libnix `wmemcpy` copies half the string.** The first menu drew the wrong
glyphs (letters as one Korean glyph, digits scrambled). Font maps
`wchar_t -> glyph` and every string to draw goes through `std::wstring`;
libstdc++ copies wide strings with `char_traits<wchar_t>::copy` = `wmemcpy`,
and libnix's is `move.l n,d0; add.l d0,d0; CopyMem` - n*2 bytes for 4-byte
`wchar_t` (its neighbours wmemset/wmemmove/wmemcmp/wmemchr/wcslen all use
*4). Any wstring past the 3-char SSO buffer had garbage in its second half.
`native/libnix_fixes.c` replaces it (own archive member, no clash). After
that the menu reads "OpenXcom 1.0 Dev / New Game / New Battle / Load Game /
Options / Quit" and the palette that looked "wrong" is simply UFO's green
main-menu palette - verified against `PALETTES.DAT` decoded on the host.

**Input is injected inside the guest.** Driving the game with synthetic host
mouse input went wrong the moment WinUAE dropped its mouse trap: the clicks
landed on the user's desktop. All host-input scripts are retired
(`winuae/harness/_retired_host_input/`). `sdlmini_autoinput.c` polls
`Work:autoinput.txt` (`move/click/rclick/key/wait/quit`), feeds SDLmini's own
event queue and deletes the file when done; `harness/autoinput.ps1` writes it
and waits. Game screen in the WinUAE window: scale 2.0, origin (106,78).

**Front line now: starting a new game.** Main menu -> New Game -> Beginner ->
OK dies within ~2 s: `CPU TRAP 4 (illegal instruction) at PC 0x942c0000`
(a jump into garbage; `d4 = 0x40658000` = 172.0, the click's Y as a double,
`a0 = $F80ADA` in ROM). Somewhere in `NewGameState::btnOkClick` ->
`SavedGame` / world generation / `Globe` / `GeoscapeState`. Suspects, in
order: a wrong template copy kept by the linker (the "duplicate section"
family), a double returned in the wrong registers by a ROM IEEE routine
(the `fp_conv.c` pattern), a plain port bug. Markers in those constructors
are the next step.

Also new: `Engine/Game.cpp` and `Menu/StartState.cpp` log every reason the
game can quit (`game: quit() called`, `SDL_QUIT event`, StartState's
any-key-after-error), and sdlmini logs every key and button event.

## 2026-08-16 - the game loads its data; the first frame still crashes

`OpenXcom started successfully!` is now in the log. Data loading - mods,
rulesets, palettes, sound sets, every sprite - completes on the emulated
Amiga. The game then dies on its first drawn frame with `#8000000B`
(the entry above explains what it really was; "bus error" here was wrong).
That is the current front line.

Four separate causes were untangled to get here. None of them was what the
earlier `#80000003` Guru looked like:

**1. RAM. 32 MB is not enough.** The Guru was the game running out of memory
while loading sounds - `malloc` returned NULL, the game used the NULL, and the
68020 took an address error. With `z3mem_size=256` the same binary walks
straight past it. The binary alone is ~15 MB and the loaded data is more; the
port has no measured RAM figure yet and this is still the top risk.
`winuae/oxc-aga-ram256.uae` exists to prove that a symptom is memory pressure
and nothing else. **It is a probe, not a target machine.**

**2. The test data is incomplete.** `data/UFO/SOUND/` has `SAMPLE.CAT` but not
`SAMPLE2.CAT` or `SAMPLE3.CAT`. Upstream throws when the second sound set is
missing, which aborts mod loading and takes the game down - one absent file
looks exactly like a port bug. The port now logs it and carries on with a
silent sound set (`Mod/Mod.cpp`, patched). The proper fix is to copy the
missing files in; until then the battlescape has no sound.

**3. Nothing decoded IFF.** X-COM's `UFOGRAPH/*.LBM` are `FORM/PBM ` files
(Deluxe Paint chunky, ByteRun1-compressed, 256-colour CMAP) and the SDL_image
shim only did BMP. `native/sdlmini/src/sdlmini_lbm.c` decodes both PBM and
planar ILBM; `sdlmini_image.c` now picks the decoder by content rather than by
file extension.

**4. `Surface::loadImage` mangled every path.** Upstream converts the filename
with `wstrToUtf8(fsToWstr(filename))` before `IMG_Load`, because desktop SDL
wants UTF-8. That round trip goes through the C library's wide-character
conversion, which on libnix returns garbage - the path arrived as
`P... .....` (seven bytes of noise) and every image load failed with "cannot
open". AmigaOS filenames are plain 8-bit bytes, so the conversion is skipped.

### Toolchain defect 4: sprintf is broken

`sprintf` on this libc produces nonsense. `fprintf`, `snprintf`, `vsprintf`
and `vsnprintf` are all correct. Proven on the machine with a ten-line program
(`sizeof(int)` is 4, so this is not the old Amiga 16-bit-`%d` convention):

```
sprintf   : d=15 ld=1111490575 x=4240 lx=F4240 s= b=100C b_l=F81E0000
fprintf   : d=1000000 ld=1000000 x=f4240 lx=f4240 s=STRING
snprintf  : d=1000000 ld=1000000 s=STRING
vsnprintf : d=1000000 ld=1000000 s=STRING
```

This cost real time: it corrupted the port's own diagnostics and sent the
investigation after a CAT-index endianness bug that does not exist. Two log
lines claimed a 16 MB sound object inside a 1.1 MB file. **Never call
`sprintf`.** Every use in `native/` is now `snprintf`.

### Nothing is written to the boot hardfile - now enforced

`hardfile2=ro` in every `winuae/*.uae` config. The port only ever wrote to
`Work:` (`PROGDIR:`, the shared folder on the host), but the hardfile was
mounted read-write, so a crashing emulator could still damage it. It cannot
now. AmigaOS boots fine from a write-protected volume: `T:` and `ENV:` live in
`RAM:`.

## 2026-08-16 - first run on the emulated Amiga

**`m68k-amigaos-strip` produces broken executables. Never strip.** This cost
most of a night. A stripped Hunk binary loads and then takes the machine down:
WinUAE stops the CPU with **HALT1**, black screen, no Guru, nothing in any log
- indistinguishable from the program crashing in its first instruction. Proven
on a 10 KB hello-world: the unstripped binary prints, the stripped one is
silent. (The openttd port passes `--disable-strip` to configure, which is the
same conclusion arrived at from the other side.) `build.sh` no longer strips;
the binaries are 15 MB instead of 12 MB.

**`std::ifstream::close()` never returns** on a file that exists. Every
destructor calls it, so every scope exit hangs. `native/amiga_fstream.h` puts
stdio under the stream interface; the patch script swaps it in across the game
and rewrites `YAML::LoadFile`. The streambuf was independently verified on the
machine against plain stdio (CAT index, `seekg`, `peek`, `tellg` - all exact),
so it can be ruled out when something else looks like an I/O bug.

**The Hunk format has no COMDAT.** Duplicated template instantiations are
de-duplicated by the linker, which warns `duplicate section ... has different
size` and sometimes keeps the wrong one. That made `YAML::LoadFile` loop
forever until yaml-cpp was built as a single translation unit.

### Test-harness rules learned here (all of them cost a wrong conclusion first)

- **One binary per boot.** A halt stops everything after it in the startup
  script, so a script that tests five binaries only ever reports on the first
  failure.
- **libnix closes the shell's output handle on exit**, so the `Echo` after a
  program in the startup script often never runs. Absence of that marker means
  nothing; only the program's own output counts.
- **Never trust a binary built with different flags as a control.** A probe
  built without `-mcpu=68020` links the 68000 multilib and dies on this
  machine for reasons that have nothing to do with the port.
- **Isolate before theorising.** Three of the four causes above were settled by
  a ten-line program run on the same machine (`cattest`, `fmttest`,
  `filetest`), not by reading the game's code. Sources are in
  `C:\temp\oxctest`.
- WinUAE must be launched as `winuae.exe -f <config>` with `use_gui=no`, and
  the window position must be forced (`winuae.ini` remembers a monitor that may
  not exist - the emulator then runs with no visible window at all).
- The runtime (Kickstart, `boot.hdf`, `Work:`) lives on **C:\temp\amiga_oxcom**,
  not on the network drive: copying the game data there took ~15 minutes once.

## 2026-08-16 - stage 1: first 68k build

**Base chosen and fetched.** Upstream `SupSuper/OpenXcom` at `00fbacde`
(2016-06-27), the "TFTD matured, upstream goes quiet" point from
`PORT_RESEARCH.md`. The pristine tarball is `upstream/openxcom-00fbacde.tar.gz`
and is never modified: `build/apply-amiga-patches.py` reconstructs the port
from it on every build, the same model as `openttd_amiga_68k`.

**SDL is replaced, not ported.** `native/sdlmini/` is a source-compatible
subset of SDL 1.2 implemented on top of `amiga_gfx.c` / `amiga_audio.c` taken
from the OpenTTD port:

- The public headers are SDL 1.2.15's own, verbatim, so every struct layout and
  enum value the game compiles against is exactly what it expects. Only
  `SDL_config.h` is ours.
- `SDL_mixer.h`, `SDL_image.h`, `SDL_gfxPrimitives.h` are ours, matching the
  1.2-era APIs OpenXcom calls.
- Implemented: video mode / surfaces / 8bpp blits with colour key and
  clipping / palettes / events / keyboard (Amiga raw codes -> SDLK) / mouse /
  cursor / timers / RWops / BMP and IFF LBM loading / threads (run inline) /
  semaphores / SDL_gfx lines, circles, flat and textured polygons / SDL_mixer
  on four Paula channels.
- Deliberately not implemented, with a logged reason rather than a silent
  stub: 32bpp blits, SDL_gfx text primitives (used only by the developer map
  dump), OpenGL of any kind.

The real SDL 1.2 for 68k (HenrykRichter's fork) was **not** used. The OpenTTD
port took that route first and hit a hard blocker - `CGX_NormalUpdate` hangs in
`LockBitMapTags` on this toolchain - and ended up writing `amiga_gfx.c`
instead. Repeating that experiment was not worth a day.

**Removed from the game:** OpenGL (upstream's own `__NO_OPENGL`), the HQX/xBRZ
scalers, and the zoom path that exists only to feed them (`Engine/Zoom.cpp`
replaced with a straight copy plus a nearest-neighbour fallback). Music is off
via upstream's `__NO_MUSIC` until the ADPCM streaming stage.

**Replaced wholesale:** `Engine/CrossPlatform.cpp`. Upstream is Win32 + X11 +
POSIX in one file; the Amiga version is `PROGDIR:` paths, `stat`/`dirent`,
Intuition requesters for errors, and no backtrace. AmigaOS path rule that bit
first: a trailing slash means "the parent of", so it is stripped before every
`stat()` and `mkdir()` while `endPath()` still hands one to the game.

**Three binaries, one code base:** `openxcom-aga`, `openxcom-rtg`,
`openxcom-ask`. They differ only in `AMIGA_BACKEND_DEFAULT`; each still accepts
`-aga` / `-rtg` / `-ask`. The "ask" build puts an Intuition `EasyRequest` on
the Workbench screen before anything opens a display, and only offers the RTG
button when an 8-bit RTG mode actually exists.

### Result

All 304 game files, yaml-cpp and the native layer compile, and all three
variants link:

| binary | size | stripped |
|---|---|---|
| `openxcom-aga` / `-rtg` / `-ask` | 15,133,288 B | **11,918,424 B** |

- Magic `00 00 03 F3`: real AmigaOS Hunk executables.
- **Zero FPU instructions in the binary** (`objdump -d | grep -c f<op>` = 0), so
  `-mcpu=68020 -msoft-float` did what it claims and the port needs no FPU today
  - before a single float has been converted to fixed-point. What that costs in
  speed is unmeasured; soft-float is not free, it is just not fatal.
- The linker emits a wall of "duplicate section ... has different size/contents"
  warnings for C++ template instantiations. The OpenTTD port sees the same ones
  and they are non-fatal.
- Five files are compiled at `-O0` after a cc1plus ICE under WSL1
  (`Options.cpp`, `NewBattleState.cpp`, `Mod.cpp`, `SaveConverter.cpp`,
  `SavedGame.cpp`). That is a real speed cost on a 68020 and should not stay.

**11.9 MB of executable is the first hard number for the RAM question**, and it
is not encouraging: OpenTTD's 68k binary is 5.7 MB. Nothing has been done about
it yet - no `-ffunction-sections`/`--gc-sections`, no attempt to cut RTTI or
template bloat. That is the obvious next lever after the game runs at all.

### Toolchain findings (this project, this host)

- bebbo amiga-gcc **6.5.0b** compiles the 2016 OpenXcom tree as `-std=gnu++11`
  without source changes. C++11 is needed for **yaml-cpp 0.6.3**, which is
  boost-free - 0.5.x would have dragged in boost headers for no gain.
- `-fno-rtti` is not an option: the game uses `dynamic_cast` (BriefingState).
- SDL 1.2.15's headers compile clean for m68k with a hand-written
  `SDL_config.h`. `SDL_BYTEORDER` resolves to big-endian correctly (verified),
  so upstream's `SDL_SwapLE32` calls do the right thing.
- `src/dirent.h` (a Microsoft Visual Studio shim) shadows the real
  `<dirent.h>` because `src/` is on the include path, and its non-MSVC branch
  then includes itself. It is deleted by the patch script.
- vasm needs `-I/opt/amiga/m68k-amigaos/ndk-include` for Kalms' c2p
  (`graphics/gfx.i`).
- WSL1 makes cc1plus segfault on some files (GCC's own recursion vs an 8 MB
  stack). `ulimit -s 65536` plus a per-file `-O0` retry handles it; files that
  end up at `-O0` are listed at the end of the build.
- Inherited from the OpenTTD port and honoured here: `-O1` (not `-O2`, which
  breaks exception unwinding), `-mcpu=68020 -msoft-float` (not `-m68040`,
  which silently selects the 68881 multilib), never `-lpthread` or `-lc`.

### Not done yet

- The first drawn frame (`#8000000B`).
- The missing `SAMPLE2.CAT` / `SAMPLE3.CAT` in the test data.
- Music, ADPCM streaming and the Paula music channels.
- The FPU-ectomy: 866 `float`/`double` occurrences are still in the tree.
  Nothing has been converted to fixed-point yet - the binary uses soft-float.
- A real RAM measurement. This is still the top risk.
