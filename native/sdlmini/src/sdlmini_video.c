/*
 * SDLmini - surfaces, blitting and the video "mode".
 *
 * The whole port is 8 bits per pixel by design: 320x200x8 is what X-COM is,
 * what AGA can push through a c2p at a playable rate, and what an 8-bit RTG
 * screen takes without conversion. The 32bpp paths OpenXcom carries for HQX
 * and OpenGL are removed from the game tree, not emulated here - a 32bpp blit
 * that silently half-works would be worse than a link error.
 *
 * The one exception is surface ALLOCATION: screenshots and the debug map
 * dumper allocate 24bpp surfaces and write their pixels by hand without ever
 * blitting them. Those are allowed, and only the blitters refuse anything that
 * is not 8 -> 8.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "sdlmini.h"
#include "amiga_gfx.h"

static SDL_Surface *s_screen;
int SDLmini_diag_armed; /* TEMP: set by the game after the globe blit */
unsigned long SDLmini_flips;  /* one per rendered frame (SDL_Flip) */
static int          s_backend = 0;            /* AMIGAGFX_BACKEND_AGA */
static int          s_video_ready;

void SDLmini_SetBackend(int backend) { s_backend = backend; }
int  SDLmini_GetBackend(void)        { return s_backend; }

SDL_Surface *SDLmini_ScreenSurface(void) { return s_screen; }

void SDLmini_VideoInit(void) { s_video_ready = 1; }

void SDLmini_VideoQuit(void)
{
	if (s_screen != NULL) {
		/* The screen surface never owns its pixels - they belong to
		 * amiga_gfx.c chunky buffer - so only the wrapper goes. */
		free(s_screen->format->palette->colors);
		free(s_screen->format->palette);
		free(s_screen->format);
		free(s_screen);
		s_screen = NULL;
	}
	if (s_video_ready) {
		amigagfx_close();
		s_video_ready = 0;
	}
}

/* ------------------------------------------------------------- pixel fmt -- */

static SDL_PixelFormat *alloc_format(int bpp, Uint32 rmask, Uint32 gmask, Uint32 bmask, Uint32 amask)
{
	SDL_PixelFormat *fmt = (SDL_PixelFormat *)calloc(1, sizeof(SDL_PixelFormat));
	if (fmt == NULL) return NULL;

	fmt->BitsPerPixel  = (Uint8)bpp;
	fmt->BytesPerPixel = (Uint8)((bpp + 7) / 8);
	fmt->alpha         = SDL_ALPHA_OPAQUE;

	if (bpp == 8) {
		SDL_Palette *pal = (SDL_Palette *)calloc(1, sizeof(SDL_Palette));
		if (pal == NULL) { free(fmt); return NULL; }
		pal->ncolors = 256;
		pal->colors  = (SDL_Color *)calloc(256, sizeof(SDL_Color));
		if (pal->colors == NULL) { free(pal); free(fmt); return NULL; }
		fmt->palette = pal;
		return fmt;
	}

	/* Truecolour surfaces exist only to be written into and handed to
	 * lodepng, so the masks are recorded and nothing more is derived from
	 * them than the shifts those writers use. */
	fmt->Rmask = rmask; fmt->Gmask = gmask; fmt->Bmask = bmask; fmt->Amask = amask;
	if (rmask == 0x0000ffUL) { fmt->Rshift = 0;  fmt->Gshift = 8;  fmt->Bshift = 16; }
	else                     { fmt->Rshift = 16; fmt->Gshift = 8;  fmt->Bshift = 0;  }
	fmt->Ashift = 24;
	return fmt;
}

static void free_format(SDL_PixelFormat *fmt)
{
	if (fmt == NULL) return;
	if (fmt->palette != NULL) {
		free(fmt->palette->colors);
		free(fmt->palette);
	}
	free(fmt);
}

/* ------------------------------------------------------------- surfaces -- */

