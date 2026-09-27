/*
 * amixcom-prefs - AmiXcom settings, before the game starts. An Intuition
 * (GadTools) window on Workbench, and a command line for machines whose
 * mouse is not usable. Copied from the author's Master of Magic port
 * (Ami_ReMoM: native/remom/AmiXcomPrefs.c) and fitted to this game's file.
 *
 *     AmiXcomPrefs                     window
 *     AmiXcomPrefs SHOW                print the settings and the machine
 *     AmiXcomPrefs MUSIC=Pre-rendered  save without a window
 *     AmiXcomPrefs CONVERT             convert the music now
 *     AmiXcomPrefs ?                   help
 *
 * WHY A SEPARATE PROGRAM, when the game has its own "Amiga" options tab:
 * converting the music takes minutes and happens at the first start, the
 * display standard decides whether the game shows anything at all, and a
 * player whose screen does not open never reaches the menu. Both have to be
 * settable before the game runs.
 *
 * THE FILE IS THE GAME'S OWN: PROGDIR:user/options.cfg, the YAML the game
 * reads and writes. Only the lines listed below are touched - every other
 * line is copied through untouched, so nothing the player set in the game is
 * lost. A missing line is added under "options:"; a missing file is created
 * with just these keys, and the game fills in the rest itself.
 *
 * Text in the window is English (the player reads it), comments are Polish.
 * Never sprintf (CLAUDE.md, defect 4) - only snprintf.
 */

#include <exec/types.h>
#include <dos/dos.h>
#include <dos/dostags.h>
#include <intuition/intuition.h>
#include <intuition/gadgetclass.h>
#include <libraries/gadtools.h>
#include <graphics/gfxbase.h>
#include <graphics/text.h>

#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/intuition.h>
#include <proto/graphics.h>
#include <proto/gadtools.h>

#include <stdio.h>
#include <string.h>
#include <stdlib.h>


static const char verstag[] __attribute__((used)) =
    "$VER: AmiXcomPrefs 0.4.4 (26.09.2026)";

#define PLIK "PROGDIR:user/options.cfg"

struct Library *GadToolsBase = NULL;

/* ------------------------------------------------------------------------ */
/*  Ustawienia                                                              */
/* ------------------------------------------------------------------------ */

enum { O_MUSIC, O_MQUAL, O_SPLASH, O_VIDEO, O_BAR, O_CURSOR, O_LANG, O_COUNT };

typedef struct
{
    const char *klucz;      /* klucz w options.cfg */
    int bool_p;             /* 1 = w pliku jest true/false, nie liczba */
    /* Drugi klucz, gdy jeden wiersz w oknie ustawia dwie rzeczy naraz:
     * "AdLib, pre-rendered" to amigaMusic=2 ORAZ amigaMusicSource=1. Gracz
     * nie powinien musiec skladac trybu z dwoch list. NULL = zwykla opcja. */
    const char *klucz2;
    int mapa1[5];           /* wartosc klucza dla kazdej pozycji listy */
    int mapa2[5];           /* to samo dla klucz2 */
    const char *etykieta;   /* w oknie */
    const char *arg;        /* w linii polecen */
    char klawisz;
    int ile;
    const char *nazwy[5];   /* wartosci w oknie (i slowa w linii polecen) */
    const char *podpowiedz[5];
    int domyslna;
} opcja_t;

static const opcja_t OPCJE[O_COUNT] = {
    /* jeden wiersz, dwa klucze: zrodlo (GM.CAT / ADLIB.CAT) i to, czy gra
     * miksuje w trakcie gry, czy czyta gotowy plik z dysku */
    { "amigaMusic", 0, "amigaMusicSource",
      { 0, 1, 1, 2, 2 }, { 0, 0, 1, 0, 1 },
      "Music:", "MUSIC", 'M', 5,
      { "Off", "Samples live", "AdLib live", "Samples converted", "AdLib converted" },
      { "No music. Sound effects still play.",
        "SOUND/GM.CAT mixed while you play: costs CPU, no disk space.",
        "SOUND/ADLIB.CAT emulated while you play - needs a fast processor.",
        "GM.CAT converted to disk once (about 36 MB), then just read back.",
        "ADLIB.CAT converted to disk once (about 36 MB) - the 1994 PC sound." }, 3 },
    { "amigaMusicQuality", 0, NULL, { 0, 1, 0, 0, 0 }, { 0, 0, 0, 0, 0 },
      "Mixing:", "QUALITY", 'Q', 2,
      { "22 kHz plain", "22 kHz smooth", NULL, NULL, NULL },
      { "22 kHz, no interpolation between sample points: cheaper on an 020/030.",
        "22 kHz, interpolated: cleaner treble, about twice the mixing cost.", NULL, NULL, NULL }, 0 },
    { "amigaSplashStyle", 0, NULL, { 0, 1, 0, 0, 0 }, { 0, 0, 0, 0, 0 },
      "Loading screen:", "SPLASH", 'L', 2,
      { "Modern", "Retro", NULL, NULL, NULL },
      { "The port's own loading pictures.",
        "8-bit style redraws of the same scenes, by Banter.", NULL, NULL, NULL }, 1 },
    { "amigaVideoMode", 0, NULL, { 0, 1, 2, 0, 0 }, { 0, 0, 0, 0, 0 },
      "Display:", "VIDEO", 'V', 3,
      { "Auto", "PAL", "NTSC", NULL, NULL },
      { "Follow the machine's display standard - right on almost every Amiga.",
        "Force a 50 Hz PAL screen.",
        "Force a 60 Hz NTSC screen.", NULL, NULL }, 0 },
    { "amigaAppBar", 1, NULL, { 0, 1, 0, 0, 0 }, { 0, 0, 0, 0, 0 },
      "Title bar:", "BAR", 'B', 2,
      { "Off", "On", NULL, NULL, NULL },
      { "Full screen, no bar.",
        "Screen title bar with the depth gadget (flip to Workbench).", NULL, NULL, NULL }, 1 },
    /* amigaCursor jest w grze LICZBA (OPT int), nie bool - zapisane "true"
     * gra odrzuca i bierze wartosc domyslna. */
    { "amigaCursor", 0, NULL, { 0, 1, 0, 0, 0 }, { 0, 0, 0, 0, 0 },
      "Pointer:", "POINTER", 'P', 2,
      { "Game", "System", NULL, NULL, NULL },
      { "The game draws its own cursor.",
        "The Workbench pointer - smooth at 50 Hz. The default.", NULL, NULL, NULL }, 1 },
    { "amigaLangAuto", 1, NULL, { 0, 1, 0, 0, 0 }, { 0, 0, 0, 0, 0 },
      "Language:", "LANGUAGE", 'G', 2,
      { "As set", "From Workbench", NULL, NULL, NULL },
      { "Keep the language chosen in the game.",
        "Take it from Prefs/Locale when this port has that translation.", NULL, NULL, NULL }, 1 },
};

