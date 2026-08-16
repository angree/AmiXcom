/*
 * SDLmini - BMP loading.
 *
 * One caller: Font::loadTerminal(), which decodes the built-in 1bpp DOS font
 * (288x48, bottom-up, uncompressed) and blits it into an 8bpp surface. The
 * loader therefore always produces an 8bpp surface with the file palette
 * indices intact, expanding 1 and 4 bit rows on the way, and refuses anything
 * compressed or truecolour rather than guessing.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "sdlmini.h"

static Uint16 rd16(const Uint8 *p) { return (Uint16)(p[0] | (p[1] << 8)); }
static Uint32 rd32(const Uint8 *p)
{
	return (Uint32)p[0] | ((Uint32)p[1] << 8) | ((Uint32)p[2] << 16) | ((Uint32)p[3] << 24);
}

SDL_Surface *SDL_LoadBMP_RW(SDL_RWops *src, int freesrc)
{
	Uint8 header[54];
	Uint8 palette[256 * 4];
	SDL_Surface *surface = NULL;
	Uint32 dataOffset, headerSize, compression, paletteEntries;
	int width, height, bpp, topDown = 0;
	int srcPitch, y;
	Uint8 *row = NULL;

	if (src == NULL) return NULL;

	if (SDL_RWread(src, header, 1, 54) != 54) {
		SDL_SetError("SDLmini: BMP too short");
		goto done;
	}
	if (header[0] != 'B' || header[1] != 'M') {
		SDL_SetError("SDLmini: not a BMP");
		goto done;
	}

	dataOffset  = rd32(header + 10);
	headerSize  = rd32(header + 14);
	width       = (int)rd32(header + 18);
	height      = (int)(Sint32)rd32(header + 22);
	bpp         = rd16(header + 28);
	compression = rd32(header + 30);
	paletteEntries = rd32(header + 46);

	if (headerSize < 40 || compression != 0) {
		SDL_SetError("SDLmini: only uncompressed BMPs are supported");
		goto done;
	}
	if (bpp != 1 && bpp != 4 && bpp != 8) {
		SDL_SetError("SDLmini: only 1/4/8bpp BMPs are supported (got %d)", bpp);
		goto done;
	}
	if (height < 0) { height = -height; topDown = 1; }
	if (paletteEntries == 0) paletteEntries = (Uint32)1 << bpp;
	if (paletteEntries > 256) paletteEntries = 256;

	surface = SDL_CreateRGBSurface(0, width, height, 8, 0, 0, 0, 0);
	if (surface == NULL) goto done;

	/* Palette: BGRX in the file, RGB in SDL. */
	if (SDL_RWread(src, palette, 1, (int)(paletteEntries * 4)) == (int)(paletteEntries * 4)) {
		Uint32 i;
		for (i = 0; i < paletteEntries; i++) {
			surface->format->palette->colors[i].b = palette[i * 4 + 0];
			surface->format->palette->colors[i].g = palette[i * 4 + 1];
			surface->format->palette->colors[i].r = palette[i * 4 + 2];
			surface->format->palette->colors[i].unused = 255;
		}
	}

	srcPitch = ((width * bpp + 31) / 32) * 4;      /* rows are 4-byte aligned */
	row = (Uint8 *)malloc((size_t)srcPitch);
	if (row == NULL) {
		SDL_FreeSurface(surface);
		surface = NULL;
		SDL_SetError("SDLmini: out of memory reading BMP");
		goto done;
	}

	SDL_RWseek(src, (int)dataOffset, RW_SEEK_SET);
	for (y = 0; y < height; y++) {
		int dstY = topDown ? y : (height - 1 - y);
		Uint8 *dst = (Uint8 *)surface->pixels + (size_t)dstY * surface->pitch;
		int x;

		if (SDL_RWread(src, row, 1, srcPitch) != srcPitch) break;

		switch (bpp) {
			case 8:
				memcpy(dst, row, (size_t)width);
				break;
			case 4:
				for (x = 0; x < width; x++) {
					Uint8 b = row[x / 2];
					dst[x] = (Uint8)((x & 1) ? (b & 0x0f) : (b >> 4));
				}
				break;
			default: /* 1 */
				for (x = 0; x < width; x++) {
					Uint8 b = row[x / 8];
					dst[x] = (Uint8)((b >> (7 - (x & 7))) & 1);
				}
				break;
		}
	}

done:
	free(row);
	if (freesrc && src != NULL) SDL_RWclose(src);
	return surface;
}

int SDL_SaveBMP_RW(SDL_Surface *surface, SDL_RWops *dst, int freedst)
{
	/* Screenshots go through lodepng, so nothing in the port needs this. */
	(void)surface;
	if (freedst && dst != NULL) SDL_RWclose(dst);
	SDL_SetError("SDLmini: BMP writing is not implemented");
	return -1;
}