static SDL_Surface *new_surface(int w, int h, int bpp, int pitch,
                                Uint32 rmask, Uint32 gmask, Uint32 bmask, Uint32 amask,
                                void *pixels)
{
	SDL_Surface *s = (SDL_Surface *)calloc(1, sizeof(SDL_Surface));
	if (s == NULL) { SDL_SetError("out of memory (surface header)"); return NULL; }

	s->format = alloc_format(bpp, rmask, gmask, bmask, amask);
	if (s->format == NULL) { free(s); SDL_SetError("out of memory (pixel format)"); return NULL; }

	s->w        = w;
	s->h        = h;
	s->pitch    = (Uint16)pitch;
	s->refcount = 1;
	s->clip_rect.x = 0;
	s->clip_rect.y = 0;
	s->clip_rect.w = (Uint16)w;
	s->clip_rect.h = (Uint16)h;

	if (pixels != NULL) {
		s->pixels = pixels;
		s->flags |= SDL_PREALLOC;
	} else {
		s->pixels = calloc(1, (size_t)pitch * (size_t)h);
		if (s->pixels == NULL) {
			free_format(s->format);
			free(s);
			SDL_SetError("out of memory (%d x %d x %dbpp surface)", w, h, bpp);
			return NULL;
		}
	}
	return s;
}

SDL_Surface *SDL_CreateRGBSurface(Uint32 flags, int width, int height, int depth,
                                  Uint32 Rmask, Uint32 Gmask, Uint32 Bmask, Uint32 Amask)
{
	int bpp   = (depth + 7) / 8;
	int pitch = (width * bpp + 3) & ~3;         /* SDL aligns rows to 4 bytes */
	SDL_Surface *s = new_surface(width, height, depth, pitch, Rmask, Gmask, Bmask, Amask, NULL);
	if (s != NULL) s->flags |= (flags & SDL_SRCCOLORKEY);
	return s;
}

SDL_Surface *SDL_CreateRGBSurfaceFrom(void *pixels, int width, int height, int depth, int pitch,
                                      Uint32 Rmask, Uint32 Gmask, Uint32 Bmask, Uint32 Amask)
{
	return new_surface(width, height, depth, pitch, Rmask, Gmask, Bmask, Amask, pixels);
}

void SDL_FreeSurface(SDL_Surface *surface)
{
	if (surface == NULL) return;
	if (surface == s_screen) return;            /* owned by SDLmini_VideoQuit */
	if (--surface->refcount > 0) return;
	if (!(surface->flags & SDL_PREALLOC)) free(surface->pixels);
	free_format(surface->format);
	free(surface);
}

SDL_Surface *SDL_ConvertSurface(SDL_Surface *src, SDL_PixelFormat *fmt, Uint32 flags)
{
	SDL_Surface *dst;

	if (src == NULL) return NULL;
	if (fmt->BitsPerPixel != src->format->BitsPerPixel) {
		SDL_SetError("SDLmini: conversion between depths is not supported (%d -> %d)",
		             src->format->BitsPerPixel, fmt->BitsPerPixel);
		return NULL;
	}

	dst = SDL_CreateRGBSurface(flags, src->w, src->h, src->format->BitsPerPixel,
	                           fmt->Rmask, fmt->Gmask, fmt->Bmask, fmt->Amask);
	if (dst == NULL) return NULL;

	{
		int y;
		int bytes = src->w * src->format->BytesPerPixel;
		for (y = 0; y < src->h; y++) {
			memcpy((Uint8 *)dst->pixels + (size_t)y * dst->pitch,
			       (Uint8 *)src->pixels + (size_t)y * src->pitch, (size_t)bytes);
		}
	}
	if (src->format->palette != NULL && dst->format->palette != NULL) {
		memcpy(dst->format->palette->colors, src->format->palette->colors,
		       (size_t)src->format->palette->ncolors * sizeof(SDL_Color));
		dst->format->palette->ncolors = src->format->palette->ncolors;
	}
	dst->format->colorkey = src->format->colorkey;
	dst->flags |= (src->flags & SDL_SRCCOLORKEY);
	return dst;
}


/* One-shot markers. The game crashed on its first drawn frame with a bus
 * error and the log stopped at "started successfully", so every entry point
 * the first frame goes through says so exactly once. Cheap enough to leave in
 * until the port is reliable: one comparison per call. */