static int wart[O_COUNT];

/* Wartosc jednego klucza z linii "  klucz: wartosc" (YAML gry). */
static int wartosc_z_linii(const char *linia, const char *klucz, int bool_p, int *out)
{
    const char *p = linia;
    size_t n = strlen(klucz);
    while (*p == ' ' || *p == '\t') p++;
    if (strncmp(p, klucz, n) != 0 || p[n] != ':') return 0;
    p += n + 1;
    while (*p == ' ' || *p == '\t') p++;
    if (bool_p) { *out = (strncmp(p, "true", 4) == 0) ? 1 : 0; return 1; }
    if (*p < '0' || *p > '9') return 0;
    *out = atoi(p);
    return 1;
}

/* Wartosc, ktora ma trafic do pliku dla danego klucza tej opcji. */
static void do_pliku(const opcja_t *o, int wybor, char *dst, int cap, int drugi)
{
    int v = drugi ? o->mapa2[wybor] : o->mapa1[wybor];
    if (!drugi && o->bool_p) snprintf(dst, (size_t)cap, "%s", v ? "true" : "false");
    else snprintf(dst, (size_t)cap, "%d", v);
}

static void wczytaj(void)
{
    FILE *f;
    char linia[256];
    int i, v;

    int k1[O_COUNT], k2[O_COUNT];

    for (i = 0; i < O_COUNT; i++) { wart[i] = OPCJE[i].domyslna; k1[i] = -1; k2[i] = -1; }
    f = fopen(PLIK, "r");
    if (f == NULL) return;
    while (fgets(linia, sizeof linia, f) != NULL) {
        for (i = 0; i < O_COUNT; i++) {
            if (wartosc_z_linii(linia, OPCJE[i].klucz, OPCJE[i].bool_p, &v)) k1[i] = v;
            if (OPCJE[i].klucz2 != NULL
                && wartosc_z_linii(linia, OPCJE[i].klucz2, 0, &v)) k2[i] = v;
        }
    }
    fclose(f);
    for (i = 0; i < O_COUNT; i++) {
        int j;
        if (k1[i] < 0) continue;
        if (OPCJE[i].klucz2 == NULL) {
            if (k1[i] >= 0 && k1[i] < OPCJE[i].ile) wart[i] = k1[i];
            continue;
        }
        if (k2[i] < 0) k2[i] = 0;
        for (j = 0; j < OPCJE[i].ile; j++) {
            /* "Off" nie ma zrodla - pasuje do kazdego */
            if (OPCJE[i].mapa1[j] != k1[i]) continue;
            if (OPCJE[i].mapa1[j] != 0 && OPCJE[i].mapa2[j] != k2[i]) continue;
            wart[i] = j;
            break;
        }
    }
}

/* Przepisuje options.cfg linia po linii, podmieniajac tylko nasze klucze;
   brakujace dopisuje zaraz pod "options:" (na koncu pliku wpadlyby do sekcji
   "mods:"). Cudzej linii nie rusza - gracz ma tam wszystko, co ustawil w grze.
   Nowy plik powstaje obok i podmienia stary dopiero, gdy jest kompletny. */

/* ile kluczy ma ta opcja (1 albo 2) i jak sie nazywaja */
static const char *klucz_nr(const opcja_t *o, int nr)
{
    return nr == 0 ? o->klucz : o->klucz2;
}

static void linia_klucza(const opcja_t *o, int wybor, int nr, char *dst, int cap)
{
    char v[16];
    do_pliku(o, wybor, v, (int)sizeof v, nr);
    snprintf(dst, (size_t)cap, "  %s: %s\n", klucz_nr(o, nr), v);
}

static int zapisz(void)
{
    FILE *we, *wy;
    char linia[256];
    char nowa[280];
    int widziane[O_COUNT][2];
    int i, nr, v, po_options = 0;

    for (i = 0; i < O_COUNT; i++) { widziane[i][0] = 0; widziane[i][1] = 0; }

    we = fopen(PLIK, "r");
    if (we == NULL) {                       /* nie ma pliku: sam naglowek */
        wy = fopen(PLIK, "w");
        if (wy == NULL) return 0;
        fprintf(wy, "options:\n");
        for (i = 0; i < O_COUNT; i++)
            for (nr = 0; nr < 2; nr++) {
                if (klucz_nr(&OPCJE[i], nr) == NULL) continue;
                linia_klucza(&OPCJE[i], wart[i], nr, nowa, (int)sizeof nowa);
                fputs(nowa, wy);
            }
        fclose(wy);
        return 1;
    }

    wy = fopen(PLIK ".new", "w");
    if (wy == NULL) { fclose(we); return 0; }
    while (fgets(linia, sizeof linia, we) != NULL) {
        int zajete = 0;
        for (i = 0; i < O_COUNT && !zajete; i++) {
            for (nr = 0; nr < 2; nr++) {
                const char *k = klucz_nr(&OPCJE[i], nr);
                if (k == NULL) continue;
                if (!wartosc_z_linii(linia, k, nr == 0 ? OPCJE[i].bool_p : 0, &v)) continue;
                zajete = 1;
                if (widziane[i][nr]) break;      /* duplikat: zostaje jeden */
                widziane[i][nr] = 1;
                linia_klucza(&OPCJE[i], wart[i], nr, nowa, (int)sizeof nowa);
                fputs(nowa, wy);
                break;
            }
        }
        if (zajete) continue;
        fputs(linia, wy);
        if (!po_options) {
            /* plik moze zaczynac sie od BOM-a (EF BB BF), jesli ktos edytowal
             * go na PC - gra to znosi, wiec my tez musimy */
            const char *p = linia;
            if ((unsigned char)p[0] == 0xEF && (unsigned char)p[1] == 0xBB
                && (unsigned char)p[2] == 0xBF) p += 3;
            if (strncmp(p, "options:", 8) == 0) po_options = 1;
        }
    }
    fclose(we);
    /* czego w pliku nie bylo - na koniec sekcji options (gra czyta cala mape) */
    for (i = 0; i < O_COUNT; i++)
        for (nr = 0; nr < 2; nr++) {
            if (klucz_nr(&OPCJE[i], nr) == NULL || widziane[i][nr]) continue;
            linia_klucza(&OPCJE[i], wart[i], nr, nowa, (int)sizeof nowa);
            fputs(nowa, wy);
        }
    fclose(wy);
    if (!po_options) { DeleteFile((CONST_STRPTR)PLIK ".new"); return 0; }
    if (!DeleteFile((CONST_STRPTR)PLIK)) { DeleteFile((CONST_STRPTR)PLIK ".new"); return 0; }
    if (!Rename((CONST_STRPTR)PLIK ".new", (CONST_STRPTR)PLIK)) return 0;
    return 1;
}

