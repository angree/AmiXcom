/*
 * SDLmini - SDL_image, reduced to what OpenXcom actually loads through it:
 * Windows BMP and IFF LBM. PNG never comes through here (the game decodes its
 * own PNGs with lodepng); anything else is refused with a named reason rather
 * than a silent NULL.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "SDL_image.h"
#include "sdlmini.h"

SDL_Surface *SDLmini_LoadLBM(const Uint8 *data, Uint32 size);

/* The format is decided by content, not by the file name: X-COM's data has
 * both .LBM and .BDY spellings and mods are not consistent either. */
SDL_Surface *IMG_Load_RW(SDL_RWops *src, int freesrc)
{
	Uint8 magic[12];
	int size, n;
	Uint8 *buf;
	SDL_Surface *surf = NULL;

	if (src == NULL) return NULL;

	size = SDL_RWseek(src, 0, RW_SEEK_END);
	SDL_RWseek(src, 0, RW_SEEK_SET);
	if (size < 12) {
		SDL_SetError("SDLmini: image file is too short to identify");
		if (freesrc) SDL_RWclose(src);
		return NULL;
	}

	n = SDL_RWread(src, magic, 1, 12);
	SDL_RWseek(src, 0, RW_SEEK_SET);
	if (n < 12) {
		SDL_SetError("SDLmini: image file is too short to identify");
		if (freesrc) SDL_RWclose(src);
		return NULL;
	}

	if (magic[0] == 'B' && magic[1] == 'M') {
		return SDL_LoadBMP_RW(src, freesrc);
	}

	if (memcmp(magic, "FORM", 4) == 0 &&
	    (memcmp(magic + 8, "PBM ", 4) == 0 || memcmp(magic + 8, "ILBM", 4) == 0)) {
		SDLmini_Log("SDLmini: decoding an IFF image");
		buf = (Uint8 *)malloc((size_t)size);
		if (buf == NULL) {
			SDL_SetError("SDLmini: out of memory reading an image");
		} else {
			SDL_RWread(src, buf, 1, size);
			surf = SDLmini_LoadLBM(buf, (Uint32)size);
			free(buf);
		}
		if (freesrc) SDL_RWclose(src);
		return surf;
	}

	/* %02lx, not %02x: printf on this libc takes 16 bits for %x. */
	SDL_SetError("SDLmini: unsupported image format (starts %02lx %02lx %02lx %02lx)",
	             (unsigned long)magic[0], (unsigned long)magic[1],
	             (unsigned long)magic[2], (unsigned long)magic[3]);
	if (freesrc) SDL_RWclose(src);
	return NULL;
}

SDL_Surface *IMG_Load(const char *file)
{
	SDL_RWops *rw;

	if (file == NULL) return NULL;
	rw = SDL_RWFromFile(file, "rb");
	if (rw == NULL) {
		SDL_SetError("SDLmini: cannot open an image file");
		return NULL;
	}
	return IMG_Load_RW(rw, 1);
}

const char *IMG_GetError(void)
{
	return SDL_GetError();
}