#define SDLMINI_FIRST(tag) do { 	static int once_; 	if (!once_) { once_ = 1; SDLmini_Log("SDLmini: first " tag); } } while (0)

int SDL_LockSurface(SDL_Surface *surface)    { (void)surface; return 0; }
void SDL_UnlockSurface(SDL_Surface *surface) { (void)surface; }

int SDL_SetColorKey(SDL_Surface *surface, Uint32 flag, Uint32 key)
{
	if (surface == NULL) return -1;
	{
		static int logged_;
		if (logged_ < 6) {
			char b[128];
			snprintf(b, sizeof b, "SDLmini: SetColorKey(%dx%d, flag %lx, key %lu) flags before %lx", surface->w, surface->h, (unsigned long)flag, (unsigned long)key, (unsigned long)surface->flags);
			SDLmini_Log(b);
			logged_++;
		}
	}
	if (flag & SDL_SRCCOLORKEY) {
		surface->flags |= SDL_SRCCOLORKEY;
		surface->format->colorkey = key;
	} else {
		surface->flags &= ~SDL_SRCCOLORKEY;
		surface->format->colorkey = 0;
	}
	return 0;
}

SDL_bool SDL_SetClipRect(SDL_Surface *surface, const SDL_Rect *rect)
{
	SDL_Rect full;
	if (surface == NULL) return SDL_FALSE;

	full.x = 0; full.y = 0;
	full.w = (Uint16)surface->w; full.h = (Uint16)surface->h;
	if (rect == NULL) {
		surface->clip_rect = full;
		return SDL_TRUE;
	}
	{
		int x1 = rect->x, y1 = rect->y;
		int x2 = rect->x + rect->w, y2 = rect->y + rect->h;
		if (x1 < 0) x1 = 0;
		if (y1 < 0) y1 = 0;
		if (x2 > surface->w) x2 = surface->w;
		if (y2 > surface->h) y2 = surface->h;
		if (x2 <= x1 || y2 <= y1) {
			surface->clip_rect.x = surface->clip_rect.y = 0;
			surface->clip_rect.w = surface->clip_rect.h = 0;
			return SDL_FALSE;
		}
		surface->clip_rect.x = (Sint16)x1;
		surface->clip_rect.y = (Sint16)y1;
		surface->clip_rect.w = (Uint16)(x2 - x1);
		surface->clip_rect.h = (Uint16)(y2 - y1);
	}
	return SDL_TRUE;
}

void SDL_GetClipRect(SDL_Surface *surface, SDL_Rect *rect)
{
	if (surface != NULL && rect != NULL) *rect = surface->clip_rect;
}

/* ------------------------------------------------------------- palettes -- */

static void push_palette_to_screen(const SDL_Color *colors, int first, int n)
{
	unsigned char rgb[256 * 3];
	int i;
	if (n > 256) n = 256;
	for (i = 0; i < n; i++) {
		rgb[i * 3 + 0] = colors[i].r;
		rgb[i * 3 + 1] = colors[i].g;
		rgb[i * 3 + 2] = colors[i].b;
	}

	/* Report the first few full-palette loads. A ramp test proved the path
	 * from here to the AGA colour registers is exact, so when the screen
	 * comes up in the wrong hues the question is what the GAME asked for -
	 * and that is only answerable by printing it. Capped, because a full
	 * load happens on every screen change. */
	if (first == 0 && n >= 256) {
		static int dumps;
		if (dumps < 3) {
			char line[160];
			int k;
			dumps++;
			SDLmini_Log("SDLmini: full palette set, sampling it:");
			for (k = 0; k < 256; k += 32) {
				snprintf(line, sizeof(line),
				         "  [%3ld] %3ld,%3ld,%3ld   [%3ld] %3ld,%3ld,%3ld",
				         (long)k,
				         (long)rgb[k*3], (long)rgb[k*3+1], (long)rgb[k*3+2],
				         (long)(k + 16),
				         (long)rgb[(k+16)*3], (long)rgb[(k+16)*3+1], (long)rgb[(k+16)*3+2]);
				SDLmini_Log(line);
			}
		}
	}

	amigagfx_set_palette(rgb, first, n);
}