/* ------------------------------------------------------------------------ */
/*  Co ma maszyna - tylko do odczytu, nic nie otwiera                        */
/* ------------------------------------------------------------------------ */

static int ma_aga(void)
{
    struct GfxBase *g = (struct GfxBase *)GfxBase;
    return (g != NULL && (g->ChipRevBits0 & GFXF_AA_ALICE)) ? 1 : 0;
}

static int ma_rtg(void)
{
    struct Library *b = OpenLibrary((CONST_STRPTR)"cybergraphics.library", 0L);
    if (b == NULL) return 0;
    CloseLibrary(b);
    return 1;
}

static int ma_ntsc(void)
{
    struct GfxBase *g = (struct GfxBase *)GfxBase;
    return (g != NULL && (g->DisplayFlags & NTSC)) ? 1 : 0;
}

static void opis_maszyny(char *dst, int cap)
{
    snprintf(dst, (size_t)cap, "This machine:  AGA %s   RTG %s   %s",
             ma_aga() ? "yes" : "no", ma_rtg() ? "yes" : "no",
             ma_ntsc() ? "NTSC" : "PAL");
    dst[cap - 1] = 0;
}

/* ------------------------------------------------------------------------ */
/*  Okno                                                                     */
/* ------------------------------------------------------------------------ */

#define GID_OPCJA 10      /* 10..14 cykle, 20..24 podpowiedzi */
#define GID_PODP  20
#define GID_SAVE  30
#define GID_CANCEL 31

#define KLAWISZE "Keys: M S Q L V B P G change   C convert   D delete   S save"
#define GID_KONW 32
#define GID_KASUJ 33
#define GID_STATUS 42

/* ------------------------------------------------------------------------ */
/*  Muzyka: konwersja na miejscu (native/remom/muzyka_konw.c)               */
/* ------------------------------------------------------------------------ */

static int rowne(const char *a, const char *b);
static int tryb_konwertowany(void);
static LONG pen_ok = -1, pen_nie = -1;   /* ciemnozielony / ciemnoczerwony */
static LONG pen_txt = -1, pen_cien = -1; /* zwykly tekst i cien pod nim */
static void odswiez_stan(struct Window *win);

/* ---- napisy z cieniem ---------------------------------------------------
   GadTools TEXT_KIND umie tylko wybrac kolor tekstu (GTTX_FrontPen), a na
   Workbenchu z przestawiona paleta kazdy pojedynczy kolor moze zniknac w tle.
   Rysujemy wiec sami: najpierw cien (czarny, o piksel nizej i w prawo), potem
   jasny napis. Ktorykolwiek z dwoch kolorow odcina sie od tla, napis da sie
   przeczytac - a zielone/czerwone "jest muzyka / nie ma" widac z daleka.

   Napisy siedza w tabeli, bo okno trzeba przerysowac po IDCMP_REFRESHWINDOW
   i po kazdej zmianie podpowiedzi albo stanu muzyki. */
struct Napis {
    int x, y, w;             /* wspolrzedne w oknie, w = szerokosc do wyczyszczenia */
    const char *s;           /* MUSI zyc tak dlugo jak okno (staly napis albo bufor) */
    LONG pen;
};
static struct Napis NAPISY[16];
static int napisow = 0;

static int dodaj_napis(int x, int y, int w, const char *s, LONG pen)
{
    if (napisow >= (int)(sizeof NAPISY / sizeof NAPISY[0])) return -1;
    NAPISY[napisow].x = x;
    NAPISY[napisow].y = y;
    NAPISY[napisow].w = w;
    NAPISY[napisow].s = s;
    NAPISY[napisow].pen = pen;
    return napisow++;
}

static void rysuj_napis(struct Window *win, int idx)
{
    struct RastPort *rp;
    struct Napis *n;
    int base, len;
    if (win == NULL || idx < 0 || idx >= napisow) return;
    rp = win->RPort;
    n = &NAPISY[idx];
    len = (int)strlen(n->s);
    base = n->y + rp->TxBaseline;
    /* stary napis w tle okna - inaczej krotszy tekst zostawia ogon */
    SetAPen(rp, 0);
    SetDrMd(rp, JAM1);
    RectFill(rp, (WORD)n->x, (WORD)n->y,
             (WORD)(n->x + n->w), (WORD)(n->y + rp->TxHeight));
    SetAPen(rp, (ULONG)(pen_cien >= 0 ? pen_cien : 1));   /* 1 = czarny w palecie WB */
    Move(rp, (WORD)(n->x + 1), (WORD)(base + 1));
    Text(rp, (CONST_STRPTR)n->s, (ULONG)len);
    SetAPen(rp, (ULONG)(n->pen >= 0 ? n->pen : 2));       /* 2 = bialy */
    Move(rp, (WORD)n->x, (WORD)base);
    Text(rp, (CONST_STRPTR)n->s, (ULONG)len);
}

static void rysuj_napisy(struct Window *win)
{
    int i;
    for (i = 0; i < napisow; i++) rysuj_napis(win, i);
}

