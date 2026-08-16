/*
 * Amiga port replacement for src/Engine/Zoom.cpp.
 *
 * Upstream Zoom.cpp exists to scale the 320x200 game buffer up to a modern
 * desktop resolution, through SDL_gfx, the HQX/xBRZ scalers, SSE2 paths and
 * OpenGL. None of that belongs on a 68020: the port runs the game at its
 * native 320x200 and lets the display hardware show it, so the whole file
 * reduces to a straight copy plus an honest nearest-neighbour fallback for
 * the case where somebody opens a larger screen anyway.
 *
 * The class interface is unchanged, so no caller had to be patched.
 */
#include "Zoom.h"

#include <string.h>

#include "Surface.h"
#include "Options.h"
#include "OpenGL.h"

namespace OpenXcom
{

/**
 * Nearest-neighbour 8bpp scaler. Only used when the opened screen is larger
 * than the game surface; the 1:1 case never reaches it.
 */
int Zoom::_zoomSurfaceY(SDL_Surface *src, SDL_Surface *dst, int flipx, int flipy)
{
	(void)flipx;
	(void)flipy;

	if (src == 0 || dst == 0) return -1;
	if (src->format->BitsPerPixel != 8 || dst->format->BitsPerPixel != 8) return -1;

	for (int y = 0; y < dst->h; ++y)
	{
		const Uint8 *srcRow = (const Uint8 *)src->pixels + (size_t)(y * src->h / dst->h) * src->pitch;
		Uint8 *dstRow = (Uint8 *)dst->pixels + (size_t)y * dst->pitch;

		if (src->w == dst->w)
		{
			memcpy(dstRow, srcRow, (size_t)src->w);
		}
		else
		{
			for (int x = 0; x < dst->w; ++x)
			{
				dstRow[x] = srcRow[x * src->w / dst->w];
			}
		}
	}
	return 0;
}

/**
 * Puts the game surface on the screen.
 *
 * The black bands upstream computes for letterboxing a scaled image are
 * honoured, so a game surface smaller than the screen lands centred instead
 * of in the corner.
 */
void Zoom::flipWithZoom(SDL_Surface *src, SDL_Surface *dst, int topBlackBand, int bottomBlackBand, int leftBlackBand, int rightBlackBand, OpenGL *glOut)
{
	(void)glOut;

	if (src == 0 || dst == 0) return;

	if (src->w == dst->w && src->h == dst->h && topBlackBand == 0 && leftBlackBand == 0)
	{
		for (int y = 0; y < src->h; ++y)
		{
			memcpy((Uint8 *)dst->pixels + (size_t)y * dst->pitch,
			       (const Uint8 *)src->pixels + (size_t)y * src->pitch,
			       (size_t)src->w);
		}
		return;
	}

	SDL_Rect area;
	area.x = (Sint16)leftBlackBand;
	area.y = (Sint16)topBlackBand;
	area.w = (Uint16)(dst->w - leftBlackBand - rightBlackBand);
	area.h = (Uint16)(dst->h - topBlackBand - bottomBlackBand);

	SDL_FillRect(dst, 0, 0);

	if ((int)area.w == src->w && (int)area.h == src->h)
	{
		SDL_Rect dr = area;
		SDL_BlitSurface(src, 0, dst, &dr);
		return;
	}

	// Scaled: build a view of the target area and stretch into it.
	SDL_Surface view;
	view = *dst;
	view.w = area.w;
	view.h = area.h;
	view.pixels = (Uint8 *)dst->pixels + (size_t)area.y * dst->pitch + area.x;
	_zoomSurfaceY(src, &view, 0, 0);
}

/**
 * There is no SSE2 on a 68020, and nothing here asks twice.
 */
bool Zoom::haveSSE2()
{
	return false;
}

}