int SDL_SetColors(SDL_Surface *surface, SDL_Color *colors, int firstcolor, int ncolors)
{
	SDLMINI_FIRST("SDL_SetColors");
	SDL_Palette *pal;

	if (surface == NULL || surface->format->palette == NULL) return 0;
	pal = surface->format->palette;
	if (firstcolor < 0 || firstcolor + ncolors > pal->ncolors) return 0;

	memcpy(&pal->colors[firstcolor], colors, (size_t)ncolors * sizeof(SDL_Color));
	if (surface == s_screen) push_palette_to_screen(colors, firstcolor, ncolors);
	return 1;
}

int SDL_SetPalette(SDL_Surface *surface, int flags, SDL_Color *colors, int firstcolor, int ncolors)
{
	(void)flags;
	return SDL_SetColors(surface, colors, firstcolor, ncolors);
}

Uint32 SDL_MapRGB(const SDL_PixelFormat *format, Uint8 r, Uint8 g, Uint8 b)
{
	if (format->palette == NULL) {
		return ((Uint32)r << format->Rshift) | ((Uint32)g << format->Gshift) | ((Uint32)b << format->Bshift);
	}
	{
		/* Nearest match in the palette. Called a handful of times per run,
		 * never per pixel, so a linear scan is the right amount of code. */
		int i, best = 0;
		long bestd = 0x7fffffffL;
		for (i = 0; i < format->palette->ncolors; i++) {
			long dr = (long)format->palette->colors[i].r - r;
			long dg = (long)format->palette->colors[i].g - g;
			long db = (long)format->palette->colors[i].b - b;
			long d  = dr * dr + dg * dg + db * db;
			if (d < bestd) { bestd = d; best = i; if (d == 0) break; }
		}
		return (Uint32)best;
	}
}

void SDL_GetRGB(Uint32 pixel, const SDL_PixelFormat *format, Uint8 *r, Uint8 *g, Uint8 *b)
{
	if (format->palette != NULL) {
		int i = (int)(pixel & 0xff);
		*r = format->palette->colors[i].r;
		*g = format->palette->colors[i].g;
		*b = format->palette->colors[i].b;
	} else {
		*r = (Uint8)((pixel >> format->Rshift) & 0xff);
		*g = (Uint8)((pixel >> format->Gshift) & 0xff);
		*b = (Uint8)((pixel >> format->Bshift) & 0xff);
	}
}

void SDL_GetRGBA(Uint32 pixel, const SDL_PixelFormat *format, Uint8 *r, Uint8 *g, Uint8 *b, Uint8 *a)
{
	SDL_GetRGB(pixel, format, r, g, b);
	*a = SDL_ALPHA_OPAQUE;
}

/* --------------------------------------------------------------- blits -- */

/* TEMP perf counters (LISTA-ROBOT pkt 1): exact work counts per 100 frames,
 * logged from SDL_Flip. Pixel counts are exact; times use the 20 ms tick and
 * only mean anything summed over many frames. */
static unsigned long s_perf_blits, s_perf_blits_ck;      /* calls */
static unsigned long s_perf_px, s_perf_px_ck;            /* pixels copied */
static unsigned long s_perf_fills, s_perf_fill_px;
static unsigned long s_perf_c2p_ms, s_perf_last_ms;

