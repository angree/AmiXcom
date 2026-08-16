# OpenXcom -> AmigaOS 68k: research bazowej wersji z obsluga TFTD
Data researchu: 2026-08-15

## 1. Wniosek glowny: nie istnieje ZADNE wydanie (tag/release) z TFTD

Repo upstream: https://github.com/SupSuper/OpenXcom (mirror: OpenXcom/OpenXcom)

Wszystkie tagi: v0.1, v0.2, v0.3, v0.4, v0.4.5, v0.9, **v1.0 (2014-06)** - i koniec.
Zero GitHub releases po v1.0. Wszystko po 1.0 to tylko nightly z mastera.

TFTD trafilo do mastera dopiero:

| co | commit | data |
|---|---|---|
| ruleset TFTD (pierwszy moment, w ktorym TFTD w ogole da sie odpalic) | `f1e6f01` "Summon the Kraken! / Add TFTD ruleset to repository" (+14 643 linie, 31 plikow) | **2015-08-03** |
| ogloszenie na openxcom.org "Terror from the Deep now available in the nightlies!" | - | sierpien 2015 |
| stan "TFTD dopieszczone, aktywnosc gasnie" | `00fbacde` | **2016-06-27** |

Kod silnikowy pod TFTD (palety, multi-stage missions, formaty dzwieku) wchodzil
do mastera stopniowo przez 2014-2015, ale bez rulesetu z 2015-08-03 gra sie nie uruchomi.

### Rekomendowane punkty startowe
- **Absolutnie najstarszy dzialajacy TFTD:** `f1e6f014` (2015-08-03). 631 plikow src, 165 133 LOC.
- **Praktycznie najlepszy (najstarszy "dojrzaly"):** `00fbacde` (2016-06-27). 641 plikow, 170 735 LOC.
  Po sierpniu 2015 przez ~10 miesiecy leci fala fixow TFTD; od polowy 2016 aktywnosc
  spada do kilku commitow/miesiac. To jest "najmniej bloatu przy pelnej grywalnosci".

## 2. Wazna korekta zalozen z draftu planu

**a) "Wspolczesna wersja = kombajn/bloat" - to nieprawda dla vanilla OpenXcom.**

| snapshot | pliki src | LOC |
|---|---|---|
| v1.0 (2014-06) | 580 | 150 951 |
| f1e6f01 Kraken (2015-08) | 631 | 165 133 |
| 00fbacde (2016-06) | 641 | 170 735 |
| master HEAD (2026-06) | 646 | 175 397 |

Vanilla master jest tylko ~6% wiekszy niz Kraken i nadal jest na **SDL 1.2**
(`SDL_SetVideoMode`, zero `SDL_CreateWindow`) oraz praktycznie **C++03**
(0x `nullptr`, 0x `unique_ptr`, 5-9 wystapien `auto`/lambda w calym drzewie).
Bloat, o ktorym mowa w poscie, to **OXCE (MeridianOXC/OpenXcom)** - osobny fork,
57 MB repo vs 34 MB vanilla, i to on jest dzis "glownym" OpenXcomem.

**b) "Wersja bez YAML" nie istnieje.** yaml-cpp jest juz w 1.0: 142 pliki uzywaja
`YAML::`. Ruleset-y sa rdzeniem silnika od 0.9. yaml-cpp 0.5 trzeba bedzie
przeportowac tak czy siak (C++, bez zaleznosci systemowych - powinno pojsc).

**c) Sciezka "port 1.0, potem warstwowo dokladac TFTD" jest DROZSZA niz start od Kraken.**
Diff `v1.0 -> f1e6f01` na samym `src/`: 562 zmienione pliki, 69 nowych, ~82 000 linii diffa.
To nie jest "TFTD delta" - to 14 miesiecy calego rozwoju wymieszanego z TFTD.
Odtwarzanie tego recznie = przepisanie polowy projektu.
**Rekomendacja: brac od razu `00fbacde` (albo `f1e6f01`), i to JEGO debloatowac**
(wyciac OpenGL, zoom/scalery, opcjonalne skiny), zamiast dokladac TFTD do 1.0.

## 3. Stan techniczny bazy (snapshot f1e6f01 / 00fbacde) pod katem 68k

Zaleznosci: SDL 1.2, SDL_mixer, SDL_gfx, SDL_image, yaml-cpp >= 0.5. OpenGL opcjonalny.