static void napis_ustaw(struct Window *win, int idx, const char *s, LONG pen)
{
    if (idx < 0 || idx >= napisow) return;
    NAPISY[idx].s = s;
    NAPISY[idx].pen = pen;
    rysuj_napis(win, idx);
}

static int idx_podp = -1, idx_stan = -1;
static char stan_txt[160];

/* user/music/source.txt: zapisane przez gre po konwersji - z czego i w jakiej
   jakosci powstaly pliki. Bez niego mowimy tylko, ile ich jest. */
static void czym_zrobione(char *dst, int cap)
{
    FILE *f;
    BPTR stary = CurrentDir(GetProgramDir());
    dst[0] = 0;
    f = fopen("user/music/source.txt", "r");
    if (f != NULL) {
        if (fgets(dst, cap, f) != NULL) {
            char *nl = strchr(dst, '\n');
            if (nl != NULL) *nl = 0;
        }
        fclose(f);
    }
    CurrentDir(stary);
}

/* 1 = jest muzyka (zielono), 0 = nie ma (czerwono) */
static int stan_muzyki(char *dst, int cap)
{
    BPTR stary = CurrentDir(GetProgramDir());
    BPTR l = Lock((CONST_STRPTR)"user/music", ACCESS_READ);
    char skad[64];
    int n = 0;
    if (l != 0) {
        struct FileInfoBlock *fib = (struct FileInfoBlock *)AllocDosObject(DOS_FIB, NULL);
        if (fib != NULL && Examine(l, fib)) {
            while (ExNext(l, fib)) {
                size_t d = strlen((char *)fib->fib_FileName);
                if (d > 4 && rowne((char *)fib->fib_FileName + d - 4, ".raw")) n++;
            }
        }
        if (fib != NULL) FreeDosObject(DOS_FIB, fib);
        UnLock(l);
    }
    CurrentDir(stary);
    czym_zrobione(skad, (int)sizeof skad);
    if (n > 0 && skad[0])
        snprintf(dst, (size_t)cap, "Converted music: %d tunes, %s.", n, skad);
    else if (n > 0)
        snprintf(dst, (size_t)cap, "Converted music: %d tunes.", n);
    else
        snprintf(dst, (size_t)cap, "Converted music: NONE. The game converts it at the next start (about 36 MB).");
    dst[cap - 1] = 0;
    return n > 0;
}

/* zrzut ekranu Workbencha z oknem (test: czy okno sie miesci) - PPM */
static void zrzut(struct Screen *scr, const char *plik)
{
    FILE *f = fopen(plik, "wb");
    int x, y;
    ULONG rgb[3];
    UBYTE pal[256][3];
    int ile = 1 << scr->RastPort.BitMap->Depth;
    if (f == NULL) return;
    if (ile > 256) ile = 256;
    for (x = 0; x < ile; x++) {
        GetRGB32(scr->ViewPort.ColorMap, (ULONG)x, 1, rgb);
        pal[x][0] = (UBYTE)(rgb[0] >> 24); pal[x][1] = (UBYTE)(rgb[1] >> 24); pal[x][2] = (UBYTE)(rgb[2] >> 24);
    }
    fprintf(f, "P6\n%d %d\n255\n", (int)scr->Width, (int)scr->Height);
    for (y = 0; y < scr->Height; y++)
        for (x = 0; x < scr->Width; x++) {
            LONG c = ReadPixel(&scr->RastPort, (LONG)x, (LONG)y);
            fwrite(pal[(c < 0 || c >= ile) ? 0 : c], 1, 3, f);
        }
    fclose(f);
}

/* Konwersja: URUCHAMIA GRE z -amigaConvertOnly 1. Nazwy utworow siedza w
   rulesetach, wiec tylko gra wie, co konwertowac - powielanie tego tutaj
   znaczyloby drugi parser rulesetow. Gra pokazuje swoj ekran ladowania z
   paskiem postepu i konczy sie sama. */
static const char *binarka_gry(void)
{
    static const char *kandydaci[] = { "openxcom-ask", "openxcom-aga", "openxcom-rtg", NULL };
    int i;
    for (i = 0; kandydaci[i] != NULL; i++) {
        BPTR l = Lock((CONST_STRPTR)kandydaci[i], ACCESS_READ);
        if (l != 0) { UnLock(l); return kandydaci[i]; }
    }
    return NULL;
}

static int uruchom_konwersje(char *tekst, int cap)
{
    BPTR stary = CurrentDir(GetProgramDir());
    const char *exe = binarka_gry();
    char cmd[128];
    LONG rc;

    if (exe == NULL) {
        snprintf(tekst, (size_t)cap, "No game to run here - is AmiXcomPrefs in the game's drawer?");
        CurrentDir(stary);
        return 20;
    }
    snprintf(cmd, sizeof cmd, "%s -amigaConvertOnly 1", exe);
    rc = SystemTags((CONST_STRPTR)cmd, SYS_Input, (ULONG)Input(),
                    SYS_Output, (ULONG)Output(), TAG_END);
    CurrentDir(stary);
    if (rc != 0) snprintf(tekst, (size_t)cap, "The game stopped with code %ld - see Work:sdlmini.log.", (long)rc);
    else stan_muzyki(tekst, cap);
    return rc == 0 ? 0 : 10;
}

/* Tekst stanu razem z kolorem: zielono, gdy muzyka jest, czerwono, gdy nie. */
static void odswiez_stan(struct Window *win)
{
    int jest = stan_muzyki(stan_txt, (int)sizeof stan_txt);
    napis_ustaw(win, idx_stan, stan_txt, jest ? pen_ok : pen_nie);
}

static void konwertuj_okno(struct Window *win)
{
    napis_ustaw(win, idx_stan,
                "Converting - the game is doing it, this can take minutes...", pen_txt);
    uruchom_konwersje(stan_txt, (int)sizeof stan_txt);
    napis_ustaw(win, idx_stan, stan_txt, pen_txt);
    odswiez_stan(win);
}

/* ---- kasowanie muzyki ---------------------------------------------------
   Tylko user/music/#?.raw i pozostalosci #?.tmp - nic innego z katalogu gry.
   (Do 0.4.2 stalo tu jeszcze "muzyka" i ".wav" z portu Master of Magic, wiec
   przycisk nie znajdowal nic do skasowania.)
   Nazwy zbierane najpierw, kasowane potem: DeleteFile w trakcie ExNext
   psuje przegladanie katalogu. */
