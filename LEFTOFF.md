# LEFTOFF - hand-off for the next session (updated 2026-08-20, wieczor)

Read this, then `CLAUDE.md` (rules), then the top entry of `PROGRESS.md` (proofs).

## ZGLOSZENIE USERA 2026-08-20 noc: muzyka kosztuje za duzo i sie zacina

Trzy objawy, trzy rozne przyczyny. Jedna juz naprawiona.

### 1. "040 chodzi jak 030" - to koszt miksowania, zmierzony juz wczesniej

Nie jest to nowa regresja. Wlasne pomiary z `musicbench` (030/50): miks 16
glosow to **40.7% CPU na geoskopie z interpolacja**, 25.9% bez, przechwyt
30.8% / 20.2%. Zabranie ~1/3 procesora slychac dokladnie tak, jak user opisal.
ROZWIAZANIE = tryb **Pre-rendered** (surowy 8-bit PCM z dysku, ~0-1% CPU).
Tryb istnieje w opcjach, ale JEST NIENAPISANY - to nadal glowna pozycja 0.9.0.

### 2. Muzyka zacina sie przy ladowaniu - PRZYCZYNA ZNALEZIONA

`SDLmini_MixerService()` jest wolany z `SDL_Flip`
(`native/sdlmini/src/sdlmini_video.c:850`). Nie ma klatki -> nie ma dopelnienia
bufora -> Paula dogrywa ostatni bufor i przerywa. Podczas ladowania gra nie
flipuje, wiec zacina sie dokladnie wtedy.

User ma racje co do AmigaAMP: tam odtwarzanie nie stoi w petli glownej.
WLASCIWE ROZWIAZANIE = **osobny Process AmigaOS** dla muzyki:
- trzyma requesty audio.device dla kanalow 2+3,
- spi na porcie odpowiedzi (bezczynny nic nie kosztuje),
- dopelnia bufory Chip czytajac z dysku,
- przyjmuje komendy (play/stop/volume) przez port komunikatow.
MUSI to byc Process, nie przerwanie: czytanie pliku idzie przez dos.library,
ktora nie jest bezpieczna w przerwaniu.

UWAGA, zeby nie budowac zludzen: przy **miksowaniu na zywo** osobny Process
NIE usuwa kosztu CPU, tylko go przenosi - podczas ladowania mikser zacznie
konkurowac z loaderem o ten sam procesor. Zacinanie znika dopiero z
POLACZENIA: pre-render (koszt spada do ~1%) + Process (dopelnianie niezalezne
od klatek).

### 3. Muzyka z menu leci w bitwie - NAPRAWIONE

Dotyczy WYLACZNIE skrotu `amigaAutoBattle`, nie normalnej gry. W lacie
"MainMenuState.cpp (auto battle)" bylo:

    nb_->init();          <- NewBattle dostaje init()
    nb_->btnOkClick(0);
    br_->btnOkClick(0);   <- Briefing NIE dostawal init()

A `BriefingState::init()` konczy sie na `_game->getMod()->playMusic(_musicId)`
(zweryfikowane w zrodle upstream, `Battlescape/BriefingState.cpp:170`). Bez
init() muzyka bitwy nigdy nie startowala i graj dalej to, co szlo w menu.
Dodane `br_->init()` przed klikiem, plus zabezpieczenie: `init()` moze zamiast
muzyki wypchnac `CutsceneState`, wiec klik idzie tylko gdy briefing nadal jest
na wierzchu. NIEZBUDOWANE I NIEPRZETESTOWANE.

### Kolejnosc prac - wazna

Pytanie o muzyke na starcie (user prosil) ma sens DOPIERO po napisaniu trybu
Pre-rendered. Requester oferujacy wybor, ktory nic nie robi, jest gorszy niz
brak requestera. Wiec:

1. Napisac tryb **Pre-rendered** (render do `user/music/*.raw` + manifest,
   drugi pasek postepu juz gotowy, przerywalny, fallback na live).
2. Przeniesc dopelnianie strumienia do **osobnego Process**.
3. Dopiero teraz **requester na starcie** - wzorem `amigastartup_ask_backend()`
   (`EasyRequestArgs`), z ta sama kolejnoscia: przelacznik CLI -> domyslna
   wkompilowana -> requester. Wybor zapisac do options.cfg, zeby nie pytal
   przy kazdym starcie. Tresc ma uczciwie nazwac koszt obu stron: pre-render
   to ~40 MB na dysku i jednorazowy render, live to ~1/4-1/3 CPU na stale.
4. Zbudowac i przetestowac poprawke z punktu 3 powyzej (muzyka bitwy).

## STAN 2026-08-20 wieczor: MUZYKA GRA (0.9.0, jeszcze nie wydane)

