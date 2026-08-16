/*
 * SDLmini - the handful of SDL_gfx primitives OpenXcom draws with.
 *
 * Colours are packed RGBA (R<<24 | G<<16 | B<<8 | A), exactly as SDL_gfx
 * takes them and as OpenXcom's Palette::getRGBA produces them; on the 8bpp
 * surfaces this port uses they are mapped back to a palette index once per
 * call, never per pixel.
 */
#ifndef SDLMINI_SDL_GFXPRIMITIVES_H
#define SDLMINI_SDL_GFXPRIMITIVES_H

#include "SDL.h"

#ifdef __cplusplus
extern "C" {
#endif

extern int pixelColor(SDL_Surface *dst, Sint16 x, Sint16 y, Uint32 color);
extern int pixelRGBA(SDL_Surface *dst, Sint16 x, Sint16 y, Uint8 r, Uint8 g, Uint8 b, Uint8 a);

extern int lineColor(SDL_Surface *dst, Sint16 x1, Sint16 y1, Sint16 x2, Sint16 y2, Uint32 color);
extern int lineRGBA(SDL_Surface *dst, Sint16 x1, Sint16 y1, Sint16 x2, Sint16 y2,
                    Uint8 r, Uint8 g, Uint8 b, Uint8 a);

extern int filledCircleColor(SDL_Surface *dst, Sint16 x, Sint16 y, Sint16 rad, Uint32 color);
extern int filledCircleRGBA(SDL_Surface *dst, Sint16 x, Sint16 y, Sint16 rad,
                            Uint8 r, Uint8 g, Uint8 b, Uint8 a);

/* Port-specific: fill with a palette index (8bpp only). See sdlmini_gfx.c. */
extern int SDLmini_FilledPolygon8(SDL_Surface *dst, const Sint16 *vx, const Sint16 *vy, int n, Uint8 index);
extern int filledPolygonColor(SDL_Surface *dst, const Sint16 *vx, const Sint16 *vy, int n, Uint32 color);

/* The globe is drawn with this one: a polygon filled from a wrapping texture
 * surface rather than a flat colour. */
extern int texturedPolygon(SDL_Surface *dst, const Sint16 *vx, const Sint16 *vy, int n,
                           SDL_Surface *texture, int texture_dx, int texture_dy);

extern int characterColor(SDL_Surface *dst, Sint16 x, Sint16 y, char c, Uint32 color);
extern int characterRGBA(SDL_Surface *dst, Sint16 x, Sint16 y, char c, Uint8 r, Uint8 g, Uint8 b, Uint8 a);
extern int stringColor(SDL_Surface *dst, Sint16 x, Sint16 y, const char *s, Uint32 color);
extern int stringRGBA(SDL_Surface *dst, Sint16 x, Sint16 y, const char *s,
                      Uint8 r, Uint8 g, Uint8 b, Uint8 a);

#ifdef __cplusplus
}
#endif

#endif /* SDLMINI_SDL_GFXPRIMITIVES_H */