static int muzyka_pliki(int kasuj)
{
    BPTR stary = CurrentDir(GetProgramDir());
    BPTR l = Lock((CONST_STRPTR)"user/music", ACCESS_READ);
    int n = 0;
    if (l != 0) {
        struct FileInfoBlock *fib = (struct FileInfoBlock *)AllocDosObject(DOS_FIB, NULL);
        char (*nazwy)[32] = (char (*)[32])malloc(512 * 32);
        int ile = 0, i;
        if (fib != NULL && nazwy != NULL && Examine(l, fib)) {
            while (ExNext(l, fib) && ile < 512) {
                char *nm = (char *)fib->fib_FileName;
                size_t d = strlen(nm);
                if (fib->fib_DirEntryType < 0 && d > 4 && d < 32
                    && (rowne(nm + d - 4, ".raw") || rowne(nm + d - 4, ".tmp")))
                    strcpy(nazwy[ile++], nm);
            }
        }
        if (kasuj) {
            BPTR st2 = CurrentDir(l);
            for (i = 0; i < ile; i++) if (DeleteFile((CONST_STRPTR)nazwy[i])) n++;
            CurrentDir(st2);
        } else {
            n = ile;
        }
        free(nazwy);
        if (fib != NULL) FreeDosObject(DOS_FIB, fib);
        UnLock(l);
    }
    CurrentDir(stary);
    return n;
}

/* pytanie przed kasowaniem - zeby missclick nie zabral 40 minut konwersji.
   test: requester pokazany, zrzut prefs-kasuj.ppm, zamkniety bez kasowania. */
static int potwierdz_kasowanie(struct Window *win, int n, int test)
{
    struct EasyStruct es;
    LONG arg[1];
    es.es_StructSize = sizeof es;
    es.es_Flags = 0;
    es.es_Title = (UBYTE *)"AmiXcom - Delete music";
    es.es_TextFormat = (UBYTE *)"Delete all %ld converted music files?\nThis cannot be undone.";
    es.es_GadgetFormat = (UBYTE *)"Delete|Cancel";
    arg[0] = n;
    if (test) {
        struct Window *rw = BuildEasyRequestArgs(win, &es, 0, arg);
        if (rw != NULL && (ULONG)rw > 1) {
            Delay(50);
            zrzut(win->WScreen, "prefs-kasuj.ppm");
            FreeSysRequest(rw);
        }
        return 0;
    }
    return EasyRequestArgs(win, &es, NULL, arg) == 1;
}

static void kasuj_okno(struct Window *win, int test)
{
    static char tekst[96];
    int n = muzyka_pliki(0);
    if (test) { printf("AmiXcomPrefs: do skasowania %d plikow\n", n); fflush(stdout); }
    if (n == 0) snprintf(tekst, sizeof tekst, "No converted music to delete.");
    else if (!potwierdz_kasowanie(win, n, test)) snprintf(tekst, sizeof tekst, "Nothing deleted.");
    else snprintf(tekst, sizeof tekst, "Deleted %d music files.", muzyka_pliki(1));
    napis_ustaw(win, idx_stan, tekst, pen_txt);
    Delay(50);                 /* gracz zdazy przeczytac, potem stan na nowo */
    odswiez_stan(win);
}

/* linia polecen: CONVERT */
static int konwertuj_shell(void)
{
    char tekst[128];
    int r;
    if (!tryb_konwertowany()) {
        printf("Nothing to convert: MUSIC is %s. Set MUSIC=Samples converted or"
               " MUSIC=AdLib converted first.\n", OPCJE[O_MUSIC].nazwy[wart[O_MUSIC]]);
        return 5;
    }
    printf("Converting the music by running the game - this takes minutes.\n");
    fflush(stdout);
    r = uruchom_konwersje(tekst, (int)sizeof tekst);
    printf("%s\n", tekst);
    return r;
}

/* Konwertowac jest co tylko w trybach "converted" (O_MUSIC 3 i 4);
   przy "live" i "Off" przycisk jest wyszarzony, zeby nie kazac graczowi
   zgadywac, czemu nic sie nie dzieje. */
static int tryb_konwertowany(void)
{
    return wart[O_MUSIC] >= 3;
}

static void odswiez_konw(struct Window *win, struct Gadget *g)
{
    if (g == NULL) return;
    GT_SetGadgetAttrs(g, win, NULL, GA_Disabled, (ULONG)(tryb_konwertowany() ? FALSE : TRUE), TAG_END);
}

static int szer(struct Screen *scr, const char *s)
{
    return (int)TextLength(&scr->RastPort, (CONST_STRPTR)s, (ULONG)strlen(s));
}

/* 1 = zapisz, 0 = anuluj, -1 = okno sie nie otworzylo.
   test_ms > 0: okno otwiera sie, po tym czasie zamyka bez zapisu (test). */
