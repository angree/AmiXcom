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

/* loading splash (native/amiga_splash.c) */
extern void AmigaSplash_Show(void);
extern int  AmigaSplash_Active(void);
extern void AmigaSplash_End(void);

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

/* LISTA-ROBOT pkt 2, wariant C: per-surface span cache for colorkey blits.
 * Built once per surface CONTENT (rebuilt after any write), it lists for each
 * row the (offset, length) runs of NON-key pixels. A colorkey blit is then
 * pure memcpy per run - transparent pixels cost nothing at all, and the
 * per-pixel compares of variant A happen only once, at build time.
 * unused1: 0 unknown, 1 has key pixels but too noisy to cache (A path),
 * 2 fully opaque (memcpy path), 3 span cache attached (this). */
extern unsigned long SDLmini_ProfClassifyUs;
unsigned long amiga_uclock_us(void);
struct private_hwdata {
	Uint32 *rowoff;   /* [h] index into runs[] where the row starts */
	Uint16 *runs;     /* per row: count n, then n * (offset, length) */
};

static void spans_free(SDL_Surface *s)
{
	if (s->hwdata != NULL) {
		free(s->hwdata->rowoff);
		free(s->hwdata->runs);
		free(s->hwdata);
		s->hwdata = NULL;
	}
}

/* Every write path calls this: content changed, classification is stale. */
static void surf_touch(SDL_Surface *s)
{
	s->unused1 = 0;
	if (s->hwdata != NULL) spans_free(s);
}

/* One pass over the pixels: classify, and build the span cache on the fly.
 * If the surface turns out noisy (more runs than pixels/8 - alternating
 * pixels, dithered fills), the cache is dropped and variant A handles it. */
static Uint32 surf_classify(SDL_Surface *s)
{
	Uint8  key = (Uint8)(s->format->colorkey & 0xff);
	Uint32 maxpairs = (Uint32)s->w * (Uint32)s->h / 8U + (Uint32)s->h + 16U;
	Uint32 cap = (Uint32)s->h * 4U + 64U, idx = 0;
	int y, sawkey = 0;
	Uint32 *rowoff = (Uint32 *)malloc((size_t)s->h * sizeof(Uint32));
	Uint16 *runs   = (Uint16 *)malloc((size_t)cap * sizeof(Uint16));

	if (rowoff == NULL || runs == NULL) {
		free(rowoff); free(runs);
		return 1;                       /* no memory: A path, still correct */
	}
	for (y = 0; y < s->h; y++) {
		const Uint8 *p = (const Uint8 *)s->pixels + (size_t)y * s->pitch;
		Uint32 nidx;
		Uint16 n = 0;
		int x = 0;

		if (idx + 1 + 2U * ((Uint32)s->w / 2U + 1U) > cap) {
			Uint16 *grown;
			cap = cap * 2U + (Uint32)s->w;
			grown = (Uint16 *)realloc(runs, (size_t)cap * sizeof(Uint16));
			if (grown == NULL) { free(rowoff); free(runs); return 1; }
			runs = grown;
		}
		rowoff[y] = idx;
		nidx = idx++;                   /* count written after the row */
		while (x < s->w) {
			int start;
			while (x < s->w && p[x] == key) { x++; sawkey = 1; }
			if (x >= s->w) break;
			start = x;
			while (x < s->w && p[x] != key) x++;
			runs[idx++] = (Uint16)start;
			runs[idx++] = (Uint16)(x - start);
			n++;
		}
		runs[nidx] = n;
		if ((idx / 2U) > maxpairs) {    /* too noisy - not worth caching */
			free(rowoff); free(runs);
			return 1;
		}
	}
	if (!sawkey) { free(rowoff); free(runs); return 2; }

	s->hwdata = (struct private_hwdata *)malloc(sizeof(struct private_hwdata));
	if (s->hwdata == NULL) { free(rowoff); free(runs); return 1; }
	s->hwdata->rowoff = rowoff;
	s->hwdata->runs   = runs;
	return 3;
}

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
	spans_free(surface);
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

/* A lock means direct pixel writes we cannot see - whole screen dirty.
 * (Definitions live in the dirty-rectangle block further down.) */
static void dirty_add(int x, int y, int w, int h);
static void dirty_add_lock(SDL_Surface *s);
int SDL_LockSurface(SDL_Surface *surface)    { if (surface != NULL) { surf_touch(surface); dirty_add_lock(surface); } return 0; }
void SDL_UnlockSurface(SDL_Surface *surface) { if (surface != NULL) { surf_touch(surface); dirty_add_lock(surface); } }

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
	surf_touch(surface);   /* key changed: reclassify */
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
	if (surface == s_screen && !AmigaSplash_Active()) {
		push_palette_to_screen(colors, firstcolor, ncolors);
		/* Truecolour RTG converts pixels through the palette at blit time,
		 * so a palette change must reconvert everything on screen. */
		dirty_add(0, 0, surface->w, surface->h);
	}
	return 1;
}