Zweryfikowane na oxc-aga-nojit-040-40: menu glowne gra, `SND: +6%` w pasku
WinUAE, 44.6 fps w menu z muzyka (bez ~50), zero trapow. Binarki 19:28,
backup `_1949_090-music-plays.zip`.

CO POWSTALO
- `native/amiga_music.c/.h` - programowy mikser wavetable: 16 glosow,
  22 kHz MONO, wszystko na intach (pozycje 16.16, tablica poltonow,
  tablica glosnosci 65x256), parser GM.CAT 1:1 z GMCat.cpp. Zweryfikowany
  na PC przeciw referencji: +-0.3 dB w kazdym pasmie.
- `data/music.bnk` (6.3 MB, deploy do `data/common/music.bnk`) - bank sampli
  wyciety z FluidR3 (MIT, `data/FluidR3_License.txt` jedzie z nim).
  Generator: `build/gen_music_bank.py`. KLUCZOWE: bank v2 pyta logike
  referencyjna o KAZDY klawisz i zapisuje gotowa mape klawisz->sampel
  (v1 wymyslal wlasne strefy i gral INNE sample - harfa 80% nut, GM92 gral
  "Fantasia" zamiast "Bowed Glass"). Weryfikacja: 11339 nut, 0 roznic.
- Opcje w zakladce Amiga: **MUSIC** (Off / Mixed live / Pre-rendered,
  domyslnie Live) i **MUSIC QUALITY** (Low/High = interpolacja; domyslna
  wg `SysBase->AttnFlags`: High na 040/060, Low na 020/030). Przy
  Pre-rendered wiersz quality jest wyszarzony.
- Drugi pasek postepu na splashu (bursztynowy, nad glownym):
  `AmigaSplash_Progress2()` / `..._Progress2End()`. GOTOWY, ale NIC GO
  JESZCZE NIE WOLA - czeka na tryb Pre-rendered.

DLACZEGO BYLO CICHO (3 rzeczy, wszystkie naprawione)
1. `-D__NO_MUSIC` wycinal CALY blok "Load musics" w `Mod::loadResources` -
   zaden obiekt Music nie powstawal. Guard: `#if !defined(__NO_MUSIC) ||
   defined(__AMIGA__)`.
2. W kolejce formatow ADLIB stoi PRZED MIDI, a ADLIB.CAT lezy obok GM.CAT -
   gra wybierala AdlibMusic (u nas niemy). Na Amidze kolejka = `{ MUSIC_MIDI }`.
3. `SDLmini_MixerService()` istnial, ale nikt go nie wolal - bufor strumienia
   nigdy sie nie dopelnial. Podpiety pod `SDL_Flip`.

POMIARY (030/50, klasa 10 MIPS, `musicbench` w Work:)
- miks 16 glosow: geoskop 40.7% z interpolacja / 25.9% bez; przechwyt
  30.8% / 20.2%; walka 4.6% / 4.0%. PO optymalizacji petli (test zapetlenia
  i sprawdzanie konca sampla wyrzucone z petli probek, probka strazna
  w banku, amplituda raz na przebieg) NIE ZMIERZONE PONOWNIE - `musicbench`
  jest przebudowany, warto odpalic i porownac.
- ADPCM: kompresja 8%, dekompresja 6.8%; konwersja 30 min muzyki 7.5 min.
  Dlatego tryb Pre-rendered ma pisac SUROWY 8-bit PCM (~0-1% CPU, ~40 MB),
  nie ADPCM.

DO ZROBIENIA W 0.9.0
- Tryb **Pre-rendered**: render do `user/music/*.raw` + manifest, drugi pasek
  postepu, przerywalny, fallback na live przy braku miejsca. NIENAPISANY.
- Sondy `mus:` (cat/play/bank/parse/strm/audio) sa WLACZONE na stale -
  usunac przed wydaniem.
- `Work:aga071/aga072/aga080` (+ .info) - stare binarki porownawcze, sprzatnac.
- Bank 6.3 MB przy 22 kHz; przy 16 kHz zszedlby do ~4.6 MB i miks -28%.

## STAN wczesniejszy: v0.8.0 WYDANE - marsz bez freeze'ow, New Battle 2x