int SDL_FillRect(SDL_Surface *dst, SDL_Rect *dstrect, Uint32 color)
{
	int x, y, w, h, bpp;
	if (dst == NULL) return -1;
	bpp = dst->format->BytesPerPixel;

	if (dstrect == NULL) {
		x = dst->clip_rect.x; y = dst->clip_rect.y;
		w = dst->clip_rect.w; h = dst->clip_rect.h;
	} else {
		int cx1 = dst->clip_rect.x, cy1 = dst->clip_rect.y;
		int cx2 = cx1 + dst->clip_rect.w, cy2 = cy1 + dst->clip_rect.h;
		int x1 = dstrect->x, y1 = dstrect->y;
		int x2 = x1 + dstrect->w, y2 = y1 + dstrect->h;
		if (x1 < cx1) x1 = cx1;
		if (y1 < cy1) y1 = cy1;
		if (x2 > cx2) x2 = cx2;
		if (y2 > cy2) y2 = cy2;
		if (x2 <= x1 || y2 <= y1) return 0;
		x = x1; y = y1; w = x2 - x1; h = y2 - y1;
	}
	s_perf_fills++;
	s_perf_fill_px += (unsigned long)w * h;

	{
		/* TEMP diagnostic (see SDL_UpperBlit): large fills of the 320x200
		 * back buffer while it holds real content in the left area. */
		static int logged_;
		if (SDLmini_diag_armed && dst != s_screen && dst->w == 320 && dst->h == 200 && w * h > 20000 && logged_ < 8) {
			long nz = 0; int xx, yy;
			for (yy = 0; yy < 200; yy++) {
				const Uint8 *p = (const Uint8 *)dst->pixels + (size_t)yy * dst->pitch;
				for (xx = 0; xx < 256; xx++) if (p[xx]) nz++;
			}
			if (nz > 15000) {
				char b[128];
				snprintf(b, sizeof b, "SDLmini: FillRect WIPES back buffer (%ld px) %d,%d %dx%d color %lu", nz, x, y, w, h, (unsigned long)color);
				SDLmini_Log(b);
				logged_++;
			}
		}
	}
	if (bpp == 1) {
		Uint8 *row = (Uint8 *)dst->pixels + (size_t)y * dst->pitch + x;
		for (; h > 0; h--, row += dst->pitch) memset(row, (int)(color & 0xff), (size_t)w);
	} else {
		int i;
		Uint8 *row = (Uint8 *)dst->pixels + (size_t)y * dst->pitch + (size_t)x * bpp;
		for (; h > 0; h--, row += dst->pitch) {
			Uint8 *p = row;
			for (i = 0; i < w; i++) {
				memcpy(p, &color, (size_t)bpp);
				p += bpp;
			}
		}
	}
	return 0;
}

/* 8 -> 8 blit, the only one the game needs. Straight memcpy per row unless a
 * colour key is set, in which case it is a per-pixel test - the same shape as
 * SDL blit_1 without the palette-mapping table, since every surface here
 * shares one 256-entry palette. */
static void blit8(const SDL_Surface *src, const SDL_Rect *srcrect,
                  SDL_Surface *dst, const SDL_Rect *dstrect)
{
	int y;
	const Uint8 *sp = (const Uint8 *)src->pixels + (size_t)srcrect->y * src->pitch + srcrect->x;
	Uint8       *dp = (Uint8 *)dst->pixels       + (size_t)dstrect->y * dst->pitch + dstrect->x;
	int w = srcrect->w, h = srcrect->h;

	if (src->flags & SDL_SRCCOLORKEY) {
		/* Colorkey blit, 4 pixels at a time (LISTA-ROBOT pkt 2, wariant A).
		 * Measured before this change: ~330k colorkey pixels per geoscape
		 * frame (the globe's radar/country/marker layers are ~95% transparent
		 * and full-screen). One longword compare skips 4 transparent pixels;
		 * one longword store copies 4 opaque ones. The mixed case - only at
		 * sprite edges - falls back to bytes. The has-a-key-byte test is the
		 * classic (x-0x01010101) & ~x & 0x80808080 trick, no per-byte
		 * compares. 68020 takes unaligned longword accesses. */
		Uint8  key  = (Uint8)(src->format->colorkey & 0xff);
		Uint32 key4 = (Uint32)key * 0x01010101UL;
		s_perf_blits_ck++;
		s_perf_px_ck += (unsigned long)w * h;
		for (y = 0; y < h; y++) {
			const Uint8 *s = sp;
			Uint8 *d = dp;
			int n = w;
			while (n >= 4) {
				Uint32 v;
				memcpy(&v, s, 4);
				if (v != key4) {
					Uint32 xk = v ^ key4;
					if (((xk - 0x01010101UL) & ~xk & 0x80808080UL) == 0) {
						memcpy(d, &v, 4);
					} else {
						if (s[0] != key) d[0] = s[0];
						if (s[1] != key) d[1] = s[1];
						if (s[2] != key) d[2] = s[2];
						if (s[3] != key) d[3] = s[3];
					}
				}
				s += 4; d += 4; n -= 4;
			}
			while (n-- > 0) {
				Uint8 c = *s++;
				if (c != key) *d = c;
				d++;
			}
			sp += src->pitch;
			dp += dst->pitch;
		}
	} else {
		s_perf_blits++;
		s_perf_px += (unsigned long)w * h;
		for (y = 0; y < h; y++) {
			memcpy(dp, sp, (size_t)w);
			sp += src->pitch;
			dp += dst->pitch;
		}
	}
}