/* Called by the game (StartState) when loading is done: fade the splash to
 * black, then hand the display back - push the palette the game set while it
 * was suppressed and reconvert the whole frame. */
void SDLmini_SplashFinish(void)
{
	AmigaSplash_End();
	if (s_screen != NULL && s_screen->format->palette != NULL) {
		SDL_SetColors(s_screen, s_screen->format->palette->colors, 0,
		              s_screen->format->palette->ncolors);
		dirty_add(0, 0, s_screen->w, s_screen->h);
	}
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
static unsigned long s_perf_c2p_px, s_perf_skips;        /* dirty-rect effect */
/* TEMP us-probes (2026-08-19): split the per-frame blit cost */
#include "amiga_uclock.h"
unsigned long SDLmini_ProfBlitBigUs = 0, SDLmini_ProfBlitBigN = 0, SDLmini_ProfBlitSmallUs = 0, SDLmini_ProfBlitSmallN = 0, SDLmini_ProfClassifyUs = 0, SDLmini_ProfFillUs = 0;

/* -------------------------------------------------- dirty rectangles ------
 * LISTA-ROBOT pkt 1. s_screen->pixels IS amiga_gfx's chunky buffer, so the
 * planar bitplanes (AGA) / display bitmap (RTG) keep showing the OLD content
 * of any region SDL_Flip does not convert - skipping c2p on unchanged pixels
 * is therefore safe by construction.
 *
 * The game (Screen::flip) blits its whole 320x200 back buffer onto s_screen
 * every frame, changed or not, so simply recording blit rectangles would mark
 * the full screen every time. Instead the plain full blit onto s_screen runs
 * as a DIFF-copy: compare in 32-byte cells (the c2p x grid), copy only cells
 * that differ, and grow the dirty union only around them. A clean frame costs
 * one read pass over both buffers and no copy, no c2p, no flip work at all.
 * All other writes to s_screen (fills, colorkey blits, locks) dirty their
 * rectangle the ordinary way. One union rectangle, not a list: the usual
 * changes (FPS counter, blink markers) cluster, and c2p_rect snaps x to 32
 * anyway. */
static int s_dirty_x0, s_dirty_y0, s_dirty_x1, s_dirty_y1; /* x1/y1 exclusive; empty when x1<=x0 */

static void dirty_add(int x, int y, int w, int h)
{
	if (w <= 0 || h <= 0) return;
	if (s_dirty_x1 <= s_dirty_x0) {
		s_dirty_x0 = x; s_dirty_y0 = y;
		s_dirty_x1 = x + w; s_dirty_y1 = y + h;
		return;
	}
	if (x < s_dirty_x0) s_dirty_x0 = x;
	if (y < s_dirty_y0) s_dirty_y0 = y;
	if (x + w > s_dirty_x1) s_dirty_x1 = x + w;
	if (y + h > s_dirty_y1) s_dirty_y1 = y + h;
}

static void dirty_add_lock(SDL_Surface *s)
{
	if (s == s_screen) dirty_add(0, 0, s->w, s->h);
}

static int SDL_FillRect_(SDL_Surface *dst, SDL_Rect *dstrect, Uint32 color);
int SDL_FillRect(SDL_Surface *dst, SDL_Rect *dstrect, Uint32 color)
{
	unsigned long ft0_ = amiga_uclock_us();
	int r_ = SDL_FillRect_(dst, dstrect, color);
	SDLmini_ProfFillUs += amiga_uclock_us() - ft0_;
	return r_;
}
static int SDL_FillRect_(SDL_Surface *dst, SDL_Rect *dstrect, Uint32 color)
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
	surf_touch(dst);   /* pixels change: reclassify */
	if (dst == s_screen) dirty_add(x, y, w, h);

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
static void blit8(SDL_Surface *src, const SDL_Rect *srcrect,
                  SDL_Surface *dst, const SDL_Rect *dstrect)
{
	int y;
	const Uint8 *sp = (const Uint8 *)src->pixels + (size_t)srcrect->y * src->pitch + srcrect->x;
	Uint8       *dp = (Uint8 *)dst->pixels       + (size_t)dstrect->y * dst->pitch + dstrect->x;
	int w = srcrect->w, h = srcrect->h;

	surf_touch(dst);    /* destination pixels change: reclassify before reuse */
	if ((src->flags & SDL_SRCCOLORKEY) && src->unused1 == 0)
		{ unsigned long ct0_ = amiga_uclock_us(); src->unused1 = surf_classify(src); SDLmini_ProfClassifyUs += amiga_uclock_us() - ct0_; }
	/* Colorkey blits onto the screen dirty their rectangle as-is; the plain
	 * path below diff-copies instead and dirties only what really changed. */
	if (dst == s_screen && (src->flags & SDL_SRCCOLORKEY) && src->unused1 != 2)
		dirty_add(dstrect->x, dstrect->y, w, h);
	if ((src->flags & SDL_SRCCOLORKEY) && src->unused1 == 3) {
		/* wariant C: walk the cached runs - memcpy only, no compares */
		struct private_hwdata *hd = src->hwdata;
		int sx0 = srcrect->x, sx1 = srcrect->x + w;
		s_perf_blits_ck++;
		s_perf_px_ck += (unsigned long)w * h;
		for (y = 0; y < h; y++) {
			const Uint16 *r = hd->runs + hd->rowoff[srcrect->y + y];
			const Uint8 *srow = (const Uint8 *)src->pixels + (size_t)(srcrect->y + y) * src->pitch;
			Uint8 *drow = (Uint8 *)dst->pixels + (size_t)(dstrect->y + y) * dst->pitch + dstrect->x;
			int i, n = *r++;
			for (i = 0; i < n; i++) {
				int off = r[0], len = r[1], a = off, b = off + len;
				r += 2;
				if (a < sx0) a = sx0;
				if (b > sx1) b = sx1;
				if (b > a) memcpy(drow + (a - sx0), srow + a, (size_t)(b - a));
			}
		}
	} else if ((src->flags & SDL_SRCCOLORKEY) && src->unused1 != 2) {
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
	} else if (dst == s_screen) {
		/* Diff-copy (see the dirty-rectangle comment above): compare in
		 * 32-byte cells, copy changed cells only, dirty the changed area. */
		int dy0 = -1, dy1 = -1, dx0 = w, dx1 = 0;
		s_perf_blits++;
		for (y = 0; y < h; y++) {
			int c;
			for (c = 0; c < w; c += 32) {
				int len = (w - c < 32) ? (w - c) : 32;
				if (memcmp(sp + c, dp + c, (size_t)len) != 0) {
					memcpy(dp + c, sp + c, (size_t)len);
					s_perf_px += (unsigned long)len;
					if (c < dx0) dx0 = c;
					if (c + len > dx1) dx1 = c + len;
					if (dy0 < 0) dy0 = y;
					dy1 = y;
				}
			}
			sp += src->pitch;
			dp += dst->pitch;
		}
		if (dy0 >= 0)
			dirty_add(dstrect->x + dx0, dstrect->y + dy0,
			          dx1 - dx0, dy1 - dy0 + 1);
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
	{
		unsigned long bt0_ = amiga_uclock_us();
		blit8(src, &sr, dst, &dr);
		bt0_ = amiga_uclock_us() - bt0_;
		if ((unsigned long)sr.w * sr.h >= 32000UL) { SDLmini_ProfBlitBigUs += bt0_; SDLmini_ProfBlitBigN++; }
		else { SDLmini_ProfBlitSmallUs += bt0_; SDLmini_ProfBlitSmallN++; }
	}
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
	dirty_add(0, 0, s_screen->w, s_screen->h);   /* fresh screen: convert all */
	AmigaSplash_Show();   /* loading splash, once, right after the screen opens */

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
	if (AmigaSplash_Active()) { SDLmini_flips++; return 0; }   /* splash owns the display */
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
		/* Convert only the dirty union; a clean frame skips c2p entirely. */
		int maxh = (s_req_h > 0 && s_req_h < screen->h) ? s_req_h : screen->h;
		int dx0 = s_dirty_x0, dy0 = s_dirty_y0, dx1 = s_dirty_x1, dy1 = s_dirty_y1;
		s_dirty_x0 = s_dirty_y0 = s_dirty_x1 = s_dirty_y1 = 0;
		if (dx0 < 0) dx0 = 0;
		if (dy0 < 0) dy0 = 0;
		if (dx1 > screen->w) dx1 = screen->w;
		if (dy1 > maxh) dy1 = maxh;
		if (dx1 > dx0 && dy1 > dy0) {
			Uint32 t0_ = SDL_GetTicks();
			amigagfx_blit(dx0, dy0, dx1 - dx0, dy1 - dy0);
			s_perf_c2p_ms += SDL_GetTicks() - t0_;
			s_perf_c2p_px += (unsigned long)(dx1 - dx0) * (dy1 - dy0);
		} else {
			s_perf_skips++;
		}
	}
	/* TEMP perf report, one line per 100 frames (LISTA-ROBOT pkt 1). */
	if ((SDLmini_flips % 100) == 0) {
		char b_[224];
		Uint32 now_ = SDL_GetTicks();
		snprintf(b_, sizeof b_,
			"perf: 100 frames in %lu ms: c2p %lu ms (%lu px, %lu skipped), blits ck %lu (%lu px) plain %lu (%lu px diff), fills %lu (%lu px)",
			(unsigned long)(now_ - s_perf_last_ms), s_perf_c2p_ms,
			s_perf_c2p_px, s_perf_skips,
			s_perf_blits_ck, s_perf_px_ck, s_perf_blits, s_perf_px,
			s_perf_fills, s_perf_fill_px);
		SDLmini_Log(b_);
		s_perf_last_ms = now_;
		s_perf_c2p_ms = 0;
		s_perf_c2p_px = s_perf_skips = 0;
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
