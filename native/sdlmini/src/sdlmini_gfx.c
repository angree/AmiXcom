/*
 * SDLmini - SDL_gfx primitives.
 *
 * What the game actually draws with these: the globe ocean disc
 * (filledCircleColor), globe coastlines, graph lines and the battlescape
 * minimap cursor (lineColor). Everything is integer Bresenham on an 8bpp
 * surface - no alpha blending, because every surface in this port has one
 * palette and no alpha channel to blend into.
 *
 * The text primitives are the exception and are honest no-ops: their only
 * caller is the developer map dump in BattlescapeState, and carrying an 8x8
 * font in the binary to letter a debug PNG is not a trade this port should
 * make. They log once, so a surprised developer finds out why.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "SDL_gfxPrimitives.h"
#include "sdlmini.h"

/* Map a packed RGBA colour to whatever this surface stores. Done once per
 * primitive, never per pixel. */
static Uint32 map_color(SDL_Surface *dst, Uint32 color)
{
	Uint8 r = (Uint8)((color >> 24) & 0xff);
	Uint8 g = (Uint8)((color >> 16) & 0xff);
	Uint8 b = (Uint8)((color >>  8) & 0xff);
	return SDL_MapRGB(dst->format, r, g, b);
}

static void put(SDL_Surface *dst, int x, int y, Uint32 pixel)
{
	Uint8 *p;
	if (x < dst->clip_rect.x || y < dst->clip_rect.y) return;
	if (x >= dst->clip_rect.x + dst->clip_rect.w) return;
	if (y >= dst->clip_rect.y + dst->clip_rect.h) return;

	p = (Uint8 *)dst->pixels + (size_t)y * dst->pitch + (size_t)x * dst->format->BytesPerPixel;
	switch (dst->format->BytesPerPixel) {
		case 1: *p = (Uint8)pixel; break;
		case 2: *(Uint16 *)p = (Uint16)pixel; break;
		case 3: p[0] = (Uint8)(pixel & 0xff); p[1] = (Uint8)((pixel >> 8) & 0xff); p[2] = (Uint8)((pixel >> 16) & 0xff); break;
		default: *(Uint32 *)p = pixel; break;
	}
}

/* Defined below, next to the textured fill that shares it. */
static int poly_spans(SDL_Surface *dst, const Sint16 *vx, const Sint16 *vy, int n,
                      void (*span)(SDL_Surface *, int, int, int, void *), void *ud);

int pixelColor(SDL_Surface *dst, Sint16 x, Sint16 y, Uint32 color)
{
	if (dst == NULL) return -1;
	put(dst, x, y, map_color(dst, color));
	return 0;
}

int pixelRGBA(SDL_Surface *dst, Sint16 x, Sint16 y, Uint8 r, Uint8 g, Uint8 b, Uint8 a)
{
	return pixelColor(dst, x, y, ((Uint32)r << 24) | ((Uint32)g << 16) | ((Uint32)b << 8) | a);
}

int lineColor(SDL_Surface *dst, Sint16 x1, Sint16 y1, Sint16 x2, Sint16 y2, Uint32 color)
{
	int dx, dy, sx, sy, err;
	Uint32 pixel;

	if (dst == NULL) return -1;
	pixel = map_color(dst, color);

	dx = (x2 > x1) ? (x2 - x1) : (x1 - x2);
	dy = (y2 > y1) ? (y2 - y1) : (y1 - y2);
	sx = (x1 < x2) ? 1 : -1;
	sy = (y1 < y2) ? 1 : -1;
	err = dx - dy;

	for (;;) {
		put(dst, x1, y1, pixel);
		if (x1 == x2 && y1 == y2) break;
		{
			int e2 = err * 2;
			if (e2 > -dy) { err -= dy; x1 = (Sint16)(x1 + sx); }
			if (e2 <  dx) { err += dx; y1 = (Sint16)(y1 + sy); }
		}
	}
	return 0;
}

int lineRGBA(SDL_Surface *dst, Sint16 x1, Sint16 y1, Sint16 x2, Sint16 y2,
             Uint8 r, Uint8 g, Uint8 b, Uint8 a)
{
	return lineColor(dst, x1, y1, x2, y2, ((Uint32)r << 24) | ((Uint32)g << 16) | ((Uint32)b << 8) | a);
}

/* Horizontal span [x1,x2] on row y, clipped once, then a memset for 8bpp (the
 * only depth the game draws in) and a per-pixel loop for anything else. This
 * is where the globe's fill time goes, so it must not clip per pixel. */
