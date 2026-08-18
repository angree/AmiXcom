/*
 * AMIGA-PORT: loading splash with a progress bar.
 *
 * From window-open to the title screen the port loads mods for minutes on a
 * real-speed machine with nothing on screen. This module paints one of the
 * intro/ backgrounds (converted at build time by build/gen_splash.py into
 * flat 8-bit chunky + palette, data/common/splash/), overlays the AmiXcom
 * logo (index 255 = transparent), fades the palette in, fills a progress bar
 * while Mod::loadAll works through the ruleset files, and fades to black in
 * ~0.5 s when StartState hands over to the main menu.
 *
 * While the splash is active sdlmini suppresses SDL_Flip and screen palette
 * pushes, so the game's own "Loading..." screen never reaches the display.
 * The game may scribble over the chunky buffer in that time; the bar band is
 * therefore restored from a private copy before every bar blit, and only the
 * bar band is converted. The picture above it stays as planar data.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <proto/graphics.h>

#include "amiga_gfx.h"

#define SPLASH_W 320
#define SPLASH_H 200
#define BAND_Y   184           /* bottom band: bar background */
#define BAR_X0   8
#define BAR_X1   312
#define BAR_Y0   189
#define BAR_Y1   196
#define IDX_FILL 253
#define IDX_BLACK 254

static int s_active;
static int s_shown;
static unsigned char *s_image;      /* private 320x200 copy */
static unsigned char s_pal[768];
static int s_percent = -1;

int AmigaSplash_Active(void)
{
	return s_active;
}

static void set_scaled_palette(int num, int den)
{
	unsigned char tmp[768];
	int i;
	for (i = 0; i < 768; i++)
		tmp[i] = (unsigned char)((s_pal[i] * num) / den);
	amigagfx_set_palette(tmp, 0, 256);
}

static void copy_to_chunky(int y0, int y1)
{
	unsigned char *ch = (unsigned char *)amigagfx_chunky();
	const int pitch = amigagfx_pitch();
	int y;
	if (ch == NULL) return;
	for (y = y0; y < y1; y++)
		memcpy(ch + (long)y * pitch, s_image + (long)y * SPLASH_W, SPLASH_W);
}

void AmigaSplash_Show(void)
{
	FILE *f;
	char path[64];
	unsigned char hd[8];
	int w, h, i, pick;

	if (s_shown) return;
	s_shown = 1;

	/* beam position as the only entropy an Amiga always has at boot */
	pick = (int)(*(volatile unsigned short *)0xdff006) % 6;

	s_image = (unsigned char *)malloc((long)SPLASH_W * SPLASH_H);
	if (s_image == NULL) return;
	memset(s_image, IDX_BLACK, (long)SPLASH_W * SPLASH_H);

	for (i = 0; i < 6; i++) {
		snprintf(path, sizeof path, "PROGDIR:data/common/splash/bg%d.spl", (pick + i) % 6);
		f = fopen(path, "rb");
		if (f != NULL) break;
	}
	if (f == NULL) { free(s_image); s_image = NULL; return; }
	if (fread(hd, 1, 8, f) != 8 || memcmp(hd, "SPL1", 4) != 0) { fclose(f); free(s_image); s_image = NULL; return; }
	w = (hd[4] << 8) | hd[5];
	h = (hd[6] << 8) | hd[7];
	if (w != SPLASH_W || h > SPLASH_H ||
	    fread(s_pal, 1, 768, f) != 768 ||
	    fread(s_image, 1, (long)w * h, f) != (size_t)((long)w * h)) {
		fclose(f); free(s_image); s_image = NULL; return;
	}
	fclose(f);

	/* logo, bottom-right, above the bar band; 255 = transparent */
	f = fopen("PROGDIR:data/common/splash/logo.spl", "rb");
	if (f != NULL) {
		if (fread(hd, 1, 8, f) == 8 && memcmp(hd, "SPLG", 4) == 0) {
			const int lw = (hd[4] << 8) | hd[5];
			const int lh = (hd[6] << 8) | hd[7];
			if (lw <= SPLASH_W && lh <= BAND_Y) {
				const int lx = SPLASH_W - lw - 4;
				const int ly = BAND_Y - lh - 4;
				unsigned char *row = (unsigned char *)malloc(lw);
				int y, x;
				if (row != NULL) {
					for (y = 0; y < lh; y++) {
						if (fread(row, 1, lw, f) != (size_t)lw) break;
						for (x = 0; x < lw; x++)
							if (row[x] != 255)
								s_image[(long)(ly + y) * SPLASH_W + lx + x] = row[x];
					}
					free(row);
				}
			}
		}
		fclose(f);
	}

	/* palette to black, image to the screen, then fade in over ~10 frames */
	set_scaled_palette(0, 16);
	copy_to_chunky(0, SPLASH_H);
	amigagfx_blit(0, 0, SPLASH_W, SPLASH_H);
	for (i = 1; i <= 10; i++) {
		WaitTOF();
		set_scaled_palette(i, 10);
	}
	s_active = 1;
	s_percent = -1;
}

/* percent 0..100; redraws and converts only the bar band */
void AmigaSplash_Progress(int percent)
{
	int y, fillw;
	if (!s_active || s_image == NULL) return;
	if (percent < 0) percent = 0;
	if (percent > 100) percent = 100;
	if (percent <= s_percent) return;
	s_percent = percent;

	fillw = ((BAR_X1 - BAR_X0) * percent) / 100;
	for (y = BAR_Y0; y < BAR_Y1; y++) {
		unsigned char *row = s_image + (long)y * SPLASH_W;
		memset(row + BAR_X0, IDX_FILL, fillw);
		memset(row + BAR_X0 + fillw, IDX_BLACK, (BAR_X1 - BAR_X0) - fillw);
	}
	copy_to_chunky(BAND_Y, SPLASH_H);
	amigagfx_blit(0, BAND_Y, SPLASH_W, SPLASH_H - BAND_Y);
}

/* fill to 100%, fade to black in ~0.5 s, release */
void AmigaSplash_End(void)
{
	int i;
	if (!s_active) return;
	AmigaSplash_Progress(100);
	for (i = 11; i >= 0; i--) {
		WaitTOF();
		WaitTOF();
		set_scaled_palette(i, 12);
	}
	s_active = 0;
	if (s_image != NULL) { free(s_image); s_image = NULL; }
}