static int okno(int test_ms, int test_konw, int test_kasuj, int test_zapis)
{
    struct Screen *scr;
    APTR vi;
    struct Gadget *glist = NULL, *gad;
    struct Gadget *cykl[O_COUNT];
    struct Gadget *konw_gad = NULL;
    int jest_muzyka;
    struct Window *win;
    struct NewGadget ng;
    STRPTR etyk[O_COUNT][6];
    char maszyna[96];
    int i, j, cw, fh, gh, lm, gap, labw, gadw, hintw, innerw, innerh;
    int leftb, topb, y, btnw;
    int wynik = -1, koniec = 0, czekano = 0;

    scr = LockPubScreen(NULL);
    if (scr == NULL) return -1;
    vi = GetVisualInfo(scr, TAG_END);
    if (vi == NULL) { UnlockPubScreen(NULL, scr); return -1; }

    napisow = 0;
    opis_maszyny(maszyna, (int)sizeof maszyna);
    jest_muzyka = stan_muzyki(stan_txt, (int)sizeof stan_txt);
    /* Zielono, gdy muzyka jest, czerwono, gdy jej nie ma - gracz ma to widziec
     * bez czytania. CIEN NA CZARNO, litery jasne - na szarym tle Workbencha
     * (0xAAAAAA) czarny obrys pod jasna litera daje kontrast w obie strony, a
     * gdy gracz przestawi palete na jasna, czyta sie sam cien. Na ekranie o
     * czterech kolorach ObtainBestPen zwroci to, co najblizsze - dlatego kazdy
     * pen ma zapasowa wartosc w rysuj_napis(). */
    pen_ok = ObtainBestPen(scr->ViewPort.ColorMap, 0x00000000UL, 0xCCCCCCCCUL, 0x11111111UL,
                           OBP_Precision, PRECISION_GUI, TAG_END);
    pen_nie = ObtainBestPen(scr->ViewPort.ColorMap, 0xFFFFFFFFUL, 0x33333333UL, 0x22222222UL,
                            OBP_Precision, PRECISION_GUI, TAG_END);
    pen_txt = ObtainBestPen(scr->ViewPort.ColorMap, 0xFFFFFFFFUL, 0xFFFFFFFFUL, 0xFFFFFFFFUL,
                            OBP_Precision, PRECISION_GUI, TAG_END);
    pen_cien = ObtainBestPen(scr->ViewPort.ColorMap, 0x00000000UL, 0x00000000UL, 0x00000000UL,
                             OBP_Precision, PRECISION_GUI, TAG_END);

    /* wszystko liczone z fontu ekranu - Workbench moze miec dowolny */
    cw = scr->RastPort.TxWidth;  if (cw < 6) cw = 6;
    fh = scr->RastPort.TxHeight; if (fh < 8) fh = 8;
    gh = fh + 6;
    lm = cw * 2;
    gap = fh / 2; if (gap < 4) gap = 4;

    labw = 0; gadw = 0; hintw = 0;
    for (i = 0; i < O_COUNT; i++) {
        int t = szer(scr, OPCJE[i].etykieta) + cw;
        if (t > labw) labw = t;
        for (j = 0; j < OPCJE[i].ile; j++) {
            etyk[i][j] = (STRPTR)OPCJE[i].nazwy[j];
            t = szer(scr, OPCJE[i].nazwy[j]) + cw * 2 + 24;
            if (t > gadw) gadw = t;
            t = szer(scr, OPCJE[i].podpowiedz[j]);
            if (t > hintw) hintw = t;
        }
        etyk[i][OPCJE[i].ile] = NULL;
    }
    /* DWIE KOLUMNY i JEDNA wspolna linia podpowiedzi (2026-09-24): z podpowiedzia
       pod kazda opcja okno mialo 371 px wysokosci i nie miescilo sie na
       Workbenchu 640x256 - a doszly jeszcze jakosc muzyki i konwersja. */
    innerw = lm + (labw + gadw) * 2 + cw * 3 + lm;
    if (lm + hintw + lm > innerw) innerw = lm + hintw + lm;
    if (lm + szer(scr, maszyna) + lm > innerw) innerw = lm + szer(scr, maszyna) + lm;
    if (lm + szer(scr, KLAWISZE) + lm > innerw) innerw = lm + szer(scr, KLAWISZE) + lm;
    if (lm + szer(scr, stan_txt) + lm > innerw) innerw = lm + szer(scr, stan_txt) + lm;
    {   /* cztery przyciski w jednym rzedzie: Save, Convert, Delete, Cancel */
        int b = szer(scr, "Cancel") + cw * 4;
        int rzad;
        if (b < cw * 10) b = cw * 10;
        rzad = lm * 2 + b * 2 + szer(scr, "Convert music") + szer(scr, "Delete music") + cw * 14;
        if (rzad > innerw) innerw = rzad;
    }

    leftb = scr->WBorLeft;
    topb = scr->WBorTop + scr->Font->ta_YSize + 1;

    gad = CreateContext(&glist);
    memset(&ng, 0, sizeof ng);
    ng.ng_TextAttr = scr->Font;
    ng.ng_VisualInfo = vi;
    y = gap;

    for (i = 0; i < O_COUNT; i++) {
        int kol = (i < 5) ? 0 : 1, wiersz = (i < 5) ? i : i - 5;   /* 5 z lewej, reszta z prawej */
        ng.ng_LeftEdge = leftb + lm + labw + kol * (labw + gadw + cw * 3);
        ng.ng_TopEdge = topb + y + wiersz * (gh + 2);
        ng.ng_Width = gadw;
        ng.ng_Height = gh;
        ng.ng_GadgetText = NULL;   /* podpis rysujemy sami, z cieniem */
        ng.ng_GadgetID = GID_OPCJA + i;
        ng.ng_Flags = 0;
        dodaj_napis(leftb + lm + kol * (labw + gadw + cw * 3),
                    ng.ng_TopEdge + (gh - fh) / 2, labw, OPCJE[i].etykieta, pen_txt);
        gad = CreateGadget(CYCLE_KIND, gad, &ng,
                           GTCY_Labels, (ULONG)etyk[i],
                           GTCY_Active, (ULONG)wart[i], TAG_END);
        cykl[i] = gad;
    }
    y += 5 * (gh + 2) + gap;

    /* Cztery wiersze opisu - nasze, z cieniem. Podpowiedz i stan muzyki
       zmieniaja sie w trakcie, wiec trzymamy ich numery. */
    idx_podp = dodaj_napis(leftb + lm, topb + y, innerw - lm * 2,
                           OPCJE[0].podpowiedz[wart[0]], pen_txt);
    y += fh + gap + 2;
    dodaj_napis(leftb + lm, topb + y, innerw - lm * 2, maszyna, pen_txt);
    y += fh + 2;
    dodaj_napis(leftb + lm, topb + y, innerw - lm * 2, KLAWISZE, pen_txt);
    y += fh + 2;
    idx_stan = dodaj_napis(leftb + lm, topb + y, innerw - lm * 2, stan_txt,
                           jest_muzyka ? pen_ok : pen_nie);
    y += fh + gap + gap;

    btnw = szer(scr, "Cancel") + cw * 4;
    if (btnw < cw * 10) btnw = cw * 10;
    ng.ng_LeftEdge = leftb + lm;
    ng.ng_TopEdge = topb + y;
    ng.ng_Width = btnw;
    ng.ng_Height = gh;
    ng.ng_GadgetText = (STRPTR)"Save";
    ng.ng_GadgetID = GID_SAVE;
    ng.ng_Flags = PLACETEXT_IN;
    gad = CreateGadget(BUTTON_KIND, gad, &ng, TAG_END);
    ng.ng_LeftEdge = leftb + innerw - lm - btnw;
    ng.ng_GadgetText = (STRPTR)"Cancel";
    ng.ng_GadgetID = GID_CANCEL;
    gad = CreateGadget(BUTTON_KIND, gad, &ng, TAG_END);
    ng.ng_Width = szer(scr, "Convert music") + cw * 4;
    ng.ng_LeftEdge = leftb + lm + btnw + cw * 2;
    ng.ng_GadgetText = (STRPTR)"Convert music";
    ng.ng_GadgetID = GID_KONW;
    gad = CreateGadget(BUTTON_KIND, gad, &ng, TAG_END);
    konw_gad = gad;
    ng.ng_Width = szer(scr, "Delete music") + cw * 4;
    ng.ng_LeftEdge = leftb + innerw - lm - btnw - cw * 2 - ng.ng_Width;
    ng.ng_GadgetText = (STRPTR)"Delete music";
    ng.ng_GadgetID = GID_KASUJ;
    gad = CreateGadget(BUTTON_KIND, gad, &ng, TAG_END);
    y += gh + gap;
    innerh = y;

    if (gad == NULL) {   /* jeden nieudany CreateGadget -> NULL do konca */
        FreeGadgets(glist); FreeVisualInfo(vi); UnlockPubScreen(NULL, scr);
        return -1;
    }

    win = OpenWindowTags(NULL,
        WA_Title, (ULONG)"AmiXcom - Amiga Settings",
        WA_InnerWidth, (ULONG)innerw,
        WA_InnerHeight, (ULONG)innerh,
        WA_Left, (ULONG)(scr->Width > innerw ? (scr->Width - innerw) / 2 : 0),
        WA_Top, (ULONG)(scr->Height > innerh ? (scr->Height - innerh) / 3 : 0),
        WA_DragBar, TRUE,
        WA_DepthGadget, TRUE,
        WA_CloseGadget, TRUE,
        WA_Activate, TRUE,
        WA_SmartRefresh, TRUE,
        WA_PubScreen, (ULONG)scr,
        WA_Gadgets, (ULONG)glist,
        WA_IDCMP, IDCMP_CLOSEWINDOW | IDCMP_GADGETUP | IDCMP_REFRESHWINDOW
                  | IDCMP_VANILLAKEY | IDCMP_INTUITICKS,
        TAG_END);
    if (win == NULL) {
        FreeGadgets(glist); FreeVisualInfo(vi); UnlockPubScreen(NULL, scr);
        return -1;
    }
    GT_RefreshWindow(win, NULL);
    rysuj_napisy(win);
    if (test_ms > 0) {
        printf("AmiXcomPrefs: okno otwarte %dx%d na ekranie %dx%d\n",
               (int)win->Width, (int)win->Height, (int)scr->Width, (int)scr->Height);
        fflush(stdout);
    }
    if (test_ms > 0) zrzut(scr, "prefs-okno.ppm");
    if (test_kasuj) kasuj_okno(win, 1);
    if (test_konw) {
        printf("AmiXcomPrefs: test konwersji\n");
        konwertuj_okno(win);
        zrzut(scr, "prefs-konw.ppm");
        printf("AmiXcomPrefs: po konwersji w oknie\n");
    }

    while (!koniec) {
        struct IntuiMessage *msg;
        WaitPort(win->UserPort);
        while ((msg = GT_GetIMsg(win->UserPort)) != NULL) {
            ULONG cls = msg->Class;
            UWORD code = msg->Code;
            struct Gadget *src = (struct Gadget *)msg->IAddress;
            GT_ReplyIMsg(msg);
            switch (cls) {
            case IDCMP_INTUITICKS:   /* co 0,1 s - tylko dla trybu testu */
                if (test_ms > 0) {
                    czekano += 100;
                    if (czekano >= test_ms) { wynik = test_zapis ? 1 : 0; koniec = 1; }
                }
                break;
            case IDCMP_CLOSEWINDOW:
                wynik = 0; koniec = 1;
                break;
            case IDCMP_REFRESHWINDOW:
                GT_BeginRefresh(win);
                GT_EndRefresh(win, TRUE);
                rysuj_napisy(win);   /* nasze napisy Intuition nie odtworzy */
                break;
            case IDCMP_GADGETUP:
                i = (int)src->GadgetID - GID_OPCJA;
                if (i >= 0 && i < O_COUNT) {
                    wart[i] = (int)code;
                    napis_ustaw(win, idx_podp, OPCJE[i].podpowiedz[wart[i]], pen_txt);
                    if (i == O_MUSIC) odswiez_konw(win, konw_gad);
                } else if (src->GadgetID == GID_SAVE) {
                    wynik = 1; koniec = 1;
                } else if (src->GadgetID == GID_KASUJ) {
                    kasuj_okno(win, 0);
                } else if (src->GadgetID == GID_KONW) {
                    konwertuj_okno(win);
                } else if (src->GadgetID == GID_CANCEL) {
                    wynik = 0; koniec = 1;
                }
                break;
            case IDCMP_VANILLAKEY:
                /* klawiatura - na maszynie bez dzialajacej myszy to jedyna droga */
                for (i = 0; i < O_COUNT; i++) {
                    if (code == (UWORD)OPCJE[i].klawisz || code == (UWORD)(OPCJE[i].klawisz + 32)) {
                        wart[i] = (wart[i] + 1) % OPCJE[i].ile;
                        GT_SetGadgetAttrs(cykl[i], win, NULL, GTCY_Active, (ULONG)wart[i], TAG_END);
                        napis_ustaw(win, idx_podp, OPCJE[i].podpowiedz[wart[i]], pen_txt);
                        if (i == O_MUSIC) odswiez_konw(win, konw_gad);
                    }
                }
                if (code == 's' || code == 'S' || code == 13) { wynik = 1; koniec = 1; }
                if (code == 27) { wynik = 0; koniec = 1; }
                if (code == 'c' || code == 'C') konwertuj_okno(win);
                if (code == 'd' || code == 'D') kasuj_okno(win, 0);
                break;
            default:
                break;
            }
        }
    }

    CloseWindow(win);
    napisow = 0;
    if (pen_ok >= 0) ReleasePen(scr->ViewPort.ColorMap, (ULONG)pen_ok);
    if (pen_nie >= 0) ReleasePen(scr->ViewPort.ColorMap, (ULONG)pen_nie);
    if (pen_txt >= 0) ReleasePen(scr->ViewPort.ColorMap, (ULONG)pen_txt);
    if (pen_cien >= 0) ReleasePen(scr->ViewPort.ColorMap, (ULONG)pen_cien);
    pen_ok = pen_nie = pen_txt = pen_cien = -1;
    FreeGadgets(glist);
    FreeVisualInfo(vi);
    UnlockPubScreen(NULL, scr);
    return wynik;
}