Dobre wiadomosci:
- **SDL 1.2** - dokladnie ta warstwa, ktora podmieniasz w openttd_amiga_68k (i istnieje
  HenrykRichter/libSDL12_Amiga68k jako fallback/referencja).
- **C++03** - stary GCC m68k-amigaos da rade, bez C++11 runtime.
- **OpenGL/Zoom** (`src/Engine/OpenGL.*`, `Zoom.*`) - w pelni opcjonalne, do wyciecia.
- **Jeden watek** w calym projekcie: `src/Menu/StartState.cpp` (SDL_CreateThread do ladowania
  zasobow) - trywialny do zsynchronizowania.
- Gra turowa 320x200 8bpp -> c2p AGA / RTG chunky jest naturalne.

Do roboty (FPU -> integer):
866 wystapien `float`/`double`, 196 wywolan `sqrt/sin/cos/pow/atan2/exp/log`. Rozklad:

| katalog | float/double |
|---|---|
| src/Engine/ | 249 |
| src/Geoscape/ | 194 |
| src/Savegame/ | 128 |
| src/Battlescape/ | 121 |
| src/Ruleset/ | 102 |
| src/Interface/ | 38 |
| src/Basescape/ | 19 |

Geoscape (wspolrzedne kuliste, trajektorie, dogfight) to glowne gniazdo trygonometrii -
kandydat na fixed-point + LUT sin/cos, dokladnie jak w openttd. Savegame/Ruleset
to gownie parsowanie liczb z YAML - tam float mozna zamienic na fixed przy wczytywaniu.

Ryzyka do zmierzenia empirycznie:
1. **RAM** - OpenXcom trzyma wszystkie zasoby (surface'y, palety, mody) w pamieci.
   Na PC to dziesiatki-setki MB. To jest najpowazniejsze ryzyko dla 020/24-64 MB,
   powazniejsze niz CPU. Do zmierzenia przed decyzja.
2. Rozmiar binarki (STL + wyjatki + RTTI) na m68k-amigaos-gcc.
3. yaml-cpp 0.5 + boost? (0.5 nie wymaga boosta - do potwierdzenia przy budowie).
4. TFTD wymaga danych z wersji PC (Amiga nigdy nie miala TFTD).

## 4. Poprzedni port (punkt odniesienia)

- Autor: **Arti**, 2023-01-02, https://artishq.wordpress.com/2023/01/02/x-com-2-terror-from-the-deep/
- Bazuje na **wspolczesnym** OpenXcom (github.com/OpenXcom/OpenXcom), bez wlasnego repo z patchami.
- Cel: **PiStorm + Emu68**, wczesniej Vampire (odrzucony - "bardzo nieefektywny kod ladowania",
  drastycznie dlugie loady). Wymaga RTG.
- Czyli: zero optymalizacji pod klasyczne 020/030/040/060, zero c2p, zero AGA - stad opinia
  o "nieistniejacych procesorach". To potwierdza sens nowego portu.

## 5. Proponowana kolejnosc prac (skorygowany draft)

1. Wziac `00fbacde` (2016-06-27) jako baze; zrobic repo + branch `amiga`.
2. Zbudowac na PC (Linux/mingw) i **zmierzyc realne RSS** dla UFO i TFTD -> decyzja go/no-go dla 24-64 MB.
3. Debloat: wyciac OpenGL, Zoom/scalery, filtry, zbedne opcje wideo; wymusic 320x200 8bpp.
4. Podmienic warstwe SDL na kod z openttd_amiga_68k: c2p AGA + RTG + okno WB z negocjacja palety.
5. Audio: 4 kanaly Pauli bezposrednio (2 muzyka streaming z dysku, 2 SFX), ADPCM 22 kHz zamiast
   OGG/Adlib; wywlaszczanie kanalu szybkim fade-outem zamiast miksera.
6. FPU-ectomy warstwami: Geoscape -> Battlescape -> Engine, fixed-point + LUT, kompilacja
   pod czyste 020 bez -m68881.
7. Infra testowa: HDF z WB3.x + RTG w WinUAE 2.8, shared folder obok HDF na szybkie podmiany
   binarki, autostart + logowanie do pliku, testy AI z JIT/max speed, kalibracja docelowa
   bez JIT (sysinfo).
8. README: adnotacja o uzyciu kodu z openttd_amiga_68k (MIT).