int SDL_UpperBlit(SDL_Surface *src, SDL_Rect *srcrect, SDL_Surface *dst, SDL_Rect *dstrect)
{
	SDLMINI_FIRST("SDL_UpperBlit");
	SDL_Rect sr, dr;
	int cx1, cy1, cx2, cy2;

	if (src == NULL || dst == NULL) return -1;

	if (src->format->BitsPerPixel != 8 || dst->format->BitsPerPixel != 8) {
		SDL_SetError("SDLmini: only 8bpp blits exist in this port (%d -> %d)",
		             src->format->BitsPerPixel, dst->format->BitsPerPixel);
		return -1;
	}

	if (srcrect != NULL) {
		sr = *srcrect;
	} else {
		sr.x = 0; sr.y = 0; sr.w = (Uint16)src->w; sr.h = (Uint16)src->h;
	}
	dr.x = (Sint16)(dstrect != NULL ? dstrect->x : 0);
	dr.y = (Sint16)(dstrect != NULL ? dstrect->y : 0);

	/* Clip the source rectangle to the source surface. */
	if (sr.x < 0) { sr.w = (Uint16)(sr.w + sr.x); dr.x = (Sint16)(dr.x - sr.x); sr.x = 0; }
	if (sr.y < 0) { sr.h = (Uint16)(sr.h + sr.y); dr.y = (Sint16)(dr.y - sr.y); sr.y = 0; }
	if (sr.x + sr.w > src->w) sr.w = (Uint16)(src->w - sr.x);
	if (sr.y + sr.h > src->h) sr.h = (Uint16)(src->h - sr.y);
	if ((Sint16)sr.w <= 0 || (Sint16)sr.h <= 0) goto empty;

	/* Clip against the destination clip rectangle, moving the source origin
	 * by the same amount. */
	cx1 = dst->clip_rect.x;
	cy1 = dst->clip_rect.y;
	cx2 = cx1 + dst->clip_rect.w;
	cy2 = cy1 + dst->clip_rect.h;

	if (dr.x < cx1) { int d = cx1 - dr.x; sr.x = (Sint16)(sr.x + d); sr.w = (Uint16)(sr.w - d); dr.x = (Sint16)cx1; }
	if (dr.y < cy1) { int d = cy1 - dr.y; sr.y = (Sint16)(sr.y + d); sr.h = (Uint16)(sr.h - d); dr.y = (Sint16)cy1; }
	if ((Sint16)sr.w <= 0 || (Sint16)sr.h <= 0) goto empty;
	if (dr.x + sr.w > cx2) sr.w = (Uint16)(cx2 - dr.x);
	if (dr.y + sr.h > cy2) sr.h = (Uint16)(cy2 - dr.y);
	if ((Sint16)sr.w <= 0 || (Sint16)sr.h <= 0) goto empty;

	dr.w = sr.w;
	dr.h = sr.h;
	blit8(src, &sr, dst, &dr);
	if (dstrect != NULL) *dstrect = dr;
	{
		/* TEMP diagnostic: who wipes the left 256 columns of the 320x200
		 * back buffer between the globe blit and the flip? */
		static long prev_;
		static int logged_;
		if (SDLmini_diag_armed && dst != s_screen && dst->w == 320 && dst->h == 200 && logged_ < 6) {
			long nz = 0; int x, y;
			for (y = 0; y < 200; y++) {
				const Uint8 *p = (const Uint8 *)dst->pixels + (size_t)y * dst->pitch;
				for (x = 0; x < 256; x++) if (p[x]) nz++;
			}
			if (nz + 2000 < prev_) {
				char b[200];
				snprintf(b, sizeof b, "SDLmini: blit DROPPED left-area count %ld -> %ld: src %dx%d at %d,%d (srcrect %d,%d %dx%d) colorkey %lu flags %lx",
					prev_, nz, src->w, src->h, (int)dr.x, (int)dr.y, (int)sr.x, (int)sr.y, (int)sr.w, (int)sr.h,
					(unsigned long)src->format->colorkey, (unsigned long)src->flags);
				SDLmini_Log(b);
				logged_++;
			}
			prev_ = nz;
		}
	}
	return 0;

empty:
	if (dstrect != NULL) { dstrect->w = 0; dstrect->h = 0; }
	return 0;
}

