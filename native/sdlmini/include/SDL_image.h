/*
 * SDLmini - the two SDL_image entry points OpenXcom uses.
 *
 * OpenXcom decodes PNG with its own bundled lodepng and only falls through to
 * SDL_image for whatever is left, which in practice means BMP. That is what
 * this implements; anything else fails with a clear message rather than
 * pulling a decoder library into a 68020 binary.
 */
#ifndef SDLMINI_SDL_IMAGE_H
#define SDLMINI_SDL_IMAGE_H

#include "SDL.h"

#ifdef __cplusplus
extern "C" {
#endif

extern SDL_Surface *IMG_Load(const char *file);
extern SDL_Surface *IMG_Load_RW(SDL_RWops *src, int freesrc);
extern const char  *IMG_GetError(void);

#ifdef __cplusplus
}
#endif

#endif /* SDLMINI_SDL_IMAGE_H */