static void hspan(SDL_Surface *dst, int x1, int x2, int y, Uint32 pixel)
{
	int cx1 = dst->clip_rect.x, cx2 = cx1 + dst->clip_rect.w - 1;
	if (y < dst->clip_rect.y || y >= dst->clip_rect.y + dst->clip_rect.h) return;
	if (x1 < cx1) x1 = cx1;
	if (x2 > cx2) x2 = cx2;
	if (x1 > x2) return;
	if (dst->format->BytesPerPixel == 1) {
		memset((Uint8 *)dst->pixels + (size_t)y * dst->pitch + x1, (int)(pixel & 0xff), (size_t)(x2 - x1 + 1));
	} else {
		int x;
		for (x = x1; x <= x2; x++) put(dst, x, y, pixel);
	}
}

/* Filled circle, midpoint algorithm, drawn as horizontal spans. */
int filledCircleColor(SDL_Surface *dst, Sint16 cx, Sint16 cy, Sint16 rad, Uint32 color)
{
	int x, y, err;
	Uint32 pixel;

	if (dst == NULL || rad < 0) return -1;
	pixel = map_color(dst, color);

	x   = rad;
	y   = 0;
	err = 1 - x;

	while (x >= y) {
		hspan(dst, cx - x, cx + x, cy + y, pixel);
		if (y) hspan(dst, cx - x, cx + x, cy - y, pixel);
		if (x != y) {
			hspan(dst, cx - y, cx + y, cy + x, pixel);
			hspan(dst, cx - y, cx + y, cy - x, pixel);
		}
		y++;
		if (err < 0) {
			err += 2 * y + 1;
		} else {
			x--;
			err += 2 * (y - x) + 1;
		}
	}
	return 0;
}

int filledCircleRGBA(SDL_Surface *dst, Sint16 x, Sint16 y, Sint16 rad, Uint8 r, Uint8 g, Uint8 b, Uint8 a)
{
	return filledCircleColor(dst, x, y, rad, ((Uint32)r << 24) | ((Uint32)g << 16) | ((Uint32)b << 8) | a);
}

static void span_flat(SDL_Surface *dst, int x1, int x2, int y, void *ud)
{
	hspan(dst, x1, x2, y, *(Uint32 *)ud);
}

/* Port-specific: fill a polygon with a palette INDEX on an 8bpp surface. The
 * SDL_gfx API only takes RGBA, and mapping an index to RGB and back is not the
 * identity on these palettes (several blocks share colours), which would put a
 * land pixel into the wrong shading block. */
int SDLmini_FilledPolygon8(SDL_Surface *dst, const Sint16 *vx, const Sint16 *vy, int n, Uint8 index)
{
	Uint32 pixel = index;
	if (dst == NULL || dst->format->BitsPerPixel != 8) return -1;
	return poly_spans(dst, vx, vy, n, span_flat, &pixel);
}

/* Even-odd scanline polygon fill, the same rule SDL_gfx uses. */
int filledPolygonColor(SDL_Surface *dst, const Sint16 *vx, const Sint16 *vy, int n, Uint32 color)
{
	Uint32 pixel;
	if (dst == NULL) return -1;
	pixel = map_color(dst, color);
	return poly_spans(dst, vx, vy, n, span_flat, &pixel);
}

/* Scanline fill shared by the flat and textured polygon fills: computes the
 * crossings for one row and hands each span to a callback. Keeping it in one
 * place means the globe and the flat fill cannot disagree about which pixels
 * are inside a polygon - which would show up as a one-pixel seam between the
 * ocean and the land. */