/* ------------------------------------------------------------ video mode -- */

int SDLmini_show_bar = 0;          /* Options::amigaAppBar, set before SDL_SetVideoMode */
static int s_req_w = 0, s_req_h = 0; /* what the game asked for (the screen may be taller) */

SDL_Surface *SDL_SetVideoMode(int width, int height, int bpp, Uint32 flags)
{
	char msg[128];

	(void)flags;
	if (bpp != 8) {
		SDL_SetError("SDLmini: only 8bpp video modes exist (asked for %d)", bpp);
		return NULL;
	}

	if (s_screen != NULL) {
		/* Reopening the same geometry is what OpenXcom does on every options
		 * change; there is nothing to do, and reopening the screen would
		 * flash the display for no reason. */
		if (s_req_w == width && s_req_h == height) return s_screen;
		SDLmini_VideoQuit();
		s_video_ready = 1;
	}
	s_req_w = width;
	s_req_h = height;

	/* The "Amiga screen title bar" option (SDLmini_show_bar, set by the game
	 * from Options::amigaAppBar): keep Intuition's bar with the depth gadget.
	 * amigagfx opens the screen bar-many lines TALLER in that case, so the
	 * game area below the bar is still exactly width x height and mouse
	 * coordinates stay 1:1. Meaningless for the WB window backend. */
	if (amigagfx_open(width, height, SDLmini_show_bar, s_backend) != 0) {
		SDL_SetError("SDLmini: amigagfx_open(%d, %d, backend %d) failed", width, height, s_backend);
		return NULL;
	}

	s_screen = new_surface(amigagfx_game_width(), amigagfx_game_height(), 8,
	                       amigagfx_pitch(), 0, 0, 0, 0, amigagfx_chunky());
	if (s_screen == NULL) {
		amigagfx_close();
		return NULL;
	}
	s_screen->flags |= SDL_HWSURFACE | SDL_FULLSCREEN;

	snprintf(msg, sizeof(msg), "SDLmini: video %ldx%ld 8bpp, backend %ld, pitch %ld",
	        (long)s_screen->w, (long)s_screen->h, (long)amigagfx_backend(), (long)s_screen->pitch);
	SDLmini_Log(msg);
	return s_screen;
}