Po wydaniu: falszywy alarm "scroll 12->8 fps" - to byl amigaPerfLog: 1
pozostawiony w live options.cfg (per-blit pomiary us); wyzerowany. W Work:
leza binarki porownawcze aga071/aga072/aga080 (+ .info) - SPRZATNAC gdy
przestana byc potrzebne, zeby nie mylily (jak stare probe'y w run).

Dzien opisany w PROGRESS.md (gorny wpis): plastry FOV/swiatla na klatkach
animacji marszu (pomysl usera; 6amB-6amH; opcja amigaSplitWalk ON), zakladka
Amiga = przewijana lista jak ADVANCED, New Battle otwarcie 10->6 s, okclick
12.7->11.4 s. Sondy: wf:/newbattle:/savecfg: (gadatliwe za amigaPerfLog;
w LIVE options.cfg amigaPerfLog stoi na 1 z testow - wyzerowac gdy przestanie
byc potrzebne). OTWARTE: (a) cache .ybc battle.cfg pisze sie, ale odczyt nie
trafia (fallback ok, czasy akceptowalne - zagadka na pozniej); (b) dalsze cele
ladowania: rulesety 43 s (konsumpcja wezlow), audio ~25 s, LBM/LUT ~14 s,
jezyk ~13 s; (c) tura AI ~84 s (parkowane).

NOWE PULAPKI (pelniej w PROGRESS): -O1 potrafi zjesc porownanie Position w
warunku (jawne inty dzialaja); TileEngine.h na liscie restore; w repr-literale
eskapowac cudzyslowy i ast.parse PRZED zapisem pliku; substring '\t\t\t}'
lapie ogon '\t\t\t\t}'.

## STAN 2026-08-19 noc: LADOWANIE 2.7x SZYBSZE - start 344 -> 128 s (040/40), na 030/50 15 min -> 5.3 min

WYDANE jako v0.7.2 (kod 82b9b75, release z zipem na github). Pomiar = timeline
splashu (`splash: N% at X ms` w sdlmini.log, jest w binarce na stale).
Mapa procentow: 1-6 start+metadata, 6-37 parse .rul (tick/plik), 40-57
SCR/BDY/SPK geo, 58-70 sound CATy, 71-76 PCK UNITS, 76-77 okno battlescape
(LBM palety + transparency LUT + TAC00.SCR + ufograph), 77-79 sorty, 80
fonty+muzyka, 81-88 extra sprites/sounds, 89-98 jezyk.

Kroki dnia (kazdy = sekcja w apply-amiga-patches.py, wszystkie bit-exact
procz D):
- **A (6am)**: PCK/DAT/SPK/BDY slurp + dekod z pamieci (czytaly PLIK PO
  BAJCIE przez istream::read ~10 KB/s; BDY geo 57->10 s, PCK 68->46 s).
- **A2 (6am2)**: hoist `_frames[frame]` przed petle pikseli (lookup w
  std::map NA KAZDY PIKSEL; PCK 22.5->7.6 s).
- **B (ybc)**: binarny cache drzew yaml `<plik>.ybc` obok zrodla, tylko
  standard/ i common/; naglowek = size+mtime zrodla; 1. start pisze, kolejne
  omijaja caly scanner (rulesety 119->53 s, jezyk 25->15 s). Implementacja
  w patch_yamlcpp (parse.cpp, YBC_BLOCK). `out.reset(root)` NIE operator= -
  gcc 6.5 ICE (segfault) na Node::operator= w yaml_all.cpp. NIE wydawac
  .ybc w releasach.
- **A3 (6am/6am3)**: loadBdy dekoduje serie RLE memset/memcpy wprost do
  pixeli zamiast setPixelIterative (~200 cykli/px; geo BDY 11.5->5.2 s).
- **A4 (6am4)**: createTransparencyLUT z lokalna kopia palety (3x
  getColors() cross-TU NA KAZDE porownanie, 4 palety = 24 s -> ~5 s);
  loadLOFTEMPS slurp. UWAGA: okno 76-77 to NIE byl bleach ani BDY ufograph
  (obie hipotezy obalone testami) - to byl LUT.
- **C (nodealloc)**: yaml-cpp 7 alokacji/wezel -> 4: make_shared w
  memory::create_node, node(), node_ref(); pula std::set->std::vector
  (wezly unikalne z konstrukcji). patch_yamlcpp_nodealloc. Rulesety
  50->42 s, jezyk -6 s.
- **D (6am5)**: Font::load pomija arkusze _jp/_ko.png (189+67+52+52+35+18 KB
  PNG, tysiace glifow CJK) gdy jezyk != ja/ko. Fonty 17 -> 0.8 s. JEDYNA
  zmiana zachowania (ja/ko dalej dziala - warunek na Options::language).
- **Kursor**: systemowy wskaznik WIDOCZNY przez caly splash
  (amigagfx_pointer_suspend w amiga_gfx.c/h + wywolania w amiga_splash.c);
  gra chowa go dopiero po przejeciu ekranu. Zyczenie usera.

Stan po dniu (040/40): total 128 s: rulesety 43 (konsumpcja wezlow przez
Rule::load - trudne), extra+jezyk 26, PCK+okno76-77 21 (LBM/LUT/TAC00.SCR),
vanilla+CATy 19 (audio konwersje - kandydat cache/lazy), start+meta 9,
sorty 3 (sortLists uniewinniony: 3 s, nie 80). Na 030/50 grafika+dzwiek
(123 s) wazy juz wiecej niz yaml (94 s).

**Pulapki 19.08 wieczor**: (1) restore przed KAZDYM buildem - takze gdy
zmiana tylko w yaml-cpp ("StartState load markers" pada na wlasnym outputcie
skryptu; nie ma buildu bez restore); pelna lista w memory
restore-list-full + doszly Mod/MapDataSet.cpp i Engine/Font.cpp;
(2) yaml-cpp: patch_yamlcpp ma marker amiga_ybc - przy zmianie tej funkcji
przywrocic parse.cpp z ~/build/yaml-cpp-0.6.3.tar.gz; nodealloc/memory/ice
maja wlasne markery i sa naprawde idempotentne; (3) tarball gry ma CRLF -
generatory patchy MUSZA normalizowac (edit() czyta w trybie tekstowym);
(4) gra przy wyjsciu ZAPISUJE options.cfg z RAM - wyzerowany na dysku
amigaAutoBattle wraca, zerowac po zamknieciu emulatora.

Sondy loadingu: splash timeline zawsze w logu; skrypt awk do rozbicia faz
w historii sesji. Test 2x przy zmianach ybc (1. run pisze cache).

## STAN 2026-08-19 wieczor: v0.7.1 WYDANE - bitwa zamknieta, nastepny cel: LADOWANIE

github.com/angree/AmiXcom/releases/tag/v0.7.1 (kod 20a2a71). Pasek:
"AmiXcom 68K 0.7.1". CALY plan rysowania z rana ZROBIONY (1A run-y sprite'ow,
1B/1B2 osobne boxy + dokladny box kursora, 1C logika per kafel, 1D bez
colour-key, 1E scroll tylko biezaca faza + animacja wstrzymana, krok 3 =
amigaReachUp, 2 = asm blit) ORAZ tura AI 280 -> ~84 s (pary bezcelowe, memo
swiatla, cywil bez FOV, int A* guess, memo getTUCost) + fix TRAPV (dzielenie
przez sqrt(0) gdy strzelec dokladnie nad celem - ubijalo ture w srodku; user
nie umie juz wywolac dawnego "zwisu", byc moze to bylo to). Wyniki na 040-ekw:
postoj ~35 fps, kursor ~15, scroll 11-12, pelne zlozenie ~85 ms; na 030/50
walka grywalna. Szczegoly + liczby: PROGRESS.md dwa gorne wpisy (0.7.1, 0.6.1).

**NASTEPNY CEL (user): CZASY LADOWANIA.** Zmierzone wczesniej (PROGRESS/LISTA):
start gry ~3 min (sortLists ~80 s + region-sanitacja/vanilla resources ~72 s
juz czesciowo zbite - sprawdzic stan), New Battle ekran ~35 s
(NewBattleState::load: YAML battle.cfg 27 KB + Base::load), bgen.run ~35 s
(generateMap: MCD+PCK ~2.5 s?, recalcFOV 3 s, initMap), load save ~20-25 s
(parse ~11 s). Sondy startowe/loadowe juz sa w patch scripcie (6e-6v).

**SONDY po 0.7.1**: gadatliwe (prof:/cache:/us:/us2:/geo:/map:/seed:/sig:/
frameprof/slow frame) za opcja amigaPerfLog w options.cfg (domyslnie 0,
zmiana bez rebuilda). fov:/step: tylko >=300 ms. ZAWSZE wlaczone i tanie:
aisum: co 10 s w turze AI + aiturn: TOTAL na koniec (think/fov/path/light/
ray/vis/draw + id/typ biezacej jednostki - zwis AI sam sie nazwie w logu).

**Pulapki z 19.08** (oprocz starych): (1) restore_file.sh MUSI dostac pelna
liste przed KAZDYM buildem - dzis dochodza: Engine/Options.inc.h, Engine/
version.h (via tar -O, nie ma go w skrypcie restore), Battlescape/Pathfinding.
cpp/.h, PathfindingNode.cpp, AIModule.cpp, BattlescapeGame.cpp, Mod/Mod.cpp,
Engine/SurfaceSet.cpp; (2) extern "C" w srodku funkcji = blad kompilacji,
deklaracje na poziom pliku; (3) heredoc bash psuje \ w tresci patchy - skrypty
lat pisac Write'em; (4) zostawiony amigaAutoBattle: 1 w Work:user/options.cfg
= "gra startuje do walki" (dzis 2x); wydania NIE zawieraja options.cfg, wiec
zip czysty; (5) po przerwaniu buildow zaczete tlo NIE zyje - sprawdzic EXIT
w logu zanim sie czeka.

Backupy 19.08 (najwazniejsze): _1328 scroll 11-12 fps, _1341 przed krokiem 3,
_1410 TRAPV+sondy, _1452 przed 1G3, _1507 przed memo getTUCost (tura 88 s).

## Where the port stands (older context; newest state above)

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