/* ------------------------------------------------------------------------ */
/*  Linia polecen                                                            */
/* ------------------------------------------------------------------------ */

static int rowne(const char *a, const char *b)
{
    while (*a && *b) {
        if (*a == ' ') { a++; continue; }   /* "AdLib live" = ADLIBLIVE w Shellu */
        if (*b == ' ') { b++; continue; }
        int ca = (*a >= 'A' && *a <= 'Z') ? *a + 32 : *a;
        int cb = (*b >= 'A' && *b <= 'Z') ? *b + 32 : *b;
        if (ca != cb) return 0;
        a++; b++;
    }
    return *a == 0 && *b == 0;
}

static void pokaz(void)
{
    char maszyna[96];
    int i;
    opis_maszyny(maszyna, (int)sizeof maszyna);
    printf("%s\n", maszyna);
    for (i = 0; i < O_COUNT; i++) {
        printf("%-7s %-7s - %s\n", OPCJE[i].arg, OPCJE[i].nazwy[wart[i]],
               OPCJE[i].podpowiedz[wart[i]]);
    }
}

static void pomoc(void)
{
    int i, j;
    printf("AmiXcomPrefs - Amiga settings for AmiXcom\n\n");
    printf("  AmiXcomPrefs              open the window\n");
    printf("  AmiXcomPrefs SHOW         print the settings and this machine\n");
    printf("  AmiXcomPrefs CONVERT      convert the music now (runs the game)\n");
    for (i = 0; i < O_COUNT; i++) {
        printf("  AmiXcomPrefs %s=", OPCJE[i].arg);
        for (j = 0; j < OPCJE[i].ile; j++) printf("%s%s", j ? "|" : "", OPCJE[i].nazwy[j]);
        printf("\n");
    }
    printf("\nAny KEY=VALUE saves at once without a window. File: " PLIK "\n");
}