int SDL_Flip(SDL_Surface *screen)
{
	SDLMINI_FIRST("SDL_Flip");
	if (screen == NULL) return -1;
	if (screen != s_screen) return 0;
	{
		/* TEMP diagnostic: what reaches the flip in the left 256 columns.
		 * SDLmini_flips is exactly one per rendered frame, so anything that
		 * wants to know "am I being called every frame?" can compare against
		 * it (Globe::draw does). */
		unsigned long flips_;
		SDLmini_flips++;
		flips_ = SDLmini_flips;
		if (SDLmini_diag_armed) {
			long nz = 0; int x, y;
			for (y = 0; y < screen->h; y++) {
				const Uint8 *p = (const Uint8 *)screen->pixels + (size_t)y * screen->pitch;
				for (x = 0; x < 256 && x < screen->w; x++) if (p[x]) nz++;
			}
			{
				char b[128];
				snprintf(b, sizeof b, "SDLmini: flip #%lu: %ld non-zero px in left 256 cols (pixels=%p chunky=%p)",
					flips_, nz, screen->pixels, (void *)amigagfx_chunky());
				SDLmini_Log(b);
			}
			if (--SDLmini_diag_armed <= 0) SDLmini_diag_armed = 0;
		}
	}
	{
		Uint32 t0_ = SDL_GetTicks();
		amigagfx_blit(0, 0, screen->w, (s_req_h > 0 && s_req_h < screen->h) ? s_req_h : screen->h);
		s_perf_c2p_ms += SDL_GetTicks() - t0_;
	}
	/* TEMP perf report, one line per 100 frames (LISTA-ROBOT pkt 1). */
	if ((SDLmini_flips % 100) == 0) {
		char b_[192];
		Uint32 now_ = SDL_GetTicks();
		snprintf(b_, sizeof b_,
			"perf: 100 frames in %lu ms: c2p %lu ms, blits ck %lu (%lu px) plain %lu (%lu px), fills %lu (%lu px)",
			(unsigned long)(now_ - s_perf_last_ms), s_perf_c2p_ms,
			s_perf_blits_ck, s_perf_px_ck, s_perf_blits, s_perf_px,
			s_perf_fills, s_perf_fill_px);
		SDLmini_Log(b_);
		s_perf_last_ms = now_;
		s_perf_c2p_ms = 0;
		s_perf_blits = s_perf_blits_ck = s_perf_px = s_perf_px_ck = 0;
		s_perf_fills = s_perf_fill_px = 0;
	}
	return 0;
}

void SDL_UpdateRect(SDL_Surface *screen, Sint32 x, Sint32 y, Uint32 w, Uint32 h)
{
	if (screen == NULL || screen != s_screen) return;
	if (w == 0 || h == 0) { x = 0; y = 0; w = (Uint32)screen->w; h = (Uint32)screen->h; }
	amigagfx_blit((int)x, (int)y, (int)w, (int)h);
}

void SDL_UpdateRects(SDL_Surface *screen, int numrects, SDL_Rect *rects)
{
	SDLMINI_FIRST("SDL_UpdateRects");
	int i;
	for (i = 0; i < numrects; i++) {
		SDL_UpdateRect(screen, rects[i].x, rects[i].y, rects[i].w, rects[i].h);
	}
}

SDL_Surface *SDL_GetVideoSurface(void) { return s_screen; }

/* The resolution list the options screen offers. 320x200 is the only mode the
 * game is drawn for; the others exist because amiga_gfx can open them and a
 * larger RTG screen with the game centred is sometimes what a player wants. */
static SDL_Rect  s_modes[]    = { { 0, 0, 320, 200 }, { 0, 0, 640, 400 }, { 0, 0, 640, 480 } };
static SDL_Rect *s_modelist[] = { &s_modes[0], &s_modes[1], &s_modes[2], NULL };

SDL_Rect **SDL_ListModes(SDL_PixelFormat *format, Uint32 flags)
{
	(void)format; (void)flags;
	return s_modelist;
}

int SDL_VideoModeOK(int width, int height, int bpp, Uint32 flags)
{
	(void)flags;
	if (bpp != 8) return 0;
	if (width <= 0 || height <= 0) return 0;
	return 8;
}

const SDL_VideoInfo *SDL_GetVideoInfo(void)
{
	static SDL_VideoInfo info;
	static SDL_PixelFormat fmt;
	fmt.BitsPerPixel  = 8;
	fmt.BytesPerPixel = 1;
	info.vfmt = &fmt;
	return &info;
}

char *SDL_VideoDriverName(char *namebuf, int maxlen)
{
	static const char *names[] = { "amiga-aga", "amiga-rtg", "amiga-ehb", "amiga-wb" };
	int b = amigagfx_backend();
	if (b < 0 || b > 3) b = 0;
	strncpy(namebuf, names[b], (size_t)maxlen - 1);
	namebuf[maxlen - 1] = '\0';
	return namebuf;
}