static int poly_spans(SDL_Surface *dst, const Sint16 *vx, const Sint16 *vy, int n,
                      void (*span)(SDL_Surface *, int, int, int, void *), void *ud)
{
	int ymin, ymax, y, i;
	int *xs;

	if (dst == NULL || vx == NULL || vy == NULL || n < 3) return -1;

	ymin = ymax = vy[0];
	for (i = 1; i < n; i++) {
		if (vy[i] < ymin) ymin = vy[i];
		if (vy[i] > ymax) ymax = vy[i];
	}
	if (ymin < dst->clip_rect.y) ymin = dst->clip_rect.y;
	if (ymax >= dst->clip_rect.y + dst->clip_rect.h) ymax = dst->clip_rect.y + dst->clip_rect.h - 1;

	xs = (int *)malloc((size_t)n * sizeof(int));
	if (xs == NULL) return -1;

	for (y = ymin; y <= ymax; y++) {
		int count = 0;
		int j = n - 1;
		for (i = 0; i < n; i++) {
			int y1 = vy[j], y2 = vy[i];
			if ((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) {
				int x1 = vx[j], x2 = vx[i];
				xs[count++] = x1 + (y - y1) * (x2 - x1) / (y2 - y1);
			}
			j = i;
		}
		for (i = 1; i < count; i++) {
			int v = xs[i], k = i - 1;
			while (k >= 0 && xs[k] > v) { xs[k + 1] = xs[k]; k--; }
			xs[k + 1] = v;
		}
		for (i = 0; i + 1 < count; i += 2) {
			span(dst, xs[i], xs[i + 1], y, ud);
		}
	}
	free(xs);
	return 0;
}

typedef struct {
	SDL_Surface *texture;
	int dx, dy;
} TexSpan;

/* SDL_gfx samples the texture at (x - texture_dx, y - texture_dy), wrapping in
 * both directions. The wrap is one modulo per SPAN, then incremental: a `%`
 * per pixel is a 68020 divide per pixel, which is what made the globe's land
 * fill cost as much as its ocean and radars together. Clipped once per span. */
static void span_textured(SDL_Surface *dst, int x1, int x2, int y, void *ud)
{
	TexSpan *t = (TexSpan *)ud;
	SDL_Surface *tex = t->texture;
	int tw = tex->w, th = tex->h;
	int ty = (y - t->dy) % th;
	int tx, cx1, cx2;
	const Uint8 *trow;
	Uint8 *drow;

	if (y < dst->clip_rect.y || y >= dst->clip_rect.y + dst->clip_rect.h) return;
	cx1 = dst->clip_rect.x; cx2 = cx1 + dst->clip_rect.w - 1;
	if (x1 < cx1) x1 = cx1;
	if (x2 > cx2) x2 = cx2;
	if (x1 > x2) return;

	if (ty < 0) ty += th;
	trow = (const Uint8 *)tex->pixels + (size_t)ty * tex->pitch;
	tx = (x1 - t->dx) % tw;
	if (tx < 0) tx += tw;
	drow = (Uint8 *)dst->pixels + (size_t)y * dst->pitch;

	for (; x1 <= x2; x1++) {
		drow[x1] = trow[tx];
		if (++tx == tw) tx = 0;
	}
}

int texturedPolygon(SDL_Surface *dst, const Sint16 *vx, const Sint16 *vy, int n,
                    SDL_Surface *texture, int texture_dx, int texture_dy)
{
	TexSpan t;

	if (dst == NULL || texture == NULL) return -1;
	if (dst->format->BitsPerPixel != 8 || texture->format->BitsPerPixel != 8) {
		SDLmini_Log("SDLmini: texturedPolygon needs 8bpp surfaces");
		return -1;
	}
	{
		static int once_;
		if (!once_) {
			char b[160];
			once_ = 1;
			snprintf(b, sizeof b, "SDLmini: first texturedPolygon n=%d v0=%d,%d v1=%d,%d tex %dx%d off %d,%d", n, (int)vx[0], (int)vy[0], (int)vx[1], (int)vy[1], texture->w, texture->h, texture_dx, texture_dy);
			SDLmini_Log(b);
		}
	}
	t.texture = texture;
	t.dx = texture_dx;
	t.dy = texture_dy;
	return poly_spans(dst, vx, vy, n, span_textured, &t);
}

/* ----------------------------------------------------------------- text -- */

static int s_text_warned;

static int text_noop(void)
{
	if (!s_text_warned) {
		s_text_warned = 1;
		SDLmini_Log("SDLmini: SDL_gfx text primitives are no-ops (debug map dump only)");
	}
	return 0;
}

int characterColor(SDL_Surface *dst, Sint16 x, Sint16 y, char c, Uint32 color)
{
	(void)dst; (void)x; (void)y; (void)c; (void)color;
	return text_noop();
}

int characterRGBA(SDL_Surface *dst, Sint16 x, Sint16 y, char c, Uint8 r, Uint8 g, Uint8 b, Uint8 a)
{
	(void)dst; (void)x; (void)y; (void)c; (void)r; (void)g; (void)b; (void)a;
	return text_noop();
}

int stringColor(SDL_Surface *dst, Sint16 x, Sint16 y, const char *s, Uint32 color)
{
	(void)dst; (void)x; (void)y; (void)s; (void)color;
	return text_noop();
}

int stringRGBA(SDL_Surface *dst, Sint16 x, Sint16 y, const char *s, Uint8 r, Uint8 g, Uint8 b, Uint8 a)
{
	(void)dst; (void)x; (void)y; (void)s; (void)r; (void)g; (void)b; (void)a;
	return text_noop();
}