int main(int argc, char **argv)
{
    int i, j, zmiana = 0, show = 0, test_ms = 0, test_konw = 0, test_kasuj = 0;
    int test_zapis = 0, konw = 0, kasuj = 0, r;

    wczytaj();

    /* argc == 0: start z Workbencha - argv to wtedy komunikat WBStartup */
    for (i = 1; i < argc; i++) {
        char *eq;
        if (argv[i][0] == '?' || rowne(argv[i], "HELP")) { pomoc(); return 0; }
        if (rowne(argv[i], "SHOW")) { show = 1; continue; }
        if (rowne(argv[i], "TESTWINDOW")) { test_ms = 3000; continue; }
        if (rowne(argv[i], "TESTSAVE")) { test_ms = 3000; test_zapis = 1; continue; }
        if (rowne(argv[i], "TESTCONVERT")) { test_ms = 3000; test_konw = 1; continue; }
        if (rowne(argv[i], "TESTDELETE")) { test_ms = 3000; test_kasuj = 1; continue; }
        if (rowne(argv[i], "DELETEMUSIC")) { kasuj = 1; continue; }
        if (rowne(argv[i], "CONVERT")) { konw = 1; continue; }
        eq = strchr(argv[i], '=');
        if (eq != NULL) {
            int ok = 0;
            *eq = 0;
            for (j = 0; j < O_COUNT && !ok; j++) {
                if (rowne(argv[i], OPCJE[j].arg)) {
                    int k;
                    for (k = 0; k < OPCJE[j].ile; k++) {
                        if (rowne(eq + 1, OPCJE[j].nazwy[k])) { wart[j] = k; ok = 1; zmiana = 1; }
                    }
                    if (!ok) {
                        printf("AmiXcomPrefs: bad value \"%s\" for %s\n\n", eq + 1, OPCJE[j].arg);
                        pomoc();
                        return 20;
                    }
                }
            }
            if (ok) continue;
            *eq = '=';
        }
        printf("AmiXcomPrefs: do not understand \"%s\"\n\n", argv[i]);
        pomoc();
        return 20;
    }

    if (zmiana) {
        if (!zapisz()) {
            printf("AmiXcomPrefs: COULD NOT WRITE " PLIK " - is the drawer write protected?\n");
            return 20;
        }
        pokaz();
        printf("saved to " PLIK "\n");
        if (!konw) return 0;
    }
    if (kasuj) { printf("Deleted %d music files.\n", muzyka_pliki(1)); if (!konw) return 0; }
    if (konw) return konwertuj_shell();
    if (show) { pokaz(); return 0; }

    GadToolsBase = OpenLibrary((CONST_STRPTR)"gadtools.library", 37L);
    if (GadToolsBase == NULL) {
        printf("AmiXcomPrefs: no gadtools.library v37 - use the command line:\n\n");
        pomoc();
        return 20;
    }
    r = okno(test_ms, test_konw, test_kasuj, test_zapis);
    CloseLibrary(GadToolsBase);
    GadToolsBase = NULL;

    if (r < 0) {
        printf("AmiXcomPrefs: could not open the window - use the command line:\n\n");
        pomoc();
        return 20;
    }
    if (r == 1) {
        if (!zapisz()) {
            printf("AmiXcomPrefs: COULD NOT WRITE " PLIK "\n");
            return 20;
        }
        if (argc > 0) {   /* z ikony (argc == 0) bez tekstu - inaczej libnix otwiera okno CLI (gracz 0.4.0) */
            pokaz();
            printf("saved to " PLIK "\n");
        }
    }
    if (test_ms > 0) {
        printf("AmiXcomPrefs: okno zamkniete (wynik %d)\n", r);
    }
    return 0;
}
